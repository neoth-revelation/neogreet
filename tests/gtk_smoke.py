"""Run with xvfb-run -a python3 tests/gtk_smoke.py on a GTK4 host."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

loader = importlib.machinery.SourceFileLoader("neogreet", str(Path(__file__).resolve().parents[1] / "bin/neogreet"))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
from gi.repository import GLib

with tempfile.TemporaryDirectory() as directory:
    sessions = Path(directory) / "wayland-sessions"
    sessions.mkdir()
    (sessions / "demo.desktop").write_text("[Desktop Entry]\nName=Demo\nExec=demo-session\n")
    (Path(directory) / "state.json").write_text('{"last_user":"demo","last_session":"demo.desktop"}')
    config = {"wallpaper": "", "clock_format": "%A %B %H:%M", "css": ""}
    failures = []
    with patch.dict(os.environ, {"XDG_DATA_DIRS": directory, "GREETD_SOCK": "/must-not-connect"}), \
            patch.object(module, "STATE_FILE", str(Path(directory) / "state.json")), \
            patch.object(module, "save_state", side_effect=AssertionError("Demo wrote state")), \
            patch.object(module.subprocess, "run", side_effect=AssertionError("Demo executed power action")), \
            patch.object(module.GreetdClient, "_connect", side_effect=AssertionError("Demo connected to greetd")):
        application = module.NeogreetApp(is_demo=True, config=config)
        stages = [0]

        def exercise():
            try:
                window = application.get_active_window()
                if window is None or window.busy:
                    return GLib.SOURCE_CONTINUE
                if stages[0] == 0:
                    application.activate()
                    assert application.get_windows() == [window]
                    assert window.user_entry.get_text() == "demo"
                    assert window.get_focus() is window.pass_entry.get_delegate()
                    window.on_reboot(None)
                    window.on_poweroff(None)
                    assert window.pass_entry.get_visible() and window.pass_entry.get_sensitive()
                    window.user_entry.set_text("demo")
                    window.client.request = Mock(wraps=window.client.request)
                    window.user_entry.emit("activate")
                    assert window.get_focus() is window.pass_entry.get_delegate()
                    for _ in range(100):
                        window.pass_entry.emit("activate")
                        window.on_cancel(None)
                    window.client.request.assert_not_called()
                    assert not window.auth_active and not window.cancel_btn.get_visible()
                    window.pass_entry.set_text("wrong")
                    window.on_login()
                    stages[0] = 1
                elif stages[0] == 1 and not window.auth_active:
                    assert window.status_label.get_text() == module.tr("invalid_password")
                    assert window.pass_entry.get_text() == "" and window.pending_password is None
                    assert window.pass_entry.get_visible() and window.pass_entry.get_sensitive()
                    assert window.get_focus() is window.pass_entry.get_delegate()
                    window.pass_entry.set_text("demo")
                    window.pass_entry.emit("activate")
                    stages[0] = 2
                elif stages[0] == 2 and window.starting:
                    assert window.pending_password is None
                    requests = [call.args[0] for call in window.client.request.call_args_list]
                    assert [request["type"] for request in requests] == [
                        "create_session", "post_auth_message_response",
                        "create_session", "post_auth_message_response", "start_session"]
                    assert requests[1]["response"] == "wrong" and requests[3]["response"] == "demo"
                    stages[0] = 3
                    return GLib.SOURCE_REMOVE
                return GLib.SOURCE_CONTINUE
            except Exception as error:
                failures.append(error)
                application.quit()
                return GLib.SOURCE_REMOVE

        def timeout():
            failures.append(AssertionError("GTK smoke test timed out"))
            application.quit()
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(50, exercise)
        watchdog = GLib.timeout_add_seconds(10, timeout)
        application.run(["neogreet-smoke"])
        GLib.source_remove(watchdog)
        assert not failures, failures
        assert stages[0] == 3, stages
        print("GTK smoke passed: empty form sends nothing; username focus, single-submit login and retry")
