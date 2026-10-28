"""Device integration: native notifications, clipboard, browser, and a login background agent.

macOS first (osascript, pbcopy, launchd); Linux fallbacks (notify-send, wl-copy/xclip, systemd --user).
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

HOME = Path(os.environ.get("KEPLER_HOME", Path.home() / ".kepler"))
AGENT_LABEL = "com.kepler.agent"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def _run(cmd: list[str], data: str | None = None) -> bool:
    try:
        subprocess.run(cmd, input=data, text=True, capture_output=True, timeout=5, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _osa_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(title: str, message: str, subtitle: str = "", sound: bool = True) -> bool:
    """Native desktop notification. Returns False when no notifier is available."""
    if os.environ.get("KEPLER_NO_NOTIFY"):
        return False
    if IS_MAC:
        script = f"display notification {_osa_str(message)} with title {_osa_str(title)}"
        if subtitle:
            script += f" subtitle {_osa_str(subtitle)}"
        if sound:
            script += ' sound name "Submarine"'
        return _run(["osascript", "-e", script])
    if IS_LINUX and shutil.which("notify-send"):
        return _run(["notify-send", "-a", "Kepler", title, f"{subtitle}\n{message}".strip()])
    return False


def copy(text: str) -> bool:
    """Put text on the system clipboard."""
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["clip.exe"]):
        if shutil.which(cmd[0]):
            return _run(cmd, data=text)
    return False


def open_url(url: str) -> bool:
    return webbrowser.open(url)


# ---------------------------------------------------------------- background agent

def _kepler_cmd() -> list[str]:
    return [sys.executable, "-m", "kepler.cli", "agent", "run"]


def agent_plist(url: str, min_severity: str = "high") -> str:
    from xml.sax.saxutils import escape
    args = "".join(f"\n      <string>{escape(a)}</string>" for a in _kepler_cmd() + ["--url", url, "--min-severity", min_severity])
    log = escape(str(HOME / "agent.log"))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>{AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>{args}
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>ThrottleInterval</key><integer>30</integer>
    <key>StandardOutPath</key><string>{log}</string>
    <key>StandardErrorPath</key><string>{log}</string>
  </dict>
</plist>
"""


def systemd_unit(url: str, min_severity: str = "high") -> str:
    cmd = " ".join(_kepler_cmd() + ["--url", url, "--min-severity", min_severity])
    return f"""[Unit]
Description=Kepler background watcher

[Service]
ExecStart={cmd}
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
"""


def agent_paths() -> Path:
    if IS_MAC:
        return Path.home() / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"
    return Path.home() / ".config" / "systemd" / "user" / "kepler-agent.service"


def agent_install(url: str, min_severity: str = "high") -> str:
    HOME.mkdir(parents=True, exist_ok=True)
    path = agent_paths()
    path.parent.mkdir(parents=True, exist_ok=True)
    if IS_MAC:
        path.write_text(agent_plist(url, min_severity))
        uid = os.getuid()
        _run(["launchctl", "bootout", f"gui/{uid}", str(path)])
        ok = _run(["launchctl", "bootstrap", f"gui/{uid}", str(path)])
        return f"installed {path} ({'running' if ok else 'written; load it with: launchctl bootstrap gui/' + str(uid) + ' ' + str(path)})"
    if IS_LINUX:
        path.write_text(systemd_unit(url, min_severity))
        _run(["systemctl", "--user", "daemon-reload"])
        ok = _run(["systemctl", "--user", "enable", "--now", "kepler-agent.service"])
        return f"installed {path} ({'running' if ok else 'written; start it with: systemctl --user enable --now kepler-agent'})"
    raise RuntimeError("background agent is supported on macOS and Linux")


def agent_uninstall() -> str:
    path = agent_paths()
    if IS_MAC:
        _run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)])
    elif IS_LINUX:
        _run(["systemctl", "--user", "disable", "--now", "kepler-agent.service"])
    if path.exists():
        path.unlink()
        return f"removed {path}"
    return "agent was not installed"


def agent_status() -> dict:
    path = agent_paths()
    running = False
    if IS_MAC and path.exists():
        running = _run(["launchctl", "print", f"gui/{os.getuid()}/{AGENT_LABEL}"])
    elif IS_LINUX and path.exists():
        running = _run(["systemctl", "--user", "is-active", "--quiet", "kepler-agent.service"])
    return {"installed": path.exists(), "running": running, "path": str(path), "log": str(HOME / "agent.log")}


# ---------------------------------------------------------------- small persistent state for the agent / TUI

def load_state(name: str) -> dict:
    try:
        return json.loads((HOME / f"{name}.json").read_text())
    except (OSError, ValueError):
        return {}


def save_state(name: str, data: dict):
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / f"{name}.json").write_text(json.dumps(data))
