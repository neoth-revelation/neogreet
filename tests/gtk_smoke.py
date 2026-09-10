"""Run with xvfb-run -a python3 tests/gtk_smoke.py on a GTK4 host."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader("neogreet", str(Path(__file__).resolve().parents[1] / "bin/neogreet"))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
from gi.repository import GLib

with tempfile.TemporaryDirectory() as directory:
    sessions = Path(directory) / "wayland-sessions"
    sessions.mkdir()
    (sessions / "demo.desktop").write_text("[Desktop Entry]\nName=Demo\nExec=demo-session\n")
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
                    window.on_reboot(None)
                    window.on_poweroff(None)
                    window.user_entry.set_text("demo")
                    window.on_login()
                    stages[0] = 1
                elif stages[0] == 1 and window.awaiting_response:
                    window.pass_entry.set_text("wrong")
                    window.on_login()
                    stages[0] = 2
                elif stages[0] == 2 and not window.auth_active:
                    assert window.status_label.get_text() == module.tr("invalid_password")
                    window.on_login()
                    stages[0] = 3
                elif stages[0] == 3 and window.awaiting_response:
                    window.pass_entry.set_text("demo")
                    window.on_login()
                    stages[0] = 4
                elif stages[0] == 4 and window.starting:
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
        assert stages[0] == 4, stages
        print("GTK smoke test passed (demo: failed login, retry, success)")
