"""把浏览器会话固定在一个专用线程上。

为什么需要这个：

Playwright / Scrapling 的 **同步** API 对象绑定创建它们的线程和 greenlet，
换个线程调用就会炸：

    greenlet.error: Cannot switch to a different thread

FastAPI 的同步端点跑在 threadpool 里（每次请求可能是不同线程），
而浏览器会话是跨请求复用的，于是必然踩到：
进程退出时主线程去 close() → 抛异常 → 后面的「杀掉临时 Chrome」被跳过 →
留下一堆孤儿 Chrome 进程。

解法：会话的创建、取页、关闭全部通过一个专用线程执行（`call()`），
playwright 对象永远只被同一个线程碰。
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SessionThread:
    """单线程执行器：所有浏览器操作都排到这一个线程里跑。

    自带串行化效果 —— 同一站点的并发抓取会排队，顺带起到了限速作用。
    """

    def __init__(self, name: str = "ec-browser") -> None:
        self.name = name
        self._queue: queue.Queue = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        while True:
            func, box, done = self._queue.get()
            if func is None:
                done.set()
                return
            try:
                box["result"] = func()
            except BaseException as exc:  # noqa: BLE001  要原样带回调用方
                box["error"] = exc
            finally:
                done.set()

    def call(self, func: Callable[[], T], timeout: float | None = None) -> T:
        """在会话线程里执行 func 并等结果。"""
        if self._closed:
            raise RuntimeError(f"会话线程 {self.name} 已关闭")
        box: dict[str, Any] = {}
        done = threading.Event()
        self._queue.put((func, box, done))
        if not done.wait(timeout):
            raise TimeoutError(f"会话线程 {self.name} 超时（{timeout}s）")
        if "error" in box:
            raise box["error"]
        return box.get("result")

    def shutdown(self, timeout: float = 10.0) -> None:
        if self._closed:
            return
        self._closed = True
        if threading.current_thread() is self._thread:
            return
        try:
            done = threading.Event()
            self._queue.put((None, {}, done))
            done.wait(timeout)
        except Exception:  # noqa: BLE001
            logger.debug("关闭会话线程 %s 失败", self.name, exc_info=True)

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def closed(self) -> bool:
        return self._closed


def safe_close(*steps: tuple[str, Callable[[], Any]]) -> None:
    """逐步关闭，任何一步炸了都不影响后面的步骤。

    踩过的坑：close() 里第一步抛异常，后面的「杀临时 Chrome」被跳过，
    于是残留一堆浏览器进程。清理逻辑必须彼此独立。
    """
    for label, step in steps:
        try:
            step()
        except Exception:  # noqa: BLE001
            logger.debug("关闭步骤 %s 失败（继续后面的清理）", label, exc_info=True)
