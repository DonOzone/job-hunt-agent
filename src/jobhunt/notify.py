"""Ping the user: console always, plus optional ntfy.sh, Slack/Discord webhook or desktop notification.

profile.yaml:
    notify:
      ntfy_topic: my-secret-jobhunt-topic     # https://ntfy.sh - phone push notifications
      webhook_url: https://hooks.slack.com/...  # Slack or Discord incoming webhook
      desktop: true                            # notify-send / osascript / Windows balloon
"""
from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from typing import Any

import requests

from . import journal

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config: dict[str, Any] | None = None, echo=print):
        self.config = config or {}
        self.echo = echo

    def send(self, title: str, message: str, record: bool = True) -> None:
        self.echo(f"\n🔔 {title}\n{message}\n")
        if record:
            journal.log(f"{title}: {message}", kind="progress", tags=["notification"])
        topic = self.config.get("ntfy_topic")
        if topic:
            # JSON publishing keeps non-ASCII titles intact (HTTP headers are latin-1 only)
            self._safe(lambda: requests.post("https://ntfy.sh/", json={"topic": topic, "title": title,
                                                                       "message": message}, timeout=10))
        hook = self.config.get("webhook_url")
        if hook:
            key = "content" if "discord" in hook else "text"
            self._safe(lambda: requests.post(hook, json={key: f"*{title}*\n{message}"}, timeout=10))
        if self.config.get("desktop"):
            self._safe(lambda: self._desktop(title, message))

    @staticmethod
    def _desktop(title: str, message: str) -> None:
        if platform.system() == "Darwin":
            subprocess.run(["osascript", "-e", f'display notification {message!r} with title {title!r}'], check=False)
        elif platform.system() == "Windows":
            def q(text: str) -> str:
                return "'" + text.replace("'", "''")[:240] + "'"
            ps = ("Add-Type -AssemblyName System.Windows.Forms; $n = New-Object System.Windows.Forms.NotifyIcon; "
                  "$n.Icon = [System.Drawing.SystemIcons]::Information; $n.Visible = $true; "
                  f"$n.ShowBalloonTip(8000, {q(title)}, {q(message)}, 'Info'); Start-Sleep 9; $n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps])
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", title, message], check=False)

    @staticmethod
    def _safe(fn) -> None:
        try:
            fn()
        except Exception as exc:  # notifications are best-effort
            log.warning("notification failed: %s", exc)
