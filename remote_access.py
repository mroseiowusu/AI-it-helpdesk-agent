"""
remote_access.py — SSH log and diagnostics collector
=====================================================
Pulls diagnostic data from remote machines over SSH.
Supports both Linux/Mac (via SSH commands) and Windows (via SSH + PowerShell).

Install:
    pip install paramiko

Usage:
    from remote_access import collect_diagnostics
    data = collect_diagnostics(host="192.168.1.10", username="admin", password="secret", platform="windows")
"""

import logging
import paramiko

log = logging.getLogger(__name__)


def _ssh_connect(host: str, username: str, password: str = None, key_path: str = None) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs = dict(hostname=host, username=username, timeout=10)
    if key_path:
        connect_kwargs["key_filename"] = key_path
    else:
        connect_kwargs["password"] = password
    client.connect(**connect_kwargs)
    return client


def _run(client: paramiko.SSHClient, command: str) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=15)
    output = stdout.read().decode("utf-8", errors="replace").strip()
    error = stderr.read().decode("utf-8", errors="replace").strip()
    return output if output else error


def collect_linux(host: str, username: str, password: str = None, key_path: str = None) -> dict:
    """Pull diagnostics from a Linux or Mac machine over SSH."""
    client = _ssh_connect(host, username, password, key_path)
    log.info(f"Connected to Linux/Mac host: {host}")

    results = {}
    try:
        results["syslog_tail"] = _run(client, "sudo tail -n 50 /var/log/syslog 2>/dev/null || tail -n 50 /var/log/system.log 2>/dev/null")
        results["top_processes"] = _run(client, "ps aux --sort=-%cpu | head -15")
        results["disk_usage"] = _run(client, "df -h")
        results["memory_usage"] = _run(client, "free -h 2>/dev/null || vm_stat")
        results["failed_services"] = _run(client, "systemctl --failed 2>/dev/null || echo 'systemctl not available'")
        results["last_logins"] = _run(client, "last -n 10")
        log.info(f"Linux diagnostics collected from {host}")
    finally:
        client.close()

    return results


def collect_windows(host: str, username: str, password: str = None, key_path: str = None) -> dict:
    """Pull diagnostics from a Windows machine via SSH + PowerShell.
    Requires OpenSSH to be enabled on the Windows machine:
    Settings > Apps > Optional Features > OpenSSH Server
    """
    client = _ssh_connect(host, username, password, key_path)
    log.info(f"Connected to Windows host: {host}")

    results = {}
    try:
        results["event_log_errors"] = _run(
            client,
            'powershell -Command "Get-EventLog -LogName System -EntryType Error -Newest 20 | Select-Object TimeGenerated, Source, Message | Format-List"'
        )
        results["top_processes"] = _run(
            client,
            'powershell -Command "Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name, CPU, WorkingSet | Format-Table -AutoSize"'
        )
        results["disk_usage"] = _run(
            client,
            'powershell -Command "Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free | Format-Table -AutoSize"'
        )
        results["failed_services"] = _run(
            client,
            'powershell -Command "Get-Service | Where-Object {$_.Status -eq \'Stopped\' -and $_.StartType -eq \'Automatic\'} | Select-Object Name, DisplayName | Format-Table -AutoSize"'
        )
        results["system_info"] = _run(
            client,
            'powershell -Command "Get-ComputerInfo | Select-Object WindowsProductName, TotalPhysicalMemory, CsProcessors | Format-List"'
        )
        results["recent_app_errors"] = _run(
            client,
            'powershell -Command "Get-EventLog -LogName Application -EntryType Error -Newest 10 | Select-Object TimeGenerated, Source, Message | Format-List"'
        )
        log.info(f"Windows diagnostics collected from {host}")
    finally:
        client.close()

    return results


def collect_diagnostics(host: str, username: str, password: str = None,
                         key_path: str = None, platform: str = "linux") -> dict:
    """
    Main entry point. Collects all diagnostics from a remote machine.

    Args:
        host:       IP address or hostname
        username:   SSH username
        password:   SSH password (or use key_path)
        key_path:   Path to SSH private key file
        platform:   "linux", "mac", or "windows"

    Returns:
        Dict of diagnostic sections, or {"error": "..."} on failure
    """
    try:
        if platform.lower() == "windows":
            return collect_windows(host, username, password, key_path)
        else:
            return collect_linux(host, username, password, key_path)
    except Exception as e:
        log.error(f"SSH collection failed for {host}: {e}")
        return {"error": str(e)}


def summarize_for_agent(diagnostics: dict) -> str:
    """
    Formats raw diagnostics into a concise summary Claude can reason about.
    Keeps it under ~800 tokens so it fits cleanly in the agent's context.
    """
    if "error" in diagnostics:
        return f"Remote access failed: {diagnostics['error']}"

    sections = []
    for key, value in diagnostics.items():
        if value and len(value) > 10:
            label = key.replace("_", " ").title()
            truncated = value[:600] + "..." if len(value) > 600 else value
            sections.append(f"### {label}\n{truncated}")

    return "\n\n".join(sections) if sections else "No diagnostic data retrieved."


if __name__ == "__main__":
    import sys
    import json
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 4:
        print("Usage: python remote_access.py <host> <username> <password> [windows|linux]")
        sys.exit(1)

    host, username, password = sys.argv[1], sys.argv[2], sys.argv[3]
    platform = sys.argv[4] if len(sys.argv) > 4 else "linux"

    data = collect_diagnostics(host, username, password, platform=platform)
    print(json.dumps(data, indent=2))
    print("\n--- AGENT SUMMARY ---")
    print(summarize_for_agent(data))
