#!/usr/bin/env python3
"""Create a desktop shortcut that launches the HoloVision Ops Center.

Cross-platform:
  * Linux   -> ~/.local/share/applications/*.desktop  (+ a copy on ~/Desktop)
  * macOS   -> ~/Desktop/HoloVision Ops Center.command (double-clickable)
  * Windows -> Desktop\\HoloVision Ops Center.lnk       (via PowerShell)

Run once:  python3 make_shortcut.py
Remove:    python3 make_shortcut.py --remove
"""

from __future__ import annotations

import argparse
import os
import platform
import stat
import subprocess
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SERVER = HERE / "server.py"
NAME = "HoloVision Ops Center"


def desktop_dir() -> pathlib.Path:
    # Honour XDG on Linux; fall back to ~/Desktop everywhere.
    d = pathlib.Path.home() / "Desktop"
    xdg = os.environ.get("XDG_DESKTOP_DIR")
    if xdg:
        d = pathlib.Path(os.path.expandvars(xdg))
    return d


def _linux(remove: bool) -> list[pathlib.Path]:
    apps = pathlib.Path.home() / ".local/share/applications"
    apps.mkdir(parents=True, exist_ok=True)
    targets = [apps / "holovision-ops.desktop", desktop_dir() / "holovision-ops.desktop"]
    if remove:
        for t in targets:
            t.unlink(missing_ok=True)
        return targets
    content = f"""[Desktop Entry]
Type=Application
Name={NAME}
Comment=Local-first cross-protocol LAN operations center
Exec={sys.executable} {SERVER}
Path={HERE}
Terminal=true
Categories=Network;System;Utility;
"""
    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(content, encoding="utf-8")
        t.chmod(t.stat().st_mode | stat.S_IEXEC)
    # Mark the desktop copy "trusted" on GNOME if the tool exists.
    subprocess.run(["gio", "set", str(targets[1]), "metadata::trusted", "true"],
                   capture_output=True)
    return targets


def _macos(remove: bool) -> list[pathlib.Path]:
    target = desktop_dir() / f"{NAME}.command"
    if remove:
        target.unlink(missing_ok=True)
        return [target]
    content = f"""#!/bin/bash
cd "{HERE}"
exec "{sys.executable}" "{SERVER}"
"""
    target.write_text(content, encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IEXEC)
    return [target]


def _windows(remove: bool) -> list[pathlib.Path]:
    target = desktop_dir() / f"{NAME}.lnk"
    if remove:
        target.unlink(missing_ok=True)
        return [target]
    pyw = sys.executable
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath='{py}';"
        "$s.Arguments='\"{srv}\"';"
        "$s.WorkingDirectory='{cwd}';"
        "$s.Description='HoloVision Ops Center';"
        "$s.Save()"
    ).format(lnk=target, py=pyw, srv=SERVER, cwd=HERE)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return [target]


def main() -> None:
    ap = argparse.ArgumentParser(description="Create/remove the desktop shortcut")
    ap.add_argument("--remove", action="store_true", help="remove the shortcut instead")
    args = ap.parse_args()

    system = platform.system()
    handler = {"Linux": _linux, "Darwin": _macos, "Windows": _windows}.get(system)
    if not handler:
        sys.exit(f"Unsupported platform: {system}")

    try:
        made = handler(args.remove)
    except (OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"Failed to {'remove' if args.remove else 'create'} shortcut: {exc}")

    verb = "Removed" if args.remove else "Created"
    print(f"{verb} shortcut(s):")
    for m in made:
        print(f"  {m}")
    if not args.remove:
        print("\nDouble-click it to launch the Ops Center; your browser opens at "
              "http://127.0.0.1:8787")
        if system == "Linux":
            print("Tip: on first run your file manager may ask you to 'Allow "
                  "Launching' — accept it once.")


if __name__ == "__main__":
    main()
