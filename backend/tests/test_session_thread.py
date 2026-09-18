"""会话线程 + 关闭清理的回归用例。

真实事故（两个叠加）：
  1. playwright 的同步对象绑线程，FastAPI 的 threadpool 里换个线程调用就炸
     `greenlet.error: Cannot switch to a different thread`；
  2. 关闭逻辑第一步抛异常后，后面的「杀掉临时 Chrome」被跳过 →
     残留一堆孤儿浏览器进程。
"""

from __future__ import annotations

import threading
import time

import pytest

from app.scrapers.session_thread import SessionThread, safe_close


def test_callback_runs_in_the_session_thread_not_the_caller():
    ex = SessionThread("t1")
    try:
        caller = threading.get_ident()
        seen = ex.call(threading.get_ident)
        assert seen != caller
    finally:
        ex.shutdown()


def test_same_thread_for_every_call():
    ex = SessionThread("t2")
    try:
        ids = {ex.call(threading.get_ident) for _ in range(5)}
        assert len(ids) == 1, "playwright 对象要求每次调用都在同一个线程"
    finally:
        ex.shutdown()


def test_calls_from_many_threads_are_marshalled_to_one_thread():
    ex = SessionThread("t3")
    seen: list[int] = []
    lock = threading.Lock()

    def worker():
        value = ex.call(threading.get_ident)
        with lock:
            seen.append(value)

    try:
        threads = [threading.Thread(target=worker) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        assert len(set(seen)) == 1, "并发请求也必须落到同一个会话线程"
    finally:
        ex.shutdown()


def test_exception_propagates_to_caller():
    ex = SessionThread("t4")
    try:
        with pytest.raises(ValueError, match="boom"):
            ex.call(lambda: (_ for _ in ()).throw(ValueError("boom")))
    finally:
        ex.shutdown()


def test_timeout_does_not_hang_forever():
    ex = SessionThread("t5")
    try:
        with pytest.raises(TimeoutError):
            ex.call(lambda: time.sleep(3), timeout=0.2)
    finally:
        ex.shutdown()


def test_call_after_shutdown_raises():
    ex = SessionThread("t6")
    ex.shutdown()
    with pytest.raises(RuntimeError):
        ex.call(lambda: 1)


def test_safe_close_keeps_going_after_a_failure():
    """关闭时第一步炸了，后面几步照样要执行 —— 否则临时 Chrome 会残留。"""
    done: list[str] = []

    def boom():
        raise RuntimeError("first step failed")

    safe_close(
        ("会炸的一步", boom),
        ("杀 Chrome", lambda: done.append("killed")),
        ("再炸一次", boom),
        ("收尾", lambda: done.append("done")),
    )

    assert done == ["killed", "done"]


# --------------------------------------------------------------------------- #
# 空闲自动关浏览器：抓完不能一直挂着
# --------------------------------------------------------------------------- #
def test_idle_reaper_closes_and_forgets_transport(monkeypatch):
    from app import scrapers
    from app.scrapers import transport as transport_module

    closed: list[str] = []

    class FakeTransport:
        def close(self):
            closed.append("closed")

    transport_module._TRANSPORT_CACHE.clear()
    transport_module._LAST_USED.clear()
    transport_module._TRANSPORT_CACHE["surugaya:chrome_cdp"] = FakeTransport()
    transport_module._LAST_USED["surugaya:chrome_cdp"] = 0.0  # 很久没用过
    transport_module._TRANSPORT_CACHE["melonbooks:http"] = FakeTransport()
    transport_module._LAST_USED["melonbooks:http"] = 1e18  # 刚刚用过

    transport_module._reap_once(idle_timeout=180)

    assert closed == ["closed"], "只关空闲的那个"
    assert list(transport_module._TRANSPORT_CACHE) == ["melonbooks:http"]


def test_touch_keeps_transport_alive(monkeypatch):
    from app.scrapers import transport as transport_module

    class FakeTransport:
        closed = False

        def close(self):
            self.closed = True

    transport_module._TRANSPORT_CACHE.clear()
    transport_module._LAST_USED.clear()
    fake = FakeTransport()
    transport_module._TRANSPORT_CACHE["surugaya:chrome_cdp"] = fake
    transport_module.touch_transport("surugaya", "chrome_cdp")
    transport_module._reap_once(idle_timeout=180)

    assert fake.closed is False
    transport_module._TRANSPORT_CACHE.clear()
    transport_module._LAST_USED.clear()


# --------------------------------------------------------------------------- #
# 进程退出兜底：脚本/CLI 跑完不能把浏览器留成孤儿
# （实测残留过 30 个 Chrome 进程）
# --------------------------------------------------------------------------- #
def test_close_on_exit_closes_cached_transports(monkeypatch):
    from app.scrapers import transport as transport_module

    closed: list[str] = []
    monkeypatch.setattr(transport_module, "_close_cached", lambda key: closed.append(key))

    transport_module._TRANSPORT_CACHE.clear()
    transport_module._TRANSPORT_CACHE["surugaya:chrome_cdp"] = object()
    transport_module._TRANSPORT_CACHE["melonbooks:http"] = object()
    try:
        transport_module._close_on_exit()
        assert sorted(closed) == ["melonbooks:http", "surugaya:chrome_cdp"]
    finally:
        transport_module._TRANSPORT_CACHE.clear()


def test_close_on_exit_is_registered_with_atexit():
    import atexit

    from app.scrapers.transport import _close_on_exit

    assert hasattr(atexit, "_ncallbacks"), "CPython 才有；换成别的实现就跳过这个断言"
    registered = getattr(atexit, "_ncallbacks")()
    assert registered > 0
    assert callable(_close_on_exit)
