from unittest.mock import Mock
import subprocess
import sys

from app.agent import browser_cli, publish


def test_frozen_browser_wrapper_uses_bundled_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(publish.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(publish.sys, 'executable', '/bundle/backend')
    publish.write_publish_workdir(tmp_path, {'items': []})
    calls = []
    monkeypatch.setattr(subprocess, 'call', lambda cmd: calls.append(cmd) or 0)
    monkeypatch.setattr(sys, 'argv', ['browser.py', 'check'])
    import pytest
    with pytest.raises(SystemExit) as result:
        exec((tmp_path / 'browser.py').read_text(), {'__name__': '__main__'})
    assert result.value.code == 0
    assert calls == [['/bundle/backend', '--browser', 'check']]


def test_launch_keeps_login_browser_outside_task_process_group(monkeypatch):
    import app.scrapers.browser as browser
    monkeypatch.setattr(browser, 'find_chrome', lambda path: '/browser/chrome')
    def offline(*args, **kwargs):
        raise OSError('not running')
    monkeypatch.setattr(browser_cli, 'urlopen', offline)
    spawn = Mock()
    monkeypatch.setattr(browser_cli.subprocess, 'Popen', spawn)
    assert browser_cli.main(['launch']) == 0
    kwargs = spawn.call_args.kwargs
    if sys.platform == 'win32':
        assert kwargs['creationflags'] & subprocess.DETACHED_PROCESS
    else:
        assert kwargs['start_new_session'] is True
    assert kwargs['stdin'] == subprocess.DEVNULL


def test_typing_uses_platform_select_all(monkeypatch):
    page = Mock()
    browser = Mock(contexts=[Mock(pages=[page])])
    play = Mock()
    monkeypatch.setattr(browser_cli, 'connect', lambda: (play, browser))
    monkeypatch.setattr(browser_cli.sys, 'platform', 'darwin')
    browser_cli.main(['type', '#price', '12.99'])
    assert page.keyboard.press.call_args_list[0].args == ('Meta+A',)
    play.stop.assert_called_once()
