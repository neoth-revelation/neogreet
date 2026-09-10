"""Headless regression tests: no PAM, root, real power actions or GTK required."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
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

    def test_exec_expansion(self):
        self.assertEqual(app.session_command('session "two words" %U %c %k %% %i', "My session", "/a.desktop", "icon"),
                         ["session", "two words", "My session", "/a.desktop", "%", "--icon", "icon"])
        with self.assertRaises(ValueError):
            app.session_command("session %Q", "name", "file")
        with self.assertRaises(ValueError):
            app.session_command('session "broken', "name", "file")

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
            with patch.object(app, "CURRENT_LANG", "pl"), patch.object(app.shutil, "which", return_value=None):
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
    def window(self):
        # Bind production state-machine methods to a display-free test harness.
        window = types.SimpleNamespace(busy=False, auth_active=False, awaiting_response=False,
                                       starting=False, cancelling=False, is_demo=False)
        for name in ("on_login", "_on_login_result", "on_cancel", "reset_auth", "show_error"):
            setattr(window, name, types.MethodType(getattr(app.NeogreetWindow, name), window))
        for name in ("user_entry", "pass_entry", "login_btn", "cancel_btn", "session_btn",
                     "session_popover", "status_label"):
            setattr(window, name, Mock())
        window.user_entry.get_text.return_value = "alice"
        window.selected_session = {"name": "Session", "cmd": ["session"], "id": "session.desktop"}
        window.send_request = Mock()
        return window

    def test_repeated_enter_is_ignored(self):
        window = self.window()
        window.busy = True
        window.on_login()
        window.send_request.assert_not_called()

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
            window._on_login_result({"type": "auth_message", "auth_message_type": kind, "auth_message": "PAM notice"})
            window.status_label.set_text.assert_called_with("PAM notice")
            window.send_request.assert_called_with({"type": "post_auth_message_response", "response": None})

    def test_cancel_and_retry(self):
        window = self.window()
        window.on_login()
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
        window.on_login()
        window.selected_session = {"cmd": ["other"]}
        window._on_login_result({"type": "success"})
        window.send_request.assert_called_with({"type": "start_session", "cmd": ["session"], "env": []})

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
