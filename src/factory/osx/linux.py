"""Linux systemd user service + timer."""
from __future__ import annotations


def service(python: str, project: str) -> str:
    return f"""[Unit]
Description=Chalisa factory daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={project}
ExecStart={python} -m factory.daemon
Restart=on-failure
RestartSec=30
Nice=10

[Install]
WantedBy=default.target
"""


def timer() -> str:
    return """[Unit]
Description=Chalisa factory watchdog

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
"""