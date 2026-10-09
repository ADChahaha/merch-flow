"""清理专属进程组中的任务，以及另外建立进程组的后代。"""
from __future__ import annotations

import logging
import os
import signal
import subprocess

import psutil

logger = logging.getLogger(__name__)


def kill_process_tree(proc: subprocess.Popen) -> None:
    """proc 必须由 start_new_session=True 启动，不能传入应用自身的进程。"""
    groups = {proc.pid} if os.name != "nt" else set()
    children = []
    try:
        if proc.poll() is None:
            root = psutil.Process(proc.pid)
            root.suspend()
            children = root.children(recursive=True)
            for child in children:
                try:
                    child.suspend()
                except psutil.NoSuchProcess:
                    pass
            # 收集独立进程组；组内被系统接管的孤儿进程无法靠 children 找到。
            children = root.children(recursive=True)
            if os.name != "nt":
                for child in children:
                    try:
                        group = os.getpgid(child.pid)
                        if group != os.getpgrp():
                            groups.add(group)
                    except ProcessLookupError:
                        pass
            for child in reversed(children):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
    except psutil.NoSuchProcess:
        pass
    finally:
        # 即使根进程已退出，仍清理其专属组，避免漏掉重新托管的后台任务。
        for group in groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # macOS 对只剩僵尸的组也可能返回 EPERM；不能因此跳过根进程清理。
                logger.debug("无法向进程组 %s 发信号", group, exc_info=True)
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
