"""
machine_registry.py — Employee to machine lookup
=================================================
SQLite-backed registry mapping employee IDs to their machines.
In production this would connect to your Active Directory or CMDB.

Usage:
    from machine_registry import get_machine, register_machine
"""

import sqlite3
import os
import logging

log = logging.getLogger(__name__)

DB_PATH = os.environ.get("REGISTRY_DB_PATH", "/tmp/machine_registry.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the registry table if it doesn't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS machines (
                employee_id TEXT PRIMARY KEY,
                name        TEXT,
                host        TEXT NOT NULL,
                platform    TEXT NOT NULL DEFAULT 'linux',
                ssh_user    TEXT NOT NULL,
                ssh_pass    TEXT,
                ssh_key     TEXT,
                department  TEXT,
                notes       TEXT
            )
        """)
        conn.commit()
    log.info("Machine registry initialized.")


def register_machine(employee_id: str, name: str, host: str, platform: str,
                     ssh_user: str, ssh_pass: str = None, ssh_key: str = None,
                     department: str = None, notes: str = None):
    """Add or update a machine in the registry."""
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO machines (employee_id, name, host, platform, ssh_user, ssh_pass, ssh_key, department, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id) DO UPDATE SET
                name=excluded.name, host=excluded.host, platform=excluded.platform,
                ssh_user=excluded.ssh_user, ssh_pass=excluded.ssh_pass,
                ssh_key=excluded.ssh_key, department=excluded.department, notes=excluded.notes
        """, (employee_id, name, host, platform, ssh_user, ssh_pass, ssh_key, department, notes))
        conn.commit()
    log.info(f"Registered machine for employee {employee_id}: {host} ({platform})")


def get_machine(employee_id: str) -> dict | None:
    """Look up a machine by employee ID. Returns None if not found."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM machines WHERE employee_id = ?", (employee_id,)
        ).fetchone()
    if row:
        return dict(row)
    return None


def seed_demo_data():
    """Seed some fake employees for PoC demos."""
    init_db()
    demo_employees = [
        ("EMP001", "Alice Johnson", "192.168.1.101", "windows", "admin", "demo_pass_123", None, "Engineering", "Win11 laptop"),
        ("EMP002", "Bob Smith",    "192.168.1.102", "linux",   "ubuntu", "demo_pass_456", None, "Marketing",   "Ubuntu 22.04 desktop"),
        ("EMP003", "Carol White",  "192.168.1.103", "windows", "admin", "demo_pass_789", None, "Finance",     "Win10 desktop"),
        ("EMP004", "Dave Brown",   "192.168.1.104", "linux",   "dave",  "demo_pass_abc", None, "IT",          "Mac via SSH"),
    ]
    for emp in demo_employees:
        register_machine(*emp)
    log.info("Demo data seeded — 4 employees registered.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed_demo_data()
        print("Demo data seeded.")
    elif len(sys.argv) > 1:
        emp_id = sys.argv[1]
        machine = get_machine(emp_id)
        if machine:
            import json
            print(json.dumps(machine, indent=2))
        else:
            print(f"No machine found for employee ID: {emp_id}")
    else:
        print("Usage: python machine_registry.py seed")
        print("       python machine_registry.py EMP001")
