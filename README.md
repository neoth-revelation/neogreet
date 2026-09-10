<div align="center">

# 🌙 neogreet

**A sleek, modern Catppuccin Mocha greeter for `greetd` on Wayland.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![GTK: 4.8+](https://img.shields.io/badge/GTK-4.8+-green.svg)](https://www.gtk.org/)
[![Compositor: Wayland](https://img.shields.io/badge/compositor-Wayland-orange.svg)](https://wayland.freedesktop.org/)

<br />

<img src="assets/preview.png" alt="neogreet Main Screen" width="850" />

<br />

*Session Selector Popover:*

<img src="assets/session-menu.png" alt="neogreet Session Selector" width="380" />

</div>

---

## ✨ Features

- **🎨 Catppuccin Mocha Aesthetic**: Designed from the ground up to match modern Rofi & Waybar aesthetics with deep translucent backgrounds (`#1e1e2eee`), subtle borders, and glowing lavender-to-pink gradients (`#cba6f7` → `#f5c2e7`).
- **🔑 Clean, Integrated Inputs**:
  - Primary user icon embedded directly inside the username field.
  - Key icon embedded directly inside the password field, alongside a peek toggle eye icon.
  - Full-width action button matching input field dimensions.
  - Initial focus on the username (or Log In for the remembered user).
  - Interactive PAM questions: each password, OTP or other question sent by greetd is answered individually, never guessed or reused. Expired-password changes require backend support; see the authentication notes below.
- **⚡ Asynchronous & Non-Blocking**:
  - One IPC request at a time runs on a background worker; repeated Enter presses cannot overlap transactions.
  - Short-read-safe protocol, bounded frame sizes and a 60-second socket timeout.
- **🎛️ Bottom-Left Session Selector**:
  - Unobtrusive circular icon button in the lower-left corner.
  - Scans Wayland sessions in `XDG_DATA_DIRS` (default `/usr/local/share:/usr/share`). Honors hidden entries, `TryExec`, localized names and supported `Exec` field codes.
  - Automatically remembers your last selected session across reboots.
- **⏻ Quick Power Controls**:
  - Circular **Reboot** and **Power Off** buttons neatly positioned in the upper-right corner with soft hover glows.
  - Confirmation dialog, asynchronous execution and error feedback; does not bypass systemd inhibitors.
- **🧪 Built-in Demo Mode (`--demo`)**:
  - Test and preview the greeter directly inside your active desktop environment without locking the screen or restarting `greetd`.
  - Press `ESC` to exit demo mode cleanly.
  - Never connects to `greetd`, executes power actions or writes remembered state, even when `GREETD_SOCK` is present.
  - Uses a separate application identity; multiple demo previews run independently of each other and the production greeter.
- **🌐 Automatic Localization (i18n)**:
  - Detects system language and locale (`$LANG`, `$LC_MESSAGES`, `$LC_TIME`).
  - Native clock formatting and translated UI strings (English default for international users, Polish supported out-of-the-box, lightweight dictionary design for easy community contributions).
- **🪶 Ultra Lightweight**:
  - Pure Python 3 + GTK4 (`python-gobject`).
  - Zero heavy rust compilation steps, zero Electron/Node overhead, zero pip dependencies.
  - Communicates directly with the `greetd` UNIX socket (`$GREETD_SOCK`) using standard library modules (`socket`, `struct`, `json`).

---

## 📦 Requirements

- **Linux** with Wayland
- **[`greetd`](https://git.sr.ht/~kennylevinsen/greetd)**
- **`python`** (>= 3.10)
- **`python-gobject`** (PyGObject with GTK4)
- **`gtk4`** (>= 4.8)
- Optional: **`papirus-icon-theme`** and **`ttf-jetbrains-mono-nerd`** for the screenshot styling
- Any lightweight Wayland compositor to host the greeter (e.g. **Hyprland**, **Sway**, or **Cage**).

---

## 🚀 Installation

### Arch Linux (Manual / PKGBUILD)

```bash
git clone https://github.com/neoth-revelation/neogreet.git
cd neogreet
makepkg -si
```

Run from a complete checkout with Arch's `base-devel` installed. This is a
checkout-local PKGBUILD: `file://` sources explicitly locate files in `bin/`
and `examples/`, with independently maintained checksums for their contents.
Downloaded filenames include the actual content hash so rebuilding after an edit
or update cannot reuse a stale source copy. It is not a standalone AUR
PKGBUILD or a portable source-only package; those should use a tagged archive.
After editing packaged files, regenerate checksums with `updpkgsums` (pacman-contrib).
Example configurations are installed under `/usr/share/doc/neogreet/`.
Installation does **not** enable/restart greetd or overwrite `/etc/greetd/`.

### Manual Install (Any Distribution)

```bash
git clone https://github.com/neoth-revelation/neogreet.git
cd neogreet
sudo install -m 755 bin/neogreet /usr/local/bin/neogreet
```

---

## ⚙️ Configuration

Keep a working TTY login and a backup of your display-manager configuration
before switching greeters. Test with `--demo` first. Do not run this application
as root, and do not use it as a session lock screen.

### 1. Configure `greetd` (`/etc/greetd/config.toml`)

Configure `greetd` to launch your chosen Wayland compositor running as the `greeter` user:

```toml
[terminal]
vt = 1

[default_session]
command = "Hyprland --config /etc/greetd/hyprland.conf"
user = "greeter"
```

### 2. Configure Compositor (`/etc/greetd/hyprland.conf`)

An example minimal Hyprland configuration for `greetd`:

```ini
cursor {
    no_hardware_cursors = true
}

input {
    kb_layout = pl
    follow_mouse = 1
}

general {
    border_size = 0
    gaps_in = 0
    gaps_out = 0
}

decoration {
    rounding = 0
    shadow {
        enabled = false
    }
    blur {
        enabled = false
    }
}

animations {
    enabled = false
}

misc {
    disable_hyprland_logo = true
    disable_splash_rendering = true
}

# Request fullscreen; monitor selection is compositor-specific.
windowrule = match:class ^(apps\.neoth\.neogreet|neogreet)$, fullscreen on

# Optional wallpaper on other displays (install your own readable image first):
# exec-once = swaybg -i /usr/share/backgrounds/greeter.png -m fill
exec-once = neogreet; hyprctl dispatch exit
```

`kb_layout = pl` is an example; set your actual keyboard layout. The fullscreen
rule does not select a primary monitor. Configure monitor placement in your
compositor as needed. The greeter has one interactive window, not one per display.

### 3. Optional appearance (`/etc/greetd/neogreet.conf`)

This is an **INI** file for neogreet, separate from greetd's TOML configuration.
Use `examples/neogreet.conf` as a starting point:

```ini
[appearance]
wallpaper = /usr/share/backgrounds/greeter.png
clock_format = %A, %d %B %H:%M
css =
```

No wallpaper is bundled. Install your own image at the chosen path and ensure
the `greeter` account can read it (including parent directories). An absent or
empty wallpaper uses a solid Catppuccin background, so a fresh installation does
not require an image. `css` optionally points to a trusted local GTK4 stylesheet;
the built-in theme remains the default. Preview another config without modifying
system files with `neogreet --demo --config /path/to/neogreet.conf`.
Configuration must be UTF-8; unreadable or invalid files use the defaults and
produce a warning.

### Authentication and state

Enter a username and select Log In; then answer each PAM question with Continue
or Enter. Hidden and visible questions use the visibility requested by PAM.
Informational messages and PAM error notices remain visible until you select
Continue or press Enter; they are acknowledged with a null response. For example,
acknowledge a fingerprint instruction before the backend continues with its scan.
Cancel is available while waiting for your input or acknowledgement. In-flight
socket operations have a 60-second timeout; this is not a deadline for the entire
authentication conversation.

Actual PAM capabilities depend on greetd and the host's PAM configuration.
The UI can answer successive new-password questions if greetd sends them, but
greetd 0.10.3 does not call `pam_chauthtok` when `pam_acct_mgmt` reports an expired
password. Its ordinary expired-password flow therefore ends in an error, not a
password-change dialog. Adding more UI prompts cannot provide that backend support.
Fingerprint, OTP and any password-change flow need end-to-end testing on the host.

Session entries launch their declared Wayland command. X11 entries are deliberately
not listed: their `Exec` alone does not start an X server. An empty session list
produces an error instead of silently guessing `Hyprland`.
Parsed arguments are quoted for greetd's shell execution, preserving spaces,
empty arguments and literal shell characters. The session request supplies
`XDG_SESSION_TYPE=wayland` and, when `DesktopNames` is present, the corresponding
`XDG_CURRENT_DESKTOP` and `XDG_SESSION_DESKTOP`. It does not copy the greeter's
Wayland or D-Bus environment into the user session. A successful start request
means greetd accepted the command; the desktop starts only after the greeter exits.

Only the username and stable session file ID are stored under
`$XDG_CACHE_HOME/neogreet/state.json` (default `~/.cache/neogreet/state.json`),
using atomic replacement and mode 0600. This is the **greeter account's** cache,
not the logged-in user's. Ensure that account has a writable cache directory;
otherwise login still works but state is not persisted and a warning is logged.
Do not weaken permissions on user home directories to achieve this.
Empty or relative XDG cache paths use the default. Session discovery ignores
relative data directories and uses the standard defaults if none remain.

Power actions require the permissions normally provided by logind/polkit for
the active greeter session. Failures are displayed; no passwordless sudo rule or
blanket polkit authorization is installed. Inspect `journalctl -u greetd -b` when
diagnosing startup, cache or power problems. Credentials are never logged.

---

## 🧪 Interactive Demo Mode

Test `neogreet` anytime from your active terminal:

```bash
neogreet --demo
# or shorter:
neogreet -d
```

- Spawns in a floating 1280x720 window.
- Safe power buttons (simulates reboot/shutdown without affecting your machine).
- Select a session and enter a username; click Log In, then answer the simulated password question. Any password succeeds except `wrong`.
- Press `ESC` to close the window.

---

## Tests

```bash
python -m unittest discover -s tests -v
python -m py_compile bin/neogreet
# On a GTK4 host with Xvfb and a session bus:
dbus-run-session -- xvfb-run -a python tests/gtk_smoke.py
dbus-run-session -- xvfb-run -a python tests/gtk_auth_flow.py
dbus-run-session -- xvfb-run -a python tests/gtk_activation.py
# On Arch, as a regular user with base-devel and python (no installation):
python tests/package_smoke.py
```

Headless tests cover protocol framing, explicit demo isolation, malformed state,
session filtering, Desktop Entry locale matching, XDG defaults, invalid config
encoding and the authentication UI state machine. A harmless argument-printing
program checks the parsed Exec command through the same shell boundary as greetd.
A local fake UNIX socket exercises fragmented replies and password + OTP exchange;
that test explicitly skips if host policy prohibits sockets. The GTK smoke test
opens a real demo window, checks a failed attempt, retries and exits on success.
Additional GTK tests use scripted replies to exercise notices, multiple questions,
cancellation, repeated submissions and start failures with real worker threads.
Activation tests run independent demos while a harmless Gio application holds the
production D-Bus name. GTK tests call the handlers; they do not synthesize physical
keyboard input or authenticate through PAM.
GitHub Actions also builds the Arch package without installing or enabling greetd,
checks its payload and permissions, rejects a changed source with an old checksum,
and rebuilds from updated sources without clearing the download cache.
These checks do not replace a real Wayland/greetd/PAM login test in a VM or on a
machine with a verified TTY recovery path.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.

---

<div align="center">
Made with ❤️ by <a href="https://github.com/neoth-revelation">neoth-revelation</a>
</div>
