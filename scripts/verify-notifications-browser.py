#!/usr/bin/env python3
"""Exercise the shared notification UI in a real browser against this Admin demo."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for import_root in (str(ROOT),):
    while import_root in sys.path:
        sys.path.remove(import_root)
    sys.path.insert(0, import_root)

from oldman.testing.notifications import HostContract, notification_gate_main  # noqa: E402

ADMIN_HOST = HostContract(
    name="admin",
    home_path="/admin",
    login_path="/admin/login",
    center_path="/admin/user-notifications",
)


def main() -> int:
    """Run the framework's notification gate against this project's URLs."""
    return notification_gate_main(host=ADMIN_HOST, project_root=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
