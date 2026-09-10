"""Build and inspect an Arch package in a temporary copy; never install it."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def makepkg(directory, *args, succeeds=True):
    environment = dict(os.environ, LC_ALL="C", BUILDDIR=str(directory), SRCDEST=str(directory),
                       PKGDEST=str(directory), SRCPKGDEST=str(directory), LOGDEST=str(directory))
    result = subprocess.run(["makepkg", "--nodeps", "--noconfirm", *args], cwd=directory,
                            env=environment, capture_output=True, text=True, timeout=120)
    if (result.returncode == 0) != succeeds:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def inspect_package(directory):
    archive, = directory.glob("neogreet-*.pkg.tar.*")
    listing = subprocess.check_output(["bsdtar", "-tf", str(archive)], text=True).splitlines()
    payload = {path for path in listing if not path.endswith("/") and not path.startswith(".")}
    expected = {"usr/bin/neogreet", "usr/share/licenses/neogreet/LICENSE",
                "usr/share/doc/neogreet/neogreet.conf", "usr/share/doc/neogreet/config.toml",
                "usr/share/doc/neogreet/hyprland.conf"}
    assert payload == expected, payload
    assert ".INSTALL" not in listing
    executable = subprocess.check_output(["bsdtar", "-xOf", str(archive), "usr/bin/neogreet"])
    assert executable == (directory / "bin/neogreet").read_bytes()
    metadata = subprocess.check_output(["bsdtar", "-xOf", str(archive), ".PKGINFO"], text=True)
    for dependency in ("greetd", "python", "python-gobject", "gtk4>=4.8"):
        assert f"depend = {dependency}\n" in metadata
    extracted = directory / "inspection"
    extracted.mkdir(exist_ok=True)
    subprocess.run(["bsdtar", "-xf", str(archive), "-C", str(extracted), "usr/bin/neogreet"], check=True)
    assert (extracted / "usr/bin/neogreet").stat().st_mode & 0o777 == 0o755


if __name__ == "__main__":
    if os.geteuid() == 0:
        raise SystemExit("Run this test as an unprivileged build user")
    with tempfile.TemporaryDirectory(prefix="neogreet-package-") as temporary:
        # Check file:// URL handling as well as stale makepkg downloads.
        directory = Path(temporary) / "checkout with spaces # [test]"
        directory.mkdir()
        for name in ("PKGBUILD", "LICENSE"):
            shutil.copy2(ROOT / name, directory / name)
        for name in ("bin", "examples"):
            shutil.copytree(ROOT / name, directory / name)
        makepkg(directory)
        inspect_package(directory)
        source = directory / "bin/neogreet"
        old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        source.write_bytes(source.read_bytes() + b"\n# Package update test fixture.\n")
        # A changed source without an updated expected checksum must still fail.
        output = makepkg(directory, "--force", succeeds=False)
        assert "validity check" in output, output
        new_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        pkgbuild = directory / "PKGBUILD"
        pkgbuild.write_text(pkgbuild.read_text().replace(old_hash, new_hash))
        makepkg(directory, "--force")
        inspect_package(directory)
    print("Package tests passed: contents, permissions, checksum enforcement and rebuild after source update")
