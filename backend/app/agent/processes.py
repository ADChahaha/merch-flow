"""清理任务的整个进程树，包括独立进程组里的 dsh 和浏览器脚本。"""

from __future__ import annotations

import subprocess

import psutil


def kill_process_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        root = psutil.Process(proc.pid)
        # 先暂停父进程，防止在清理过程中再启动新的子进程。
        root.suspend()
        children = root.children(recursive=True)
        for child in children:
            try:
                child.suspend()
            except psutil.NoSuchProcess:
                pass
        # 再取一次：覆盖第一次枚举时仍在运行的子进程产生的后代。
        children = root.children(recursive=True)
        for child in reversed(children):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        root.kill()
    except psutil.NoSuchProcess:
        pass
    finally:
        # 保证父进程不会因枚举失败而停在 suspended 状态。
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
