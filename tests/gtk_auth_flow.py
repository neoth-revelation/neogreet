"""Real GTK and worker threads, scripted PAM replies; no greetd or power access."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import sys
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader("neogreet", str(Path(__file__).resolve().parents[1] / "bin/neogreet"))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
from gi.repository import GLib


def question(kind, text):
    return {"type": "auth_message", "auth_message_type": kind, "auth_message": text}


success = {"type": "success"}
password_first = "--interactive" not in sys.argv
conversation = [
    ({"type": "create_session", "username": "fixture"}, question("info", "Notice one")),
    ({"type": "post_auth_message_response", "response": None}, question("secret", "Password")),
    ({"type": "post_auth_message_response", "response": "fixture-Password"}, question("secret", "OTP")),
    ({"type": "post_auth_message_response", "response": "fixture-OTP"}, question("error", "Notice two")),
    ({"type": "post_auth_message_response", "response": None}, question("visible", "Recovery")),
    ({"type": "post_auth_message_response", "response": "fixture-Recovery"}, question("secret", "New password")),
    ({"type": "post_auth_message_response", "response": "fixture-New password"}, question("secret", "Confirm password")),
    ({"type": "post_auth_message_response", "response": "fixture-Confirm password"}, success),
    ({"type": "start_session", "cmd": ["fixture-session"], "env": ["XDG_SESSION_TYPE=wayland"]},
     {"type": "error", "description": "Start failed"}),
    ({"type": "create_session", "username": "fixture"}, question("info", "Cancel notice")),
    ({"type": "cancel_session"}, success),
    ({"type": "create_session", "username": "fixture"}, question("secret", "Retry password")),
    ({"type": "post_auth_message_response", "response": "fixture-final"}, success),
    ({"type": "start_session", "cmd": ["fixture-session"], "env": ["XDG_SESSION_TYPE=wayland"]}, success),
]

with tempfile.TemporaryDirectory() as directory:
    sessions = Path(directory) / "wayland-sessions"
    sessions.mkdir()
    (sessions / "fixture.desktop").write_text("[Desktop Entry]\nName=Fixture\nExec=fixture-session\n")
    failures, requests, callbacks, rendered = [], [], [], set()
    stage = [0]
    gate = threading.Event()
    main_thread = threading.get_ident()
    original_result = module.NeogreetWindow._on_login_result

    def result(window, reply):
        assert threading.get_ident() == main_thread
        callbacks.append(reply)
        return original_result(window, reply)

    def backend(payload):
        try:
            assert threading.get_ident() != main_thread
            expected, reply = conversation[len(requests)]
            requests.append(payload)
            assert payload == expected, (payload, expected)
            if len(requests) == 1:
                assert gate.wait(3), "Initial request was not released"
            return reply
        except Exception as error:
            failures.append(error)
            return {"type": "error", "description": "Test backend failed"}

    def tick(window, _clock):
        rendered.add(window.status_label.get_text())
        return GLib.SOURCE_CONTINUE

    def exercise():
        try:
            window = application.get_active_window()
            if window is None or window.busy:
                return GLib.SOURCE_CONTINUE
            if stage[0] == 0:
                window.client.request = backend
                window.add_tick_callback(tick)
                window.user_entry.set_text("fixture")
                if password_first:
                    window.pass_entry.set_text("fixture-Password")
                window.on_login()
                for _ in range(100):
                    window.on_login()
                    window.on_cancel(None)
                gate.set()
                stage[0] = 1
            elif stage[0] == 1:
                if window.awaiting_response:
                    prompt = window.status_label.get_text()
                    if prompt not in rendered:
                        return GLib.SOURCE_CONTINUE
                    assert window.pass_entry.get_text() == ""
                    assert window.pass_entry.get_visibility() == (window.prompt_kind == "visible")
                    if window.prompt_kind in ("secret", "visible"):
                        window.pass_entry.set_text("fixture-" + prompt)
                    window.on_login()
                    for _ in range(100):
                        window.on_login()
                elif not window.auth_active:
                    assert window.status_label.get_text() == "Start failed"
                    assert window.user_entry.get_sensitive() and window.session_btn.get_sensitive()
                    if password_first:
                        window.pass_entry.set_text("cancel-fixture")
                    window.on_login()
                    stage[0] = 2
            elif stage[0] == 2 and window.awaiting_response:
                window.on_cancel(None)
                stage[0] = 3
            elif stage[0] == 3 and not window.auth_active:
                assert window.pass_entry.get_text() == ""
                assert window.pending_password is None
                if password_first:
                    window.pass_entry.set_text("must-not-answer-unknown-prompt")
                window.on_login()
                stage[0] = 4
            elif stage[0] == 4 and window.awaiting_response:
                window.pass_entry.set_text("fixture-final")
                window.on_login()
                stage[0] = 5
            return GLib.SOURCE_CONTINUE
        except Exception as error:
            failures.append(error)
            application.quit()
            return GLib.SOURCE_REMOVE

    def timeout():
        failures.append(AssertionError("GTK conversation timed out"))
        gate.set()
        application.quit()
        return GLib.SOURCE_REMOVE

    with patch.dict(os.environ, {"XDG_DATA_DIRS": directory, "GREETD_SOCK": "/must-not-connect"}), \
            patch.object(module, "STATE_FILE", str(Path(directory) / "state.json")), \
            patch.object(module, "save_state", side_effect=AssertionError("Demo wrote state")), \
            patch.object(module.subprocess, "run", side_effect=AssertionError("Power action executed")), \
            patch.object(module.GreetdClient, "_connect", side_effect=AssertionError("Connected to greetd")), \
            patch.object(module.NeogreetWindow, "_on_login_result", result):
        application = module.NeogreetApp(is_demo=True, config={"wallpaper": "", "clock_format": "%H:%M", "css": "",
                                                              "password_first": password_first})
        GLib.timeout_add(50, exercise)
        watchdog = GLib.timeout_add_seconds(10, timeout)
        application.run(["neogreet-conversation"])
        GLib.source_remove(watchdog)
    assert not failures, failures
    assert len(requests) == len(callbacks) == len(conversation)
    assert {"Notice one", "Notice two"} <= rendered
    assert stage[0] == 5
    print(f"GTK conversation passed (password_first={password_first}): notices, multiple prompts, Enter, cancellation, start failure and retry")
