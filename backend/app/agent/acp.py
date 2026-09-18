"""dsh 的 ACP 客户端（Agent Client Protocol，stdio + NDJSON）。

用 ACP 而不是 headless 的原因：headless 每次都是新会话，没有上下文；
ACP 有 session/new / session/resume / session/prompt —— 同一个任务后面
还能接着聊（带着之前的对话和 products.json 继续改）。

只实现我们需要的子集：initialize / session.new / session.resume / session.prompt，
流式 session/update 回调给上层转日志，agent 发来的权限请求自动放行（沙箱本身是
workspace-write，写入仍被限制在任务目录）。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

PROTOCOL_VERSION = 1
DEFAULT_TIMEOUT = 900.0


class AcpError(RuntimeError):
    pass


class AcpNotFound(AcpError):
    pass


def summarize_update(update: dict) -> dict | None:
    """把 ACP 的 session/update 压成一条日志（不认识的就返回 None）。"""
    kind = update.get("sessionUpdate")
    content = update.get("content")
    text = content.get("text", "") if isinstance(content, dict) else ""

    if kind == "agent_thought_chunk":
        return {"level": "think", "text": text} if text else None
    if kind == "agent_message_chunk":
        return {"level": "agent-chunk", "text": text} if text else None
    if kind in {"tool_call", "tool_call_update"}:
        title = str(update.get("title") or update.get("kind") or "工具调用")
        status = str(update.get("status") or "")
        if kind == "tool_call_update" and not update.get("title") and not status:
            return None
        suffix = f"（{status}）" if status and status != "pending" else ""
        return {"level": "tool", "text": f"{title}{suffix}"}
    return None


class AcpClient:
    """一条 dsh ACP 连接。进程活着期间可以多轮 prompt（同一会话继续聊）。"""

    def __init__(
        self,
        cwd: str | Path,
        *,
        patch_path: str | Path | None = None,
        api_key: str = "",
        on_event=lambda kind, payload: None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.cwd = str(cwd)
        self.patch_path = str(patch_path) if patch_path else None
        self.api_key = api_key
        self.on_event = on_event
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self._responses: dict[int, queue.Queue] = {}
        self._next_id = 0
        self._write_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    def __enter__(self) -> "AcpClient":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()

    def start(self) -> None:
        cmd = ["dsh"]
        if self.patch_path:
            cmd += ["--patch", self.patch_path]
        cmd += ["--profile", "acp"]

        env = os.environ.copy()
        if self.api_key:
            env["DEEPSEEK_API_KEY"] = self.api_key
        env.setdefault("DSH_PERMISSION_MODE", "workspace-write")
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=self.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise AcpNotFound("找不到 dsh：npm install -g @deepseek-ai/dsh") from exc

        threading.Thread(target=self._read_stdout, name="acp-stdout", daemon=True).start()
        threading.Thread(target=self._drain_stderr, name="acp-stderr", daemon=True).start()

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), 15)
        except (OSError, ProcessLookupError):
            try:
                proc.kill()
            except OSError:
                pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass

    # ------------------------------------------------------------------ #
    def _send(self, method: str, params: dict):
        if self.proc is None or self.proc.stdin is None:
            raise AcpError("ACP 进程没起来")
        with self._write_lock:
            self._next_id += 1
            message_id = self._next_id
        box: queue.Queue = queue.Queue()
        self._responses[message_id] = box
        payload = {"jsonrpc": "2.0", "id": message_id, "method": method, "params": params}
        try:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._responses.pop(message_id, None)
            raise AcpError(f"ACP 进程已断开：{exc}") from exc
        try:
            response = box.get(timeout=self.timeout)
        except queue.Empty as exc:
            raise AcpError(f"{method} 超时（{self.timeout:.0f}s）") from exc
        finally:
            self._responses.pop(message_id, None)
        if "error" in response:
            raise AcpError(f"{method} 失败：{response['error']}")
        return response.get("result") or {}

    def _reply(self, message_id, result: dict) -> None:
        if self.proc is None or self.proc.stdin is None:
            return
        with self._write_lock:
            try:
                self.proc.stdin.write(
                    json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}, ensure_ascii=False) + "\n"
                )
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def _read_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            text = line.strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                self.on_event("noise", text)
                continue

            if "result" in message or "error" in message:
                box = self._responses.get(message.get("id"))
                if box is not None:
                    box.put(message)
                continue

            method = message.get("method")
            if method == "session/update":
                self.on_event("update", message.get("params") or {})
            elif method == "session/request_permission":
                self._answer_permission(message)
            elif method:
                # 其他 agent→client 请求：当前不需要，空回避免它卡住
                self._reply(message.get("id"), {})

    def _drain_stderr(self) -> None:
        if self.proc is None or self.proc.stderr is None:
            return
        for line in self.proc.stderr:
            text = line.rstrip("\n")
            if text:
                self.on_event("stderr", text)

    def _answer_permission(self, message: dict) -> None:
        options = (message.get("params") or {}).get("options") or []
        chosen = next(
            (opt for opt in options if str(opt.get("kind", "")).startswith("allow")),
            options[0] if options else None,
        )
        if chosen is None:
            self._reply(message.get("id"), {"outcome": {"outcome": "cancelled"}})
            return
        self._reply(
            message.get("id"),
            {"outcome": {"outcome": "selected", "optionId": chosen.get("optionId")}},
        )

    # ------------------------------------------------------------------ #
    def initialize(self) -> dict:
        return self._send(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}},
        )

    def new_session(self) -> str:
        result = self._send("session/new", {"cwd": self.cwd, "mcpServers": []})
        session_id = result.get("sessionId")
        if not session_id:
            raise AcpError(f"session/new 没返回 sessionId：{result}")
        return str(session_id)

    def resume_session(self, session_id: str) -> str:
        result = self._send(
            "session/resume", {"sessionId": session_id, "cwd": self.cwd, "mcpServers": []}
        )
        return str(result.get("sessionId") or session_id)

    def prompt(self, session_id: str, text: str) -> str:
        """发一轮用户消息，等 agent 跑完；回复内容通过 on_event 流出。"""
        result = self._send(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
        )
        return str(result.get("stopReason") or "")
