"""Headless regression tests: no PAM, root, real power actions or GTK required."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("neogreet_tested", str(ROOT / "bin/neogreet"))
spec = importlib.util.spec_from_loader(loader.name, loader)
app = importlib.util.module_from_spec(spec)
# Stub only imports/classes; tests below call actual production methods.
gi = types.ModuleType("gi")
gi.require_version = lambda *_: None
repository = types.ModuleType("gi.repository")
repository.Gtk = types.SimpleNamespace(ApplicationWindow=object, Application=object,
                                       EntryIconPosition=types.SimpleNamespace(SECONDARY=1))
repository.Gdk = types.SimpleNamespace()
repository.GLib = types.SimpleNamespace(SOURCE_REMOVE=False)
repository.Gio = types.SimpleNamespace(ApplicationFlags=types.SimpleNamespace(NON_UNIQUE=32, FLAGS_NONE=0))
with patch.dict("sys.modules", {"gi": gi, "gi.repository": repository}):
    loader.exec_module(app)


class ProtocolTests(unittest.TestCase):
    def test_demo_never_connects(self):
        with patch.dict(os.environ, {"GREETD_SOCK": "/real/socket"}), patch.object(app.socket, "socket") as sock:
            client = app.GreetdClient(is_demo=True)
            self.assertEqual(client.request({"type": "create_session"})["type"], "auth_message")
            self.assertEqual(client.request({"type": "post_auth_message_response", "response": "wrong"})["type"], "error")
            self.assertEqual(client.request({"type": "post_auth_message_response", "response": "ok"})["type"], "success")
            sock.assert_not_called()

    def test_environment_cannot_enable_demo(self):
        with patch.dict(os.environ, {"NEOGREET_DEMO": "1", "ANTIGRAVITY_GREETER_DEMO": "1"}, clear=True):
            self.assertEqual(app.GreetdClient().request({"type": "create_session"})["type"], "error")

    def test_short_reads(self):
        client = app.GreetdClient()
        client.sock = Mock()
        client.sock.recv.side_effect = [b"a", b"bc", b"d"]
        self.assertEqual(client._recv_exact(4), b"abcd")

    def test_eof_and_invalid_frames(self):
        for chunks in ([b""], [struct.pack("=I", 0)],
                       [struct.pack("=I", app.GreetdClient.MAX_MESSAGE + 1)],
                       [struct.pack("=I", 2), b"[]"],
                       [struct.pack("=I", 2), b"xx"]):
            with self.subTest(chunks=chunks):
                client = app.GreetdClient()
                sock = Mock()
                client.sock = sock
                sock.recv.side_effect = chunks
                self.assertEqual(client.request({"type": "create_session"})["type"], "error")
                self.assertIsNone(client.sock)
                sock.close.assert_called_once()

    def test_socket_timeout(self):
        client = app.GreetdClient()
        client.sock = Mock()
        client.sock.recv.side_effect = socket.timeout()
        self.assertEqual(client.request({"type": "create_session"})["type"], "error")
        self.assertIsNone(client.sock)

    def test_retry_resets_previous_transaction(self):
        client = app.GreetdClient()
        client.sock = Mock()
        replies = [{"type": "error", "error_type": "auth_error", "description": "Denied"},
                   {"type": "success"},
                   {"type": "auth_message", "auth_message_type": "secret", "auth_message": "Password:"}]
        chunks = []
        for reply in replies:
            body = json.dumps(reply).encode()
            chunks.extend([struct.pack("=I", len(body)), body])
        client.sock.recv.side_effect = chunks
        client.request({"type": "create_session", "username": "test"})
        client.request({"type": "create_session", "username": "test"})
        sent = [json.loads(call.args[0][4:]) for call in client.sock.sendall.call_args_list]
        self.assertEqual([item["type"] for item in sent],
                         ["create_session", "cancel_session", "create_session"])

    def test_real_unix_socket_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "greetd.sock")
            try:
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            except PermissionError:
                self.skipTest("Host policy prohibits UNIX sockets; run on Linux or in CI")
            server.bind(path)
            server.listen(1)
            server.settimeout(3)
            requests = []
            failures = []
            replies = [
                {"type": "auth_message", "auth_message_type": "secret", "auth_message": "Password:"},
                {"type": "auth_message", "auth_message_type": "secret", "auth_message": "OTP:"},
                {"type": "success"}, {"type": "success"},
            ]

            def read_exact(connection, length):
                data = b""
                while len(data) < length:
                    chunk = connection.recv(length - len(data))
                    if not chunk:
                        raise EOFError()
                    data += chunk
                return data

            def serve():
                try:
                    connection, _ = server.accept()
                    with connection:
                        connection.settimeout(3)
                        for reply in replies:
                            length = struct.unpack("=I", read_exact(connection, 4))[0]
                            requests.append(json.loads(read_exact(connection, length)))
                            body = json.dumps(reply).encode()
                            for byte in struct.pack("=I", len(body)) + body:
                                connection.sendall(bytes([byte]))
                except Exception as exc:
                    failures.append(exc)

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            try:
                with patch.dict(os.environ, {"GREETD_SOCK": path}):
                    client = app.GreetdClient()
                    payloads = [{"type": "create_session", "username": "test"},
                                {"type": "post_auth_message_response", "response": "password-fixture"},
                                {"type": "post_auth_message_response", "response": "123456"},
                                {"type": "start_session", "cmd": ["Hyprland"], "env": []}]
                    for payload, expected in zip(payloads, replies):
                        self.assertEqual(client.request(payload), expected)
                    client.close()
                thread.join(4)
                self.assertFalse(thread.is_alive())
                self.assertEqual(failures, [])
                self.assertEqual(requests, payloads)
            finally:
                server.close()


class StateAndSessionTests(unittest.TestCase):
    def test_corrupt_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            with patch.object(app, "STATE_FILE", str(path)):
                for content in ("{broken", "[]", '{"last_user": 42}'):
                    path.write_text(content)
                    self.assertEqual(app.load_state()["last_user"], "")
                app.save_state("alice", "hyprland.desktop")
                self.assertEqual(app.load_state()["last_session"], "hyprland.desktop")
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_locale_precedence(self):
        for env, expected in (({"LC_ALL": "C", "LANG": "pl_PL.UTF-8"}, "en"),
                              ({"LC_MESSAGES": "pl_PL.UTF-8", "LANG": "en_US.UTF-8"}, "pl"),
                              ({"LANG": "fr_FR.UTF-8"}, "en")):
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(app.detect_language(), expected)

    def test_config_percent_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config"
            path.write_text("[appearance]\nwallpaper =\nclock_format = %H:%M\n")
            self.assertEqual(app.load_config(path)["clock_format"], "%H:%M")
            self.assertEqual(app.load_config(path)["wallpaper"], "")
            self.assertEqual(app.load_config(path.with_name("missing"))["css"], "")

    def test_config_invalid_encoding_uses_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config"
            path.write_bytes(b"[appearance]\nwallpaper=\xff\n")
            with self.assertLogs("neogreet", level="WARNING"):
                self.assertEqual(app.load_config(path), app.load_config(path.with_name("missing")))

    def test_password_first_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config"
            self.assertTrue(app.load_config(path)["password_first"])
            path.write_text("[authentication]\npassword_first = false\n")
            self.assertFalse(app.load_config(path)["password_first"])
            path.write_text("[authentication]\npassword_first = invalid\n")
            with self.assertLogs("neogreet", level="WARNING"):
                self.assertTrue(app.load_config(path)["password_first"])

    def test_xdg_empty_and_relative_values_use_defaults(self):
        for value in (None, "", "relative/path"):
            env = {} if value is None else {"XDG_DATA_DIRS": value, "XDG_CACHE_HOME": value}
            with self.subTest(value=value), patch.dict(os.environ, env, clear=True):
                self.assertEqual(app.session_search_paths(),
                                 ["/usr/local/share/wayland-sessions", "/usr/share/wayland-sessions"])
                self.assertEqual(app.state_file_path(), os.path.expanduser("~/.cache/neogreet/state.json"))
        with patch.dict(os.environ, {"XDG_DATA_DIRS": "relative:/opt/sessions::/usr/share",
                                     "XDG_CACHE_HOME": "/tmp/test-cache"}):
            self.assertEqual(app.session_search_paths(),
                             ["/opt/sessions/wayland-sessions", "/usr/share/wayland-sessions"])
            self.assertEqual(app.state_file_path(), "/tmp/test-cache/neogreet/state.json")

    def test_desktop_locale_independent_of_ui_language(self):
        entry = {"Name": "Default", "Name[pl]": "Polski", "Name[pl_PL]": "Regional",
                 "Name[fr]": "Francais", "Name[sr_YU@Latn]": "Full",
                 "Name[sr_YU]": "Country", "Name[sr@Latn]": "Modifier", "Name[sr]": "Language"}
        for value, expected in (("pl_PL.UTF-8", "Regional"), ("fr_FR.UTF-8", "Francais"),
                                ("C", "Default"), ("sr_YU.UTF-8@Latn", "Full"),
                                ("sr_YU@Other", "Country"), ("sr_RS@Latn", "Modifier"),
                                ("sr_RS", "Language")):
            with self.subTest(locale=value), patch.dict(os.environ, {"LC_ALL": value}):
                self.assertEqual(app.localized_value(entry, "Name"), expected)

    def test_desktop_string_escaping(self):
        with patch.dict(os.environ, {"LC_ALL": "C"}):
            self.assertEqual(app.localized_value({"Name": r"My\sSession"}, "Name"), "My Session")

    def test_exec_expansion(self):
        self.assertEqual(app.session_command('session "two words" %U %c %k %% %i', "My session", "/a.desktop", "icon"),
                         ["session", "two words", "My session", "/a.desktop", "%", "--icon", "icon"])
        with self.assertRaises(ValueError):
            app.session_command("session %Q", "name", "file")
        with self.assertRaises(ValueError):
            app.session_command('session "broken', "name", "file")

    def test_exec_quoted_escapes_and_empty_arguments(self):
        cases = [(r'session "\\$literal"', ["session", "$literal"]),
                 (r'session "\\`literal"', ["session", "`literal"]),
                 (r'session "a\\\\b"', ["session", "a\\b"]),
                 (r'session "a\\"b" ""', ["session", 'a"b', ""]),
                 ('session "two words" "*"', ["session", "two words", "*"])]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(app.session_command(value, "name", "file"), expected)

    def test_exec_survives_greetd_shell_execution(self):
        # Match greetd's real cmd.join(" ") -> /bin/sh -c boundary, without PAM.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe = root / "argument probe"
            probe.write_text("#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
            probe.chmod(0o755)
            desktop = root / "session with spaces.desktop"
            name = "My $(printf expanded) Session"
            desktop.write_text('[Desktop Entry]\nType=Application\nName=' + name +
                               '\nExec="' + str(probe) + '" "two words" "" "*" %c %k %i %%\n'
                               'Icon=fixture-icon\nDesktopNames=Hyprland;wlroots;\n')
            with patch.dict(os.environ, {"LC_ALL": "C"}):
                _, session = app.scan_sessions(search_paths=[directory])
            request = app.session_start_request(session)
            result = subprocess.run(["/bin/sh", "-c", "exec " + " ".join(request["cmd"])],
                                    cwd=directory, capture_output=True, text=True, check=True, timeout=3)
            self.assertEqual(json.loads(result.stdout),
                             ["two words", "", "*", name, str(desktop), "--icon", "fixture-icon", "%"])
            self.assertEqual(request["env"], ["XDG_SESSION_TYPE=wayland",
                                             "XDG_CURRENT_DESKTOP=Hyprland:wlroots",
                                             "XDG_SESSION_DESKTOP=Hyprland"])

    def test_session_environment_does_not_copy_greeter_environment(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "greeter-wayland", "GREETD_SOCK": "/greeter",
                                     "DBUS_SESSION_BUS_ADDRESS": "greeter-bus", "XDG_CURRENT_DESKTOP": "Wrong"}):
            self.assertEqual(app.session_environment({}), ["XDG_SESSION_TYPE=wayland"])

    def test_session_filters_localization_and_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = {
                "a.desktop": "Name=Same\nName[pl]=Polska\nExec=session %U\n",
                "b.desktop": "Name=Same\nExec=session\n",
                "hidden.desktop": "Name=Hidden\nExec=session\nHidden=true\n",
                "missing.desktop": "Name=Missing\nExec=session\nTryExec=absent\n",
                "action.desktop": "Name=Main\nExec=main\n[Desktop Action Other]\nName=Other\nExec=other\n",
                "broken.desktop": "Name=Broken\nExec=session %Q\n",
            }
            for name, body in fixtures.items():
                (root / name).write_text("[Desktop Entry]\n" + body)
            with patch.dict(os.environ, {"LC_ALL": "pl_PL.UTF-8"}), patch.object(app.shutil, "which", return_value=None):
                sessions, selected = app.scan_sessions("b.desktop", [directory])
                self.assertEqual(len(sessions), 3)
                self.assertEqual(selected["id"], "b.desktop")
                self.assertEqual(sessions[0]["name"], "Polska")
                self.assertEqual(sessions[1]["cmd"], ["main"])

    def test_hidden_override_masks_system_session(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / "local", Path(directory) / "system"]
            for path in paths:
                path.mkdir()
            (paths[0] / "same.desktop").write_text("[Desktop Entry]\nHidden=true\n")
            (paths[1] / "same.desktop").write_text("[Desktop Entry]\nName=Session\nExec=session\n")
            self.assertEqual(app.scan_sessions(search_paths=paths), ([], None))


class UIStateTests(unittest.TestCase):
    def window(self, password_first=False):
        # Bind production state-machine methods to a display-free test harness.
        window = types.SimpleNamespace(busy=False, auth_active=False, awaiting_response=False,
                                       prompt_kind=None, starting=False, cancelling=False, is_demo=False,
                                       password_first=password_first, pending_password=None)
        for name in ("on_login", "on_username_activate", "_on_login_result", "on_cancel", "reset_auth", "show_error"):
            setattr(window, name, types.MethodType(getattr(app.NeogreetWindow, name), window))
        for name in ("user_entry", "pass_entry", "login_btn", "cancel_btn", "session_btn",
                     "session_popover", "status_label"):
            setattr(window, name, Mock())
        window.user_entry.get_text.return_value = "alice"
        window.pass_entry.get_text.return_value = ""
        window.pass_entry.set_text.side_effect = lambda text: setattr(window.pass_entry.get_text, "return_value", text)
        window.selected_session = {"name": "Session", "cmd": ["session"], "id": "session.desktop",
                                   "env": ["XDG_SESSION_TYPE=wayland"]}
        # Preserve the real busy transition while keeping replies under test control.
        window.send_request = Mock(side_effect=lambda _: setattr(window, "busy", True))
        return window

    def test_empty_combined_form_never_starts_authentication(self):
        window = self.window(password_first=True)
        window.user_entry.get_text.return_value = ""
        window.pass_entry.set_text("fixture")
        window.on_login()
        window.user_entry.get_text.return_value = "alice"
        window.pass_entry.set_text("")
        for _ in range(100):
            window.on_username_activate(None)
            window.on_login()
            window.on_cancel(None)
        window.send_request.assert_not_called()
        self.assertFalse(window.auth_active)
        self.assertIsNone(window.pending_password)
        window.pass_entry.grab_focus.assert_called()

    def test_combined_form_answers_password_once_then_waits_for_otp(self):
        for prompt in ("Password: ", "Hasło: ", "Password", "Hasło"):
            with self.subTest(prompt=prompt):
                window = self.window(password_first=True)
                window.pass_entry.set_text("  fixture password  ")
                window.on_username_activate(None)
                window.send_request.assert_not_called()
                window.on_login()
                window.send_request.assert_called_once_with({"type": "create_session", "username": "alice"})
                self.assertEqual(window.pass_entry.get_text(), "")
                window._on_login_result({"type": "auth_message", "auth_message_type": "secret", "auth_message": prompt})
                window.send_request.assert_called_with({"type": "post_auth_message_response", "response": "  fixture password  "})
                self.assertIsNone(window.pending_password)
                for _ in range(100):
                    window.on_login()
                self.assertEqual(window.send_request.call_count, 2)
                for question in ("OTP:", "Password:"):
                    window.send_request.reset_mock()
                    window._on_login_result({"type": "auth_message", "auth_message_type": "secret", "auth_message": question})
                    window.send_request.assert_not_called()
                    self.assertTrue(window.awaiting_response)
                    self.assertEqual(window.pass_entry.get_text(), "")
                    window.pass_entry.set_text("new-answer")
                    window.on_login()
                    window.send_request.assert_called_with({"type": "post_auth_message_response", "response": "new-answer"})

    def test_prefilled_password_is_discarded_for_other_questions(self):
        for kind, prompt in (("secret", "OTP:"), ("visible", "Password:"),
                             ("secret", "Password and OTP:"), ("secret", "New password:"),
                             ("secret", "Custom challenge:"), ("error", "Account notice")):
            with self.subTest(kind=kind, prompt=prompt):
                window = self.window(password_first=True)
                window.pass_entry.set_text("must-not-send")
                window.on_login()
                window.send_request.reset_mock()
                window._on_login_result({"type": "auth_message", "auth_message_type": kind, "auth_message": prompt})
                window.send_request.assert_not_called()
                self.assertIsNone(window.pending_password)
                self.assertEqual(window.pass_entry.get_text(), "")
                window.pass_entry.set_text("manual-answer")
                window.on_login()
                window.send_request.reset_mock()
                window._on_login_result({"type": "auth_message", "auth_message_type": "secret", "auth_message": "Password:"})
                window.send_request.assert_not_called()

    def test_info_before_password_requires_acknowledgement(self):
        window = self.window(password_first=True)
        window.pass_entry.set_text("fixture")
        window.on_login()
        window.send_request.reset_mock()
        window._on_login_result({"type": "auth_message", "auth_message_type": "info", "auth_message": "Notice"})
        window.send_request.assert_not_called()
        window.on_login()
        window.send_request.assert_called_with({"type": "post_auth_message_response", "response": None})
        window._on_login_result({"type": "auth_message", "auth_message_type": "secret", "auth_message": "Password:"})
        window.send_request.assert_called_with({"type": "post_auth_message_response", "response": "fixture"})

    def test_cancel_drops_prefill_and_retry_needs_new_password(self):
        window = self.window(password_first=True)
        window.pass_entry.set_text("fixture")
        window.on_login()
        window._on_login_result({"type": "auth_message", "auth_message_type": "info", "auth_message": "Notice"})
        window.on_cancel(None)
        window.send_request.assert_called_with({"type": "cancel_session"})
        self.assertIsNone(window.pending_password)
        window._on_login_result({"type": "success"})
        window.pass_entry.set_visible.assert_called_with(True)
        window.pass_entry.set_sensitive.assert_called_with(True)
        window.pass_entry.grab_focus.assert_called()
        window.send_request.reset_mock()
        window.on_login()
        window.send_request.assert_not_called()
        window.pass_entry.set_text("retry-fixture")
        window.on_login()
        window.send_request.assert_called_once_with({"type": "create_session", "username": "alice"})

    def test_error_or_success_before_password_clears_prefill(self):
        for reply in ({"type": "error", "description": "Socket closed"}, {"type": "success"}):
            window = self.window(password_first=True)
            window.pass_entry.set_text("fixture")
            window.on_login()
            window._on_login_result(reply)
            self.assertIsNone(window.pending_password)
            self.assertEqual(window.pass_entry.get_text(), "")

    def test_repeated_enter_is_ignored(self):
        window = self.window()
        window.on_login()
        for _ in range(100):
            window.on_login()
        window.send_request.assert_called_once_with({"type": "create_session", "username": "alice"})

    def test_no_fallback_session(self):
        window = self.window()
        window.selected_session = None
        window.on_login()
        window.send_request.assert_not_called()

    def test_multi_prompt_answers_are_not_reused(self):
        window = self.window()
        window.on_login()
        window.send_request.assert_called_with({"type": "create_session", "username": "alice"})
        for kind, question, answer in (("secret", "Password:", "first"),
                                       ("secret", "OTP:", "123456"),
                                       ("visible", "Recovery:", "second"),
                                       ("secret", "New password:", "third")):
            window._on_login_result({"type": "auth_message", "auth_message_type": kind, "auth_message": question})
            window.pass_entry.set_visibility.assert_called_with(kind == "visible")
            window.pass_entry.get_text.return_value = answer
            window.on_login()
            window.send_request.assert_called_with({"type": "post_auth_message_response", "response": answer})

    def test_info_and_error_acknowledgements(self):
        for kind in ("info", "error"):
            window = self.window()
            window.on_login()
            window.send_request.reset_mock()
            window._on_login_result({"type": "auth_message", "auth_message_type": kind, "auth_message": "PAM notice"})
            window.status_label.set_text.assert_called_with("PAM notice")
            window.send_request.assert_not_called()
            self.assertTrue(window.awaiting_response)
            window.pass_entry.set_visible.assert_called_with(False)
            window.on_login()
            window.send_request.assert_called_with({"type": "post_auth_message_response", "response": None})
            window.pass_entry.get_text.assert_not_called()

    def test_cancel_and_retry(self):
        window = self.window()
        window.on_login()
        window._on_login_result({"type": "auth_message", "auth_message_type": "secret", "auth_message": "Password"})
        window.on_cancel(None)
        window.send_request.assert_called_with({"type": "cancel_session"})
        window._on_login_result({"type": "success"})
        self.assertFalse(window.auth_active)
        window.on_login()
        window.send_request.assert_called_with({"type": "create_session", "username": "alice"})

    def test_real_error_is_preserved(self):
        window = self.window()
        window.on_login()
        window._on_login_result({"type": "error", "error_type": "auth_error", "description": "Account locked"})
        window.status_label.set_text.assert_called_with("Account locked")
        self.assertFalse(window.auth_active)

    def test_start_uses_frozen_selection(self):
        window = self.window()
        window.selected_session["cmd"] = ["session", "two words", ""]
        window.on_login()
        window.selected_session["cmd"].append("unexpected")
        window.selected_session["env"].append("UNEXPECTED=1")
        window.selected_session = {"cmd": ["other"]}
        window._on_login_result({"type": "success"})
        window.send_request.assert_called_with({"type": "start_session", "cmd": ["session 'two words' ''"],
                                               "env": ["XDG_SESSION_TYPE=wayland"]})

    def test_start_failure_allows_retry(self):
        window = self.window()
        window.on_login()
        window._on_login_result({"type": "success"})
        self.assertTrue(window.starting)
        window._on_login_result({"type": "error", "description": "Cannot start session"})
        self.assertFalse(window.auth_active)
        self.assertFalse(window.busy)
        window.status_label.set_text.assert_called_with("Cannot start session")
        window.on_login()
        window.send_request.assert_called_with({"type": "create_session", "username": "alice"})

    def test_cancel_information_message(self):
        window = self.window()
        window.on_login()
        window._on_login_result({"type": "auth_message", "auth_message_type": "info", "auth_message": "Notice"})
        window.on_cancel(None)
        window.send_request.assert_called_with({"type": "cancel_session"})
        window._on_login_result({"type": "success"})
        self.assertFalse(window.awaiting_response)
        self.assertIsNone(window.prompt_kind)

    def test_demo_power_buttons_do_not_execute_commands(self):
        window = self.window()
        window.is_demo = True
        window.confirm_power = Mock()
        app.NeogreetWindow.on_reboot(window, None)
        app.NeogreetWindow.on_poweroff(window, None)
        window.confirm_power.assert_not_called()

    def test_busy_cancel_does_not_overlap_request(self):
        window = self.window()
        window.busy = window.auth_active = True
        window.on_cancel(None)
        window.send_request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
