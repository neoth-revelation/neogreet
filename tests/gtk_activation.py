"""Demo activation isolation on a private session bus. Never starts a real greeter."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
from unittest.mock import patch

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]


def preview(directory, name):
    loader = importlib.machinery.SourceFileLoader("neogreet", str(ROOT / "bin/neogreet"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    application = module.NeogreetApp(is_demo=True, config={"wallpaper": "", "clock_format": name, "css": ""})
    failures = []
    checked = [False]

    def exercise():
        try:
            if not checked[0]:
                window = application.get_active_window()
                assert window is not None and window.is_demo
                if window.get_focus() is not window.user_entry.get_delegate():
                    return GLib.SOURCE_CONTINUE
                assert not application.get_is_remote()
                assert window.clock_label.get_text() == name
                assert window.pass_entry.get_visible()
                assert window.get_focus() is window.user_entry.get_delegate()
                application.activate()
                assert application.get_windows() == [window]
                Path(directory, name).touch()
                checked[0] = True
            # Both processes must own and show their own demo window.
            if all(Path(directory, label).exists() for label in ("First", "Second")):
                application.quit()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        except Exception as error:
            traceback.print_exc()
            failures.append(error)
            application.quit()
            return GLib.SOURCE_REMOVE

    def timeout():
        failures.append(AssertionError("Independent demo window did not appear"))
        application.quit()
        return GLib.SOURCE_REMOVE

    with patch.object(module.GreetdClient, "_connect", side_effect=AssertionError("Connected to greetd")), \
            patch.object(module, "save_state", side_effect=AssertionError("Demo wrote state")):
        GLib.timeout_add(100, exercise)
        watchdog = GLib.timeout_add_seconds(7, timeout)
        application.run(["demo-activation-test"])
        GLib.source_remove(watchdog)
    assert checked[0] and not failures, failures


def parent():
    # Claim only the production D-Bus name with a harmless Gio application.
    primary = Gio.Application(application_id="apps.neoth.neogreet")
    activations = []
    primary.connect("activate", lambda _: activations.append(True))
    primary.register(None)
    assert not primary.get_is_remote(), "Run on a private D-Bus session"
    loop = GLib.MainLoop()
    with tempfile.TemporaryDirectory() as directory:
        environment = dict(os.environ, GREETD_SOCK="/must-not-connect", XDG_CACHE_HOME=directory)
        children = [subprocess.Popen([sys.executable, "-B", __file__, directory, name], env=environment,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for name in ("First", "Second")]

        def poll():
            if all(child.poll() is not None for child in children):
                loop.quit()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        def timeout():
            loop.quit()
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(50, poll)
        GLib.timeout_add_seconds(10, timeout)
        try:
            loop.run()
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
            results = [(child.communicate(timeout=3), child.returncode) for child in children]
        assert not activations, "Demo activated the production application"
        assert all(code == 0 for _, code in results), results
        assert all(Path(directory, name).exists() for name in ("First", "Second"))
    print("GTK activation passed: independent demos, no production activation, one window per application")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        preview(*sys.argv[1:])
    else:
        parent()
