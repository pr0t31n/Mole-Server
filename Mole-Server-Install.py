#!/usr/bin/env python3
"""
Mole-Server — Proxysuite SOCKS5 + DNS server daemon (moled)
Install script for /Users/pr0t31n/Mole-Server/

Detects the OS and architecture, installs the appropriate moled binary,
deploys server.yaml, and creates a persistent systemd service.

Usage:
    sudo python3 Mole-Server-Install.py
    sudo python3 Mole-Server-Install.py --check
    sudo python3 Mole-Server-Install.py --config /path/to/server.yaml
    sudo python3 Mole-Server-Install.py --uninstall
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ─── ANSI colours ─────────────────────────────────────────────────────────────
R = "\033[1;31m"
G = "\033[1;32m"
Y = "\033[1;33m"
B = "\033[1;34m"
C = "\033[1;36m"
W = "\033[0m"
# ──────────────────────────────────────────────────────────────────────────────

SERVICE_NAME   = "proxysuite-server"
SERVICE_USER   = "proxysuite"
BINARY_NAME    = "moled"
BINARY_DEST    = Path("/usr/local/bin/moled")
CONFIG_DIR     = Path("/etc/proxysuite")
CONFIG_DEST    = CONFIG_DIR / "server-config.yaml"
LOG_DIR        = Path("/var/log/proxysuite")
SYSTEMD_UNIT   = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")
SCRIPT_DIR     = Path(__file__).resolve().parent

# Map (os, machine) → binary filename in SCRIPT_DIR
BINARY_MAP = {
    ("linux", "x86_64"):  "moled_linux_amd64",
    ("linux", "aarch64"): "moled_linux_arm64",
    ("linux", "armv7l"):  "moled_linux_arm64",   # best-effort; arm64 binary
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def banner():
    print(f"""
{C}╔══════════════════════════════════════════════════════╗
║   Mole-Server — Proxysuite SOCKS5 + DNS Daemon       ║
║   Install Script                                     ║
╚══════════════════════════════════════════════════════╝{W}
""")


def info(msg):  print(f"{G}[+]{W} {msg}")
def warn(msg):  print(f"{Y}[!]{W} {msg}")
def err(msg):   print(f"{R}[✗]{W} {msg}")
def step(msg):  print(f"\n{B}━━ {msg} ━━{W}")


def run(cmd, **kwargs):
    """Run a command; raise on non-zero exit."""
    print(f"    {C}>{W} {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(str(c) for c in cmd)}")
    return result


def run_ok(cmd, **kwargs):
    """Run a command; return True on success, False on failure."""
    try:
        subprocess.run(cmd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       **kwargs)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ─── OS / arch detection ──────────────────────────────────────────────────────

def detect_platform():
    """Return (os_name, machine) normalised to lowercase."""
    return platform.system().lower(), platform.machine()


def resolve_binary():
    """
    Return the Path of the local moled binary for this host.
    Raises SystemExit if the platform is unsupported.
    """
    os_name, machine = detect_platform()

    if os_name != "linux":
        err(f"Unsupported OS: {os_name}")
        print(f"""
  Only Linux targets are supported by this installer.
  Available binaries:
    moled_linux_amd64  — Linux x86_64
    moled_linux_arm64  — Linux aarch64 / armv7l
""")
        sys.exit(1)

    key = (os_name, machine)
    filename = BINARY_MAP.get(key)
    if not filename:
        err(f"Unsupported architecture: {machine}")
        print(f"  Supported: x86_64, aarch64, armv7l")
        sys.exit(1)

    binary = SCRIPT_DIR / filename
    if not binary.exists():
        err(f"Binary not found in script directory: {binary}")
        print(f"  Expected: {binary}")
        sys.exit(1)

    return binary, filename


# ─── install phases ───────────────────────────────────────────────────────────

def phase_binary(binary_path):
    step("Installing moled Binary")
    shutil.copy2(str(binary_path), str(BINARY_DEST))
    BINARY_DEST.chmod(0o755)
    info(f"Installed: {binary_path.name}  →  {BINARY_DEST}")


def phase_config(config_source):
    step("Deploying Configuration")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_DEST.exists():
        backup = CONFIG_DEST.with_suffix(".yaml.bak")
        shutil.copy2(str(CONFIG_DEST), str(backup))
        warn(f"Existing config backed up to {backup}")
    shutil.copy2(str(config_source), str(CONFIG_DEST))
    CONFIG_DEST.chmod(0o640)
    info(f"Config installed: {CONFIG_DEST}")
    info(f"Edit before starting:  sudo nano {CONFIG_DEST}")


def phase_logdir():
    step("Creating Log Directory")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    info(f"Log directory: {LOG_DIR}")


def phase_user():
    step("Creating Service User")
    if run_ok(["id", SERVICE_USER]):
        info(f"User '{SERVICE_USER}' already exists — skipping.")
        return
    run(["useradd", "--system", "--no-create-home",
         "--shell", "/usr/sbin/nologin",
         "--comment", "Proxysuite moled service account",
         SERVICE_USER])
    info(f"System user created: {SERVICE_USER}")


def phase_ownership():
    """Give the service user ownership of config and log directories."""
    step("Setting Ownership")
    run(["chown", f"root:{SERVICE_USER}", str(CONFIG_DEST)])
    run(["chown", "-R", f"{SERVICE_USER}:{SERVICE_USER}", str(LOG_DIR)])
    info(f"Config:   root:{SERVICE_USER}  (mode 640)")
    info(f"Logs:     {SERVICE_USER}:{SERVICE_USER}")


def phase_service():
    step("Installing systemd Service")

    unit_content = f"""\
[Unit]
Description=Proxysuite SOCKS5 + DNS Server (moled)
Documentation=https://github.com/mole
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={SERVICE_USER}
Group={SERVICE_USER}
ExecStart={BINARY_DEST} --config {CONFIG_DEST}
Restart=on-failure
RestartSec=5s

# Log to journald (view with: journalctl -u {SERVICE_NAME} -f)
StandardOutput=journal
StandardError=journal
SyslogIdentifier={SERVICE_NAME}

# Harden the service
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths={LOG_DIR}
ProtectHome=yes

[Install]
WantedBy=multi-user.target
"""

    SYSTEMD_UNIT.write_text(unit_content)
    SYSTEMD_UNIT.chmod(0o644)
    info(f"Unit file written: {SYSTEMD_UNIT}")

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", SERVICE_NAME])
    info(f"Service enabled (starts on boot)")


def phase_start():
    step("Starting Service")
    if run_ok(["systemctl", "is-active", "--quiet", SERVICE_NAME]):
        info(f"Service already running — restarting for new config/binary.")
        run(["systemctl", "restart", SERVICE_NAME])
    else:
        run(["systemctl", "start", SERVICE_NAME])
    info(f"Service started: {SERVICE_NAME}")
    info(f"Live logs:  journalctl -u {SERVICE_NAME} -f")


# ─── uninstall ────────────────────────────────────────────────────────────────

def uninstall():
    step("Uninstalling Mole-Server")

    if run_ok(["systemctl", "is-active", "--quiet", SERVICE_NAME]):
        run(["systemctl", "stop", SERVICE_NAME])
        info("Service stopped.")

    if run_ok(["systemctl", "is-enabled", "--quiet", SERVICE_NAME]):
        run(["systemctl", "disable", SERVICE_NAME])
        info("Service disabled.")

    if SYSTEMD_UNIT.exists():
        SYSTEMD_UNIT.unlink()
        run(["systemctl", "daemon-reload"])
        info(f"Unit file removed: {SYSTEMD_UNIT}")

    if BINARY_DEST.exists():
        BINARY_DEST.unlink()
        info(f"Binary removed: {BINARY_DEST}")

    warn(f"Config preserved: {CONFIG_DEST}")
    warn(f"Logs preserved:   {LOG_DIR}")
    warn(f"User preserved:   {SERVICE_USER}")
    print(f"\n  To fully remove, run:")
    print(f"    sudo rm -rf {CONFIG_DIR} {LOG_DIR}")
    print(f"    sudo userdel {SERVICE_USER}\n")
    info("Uninstall complete.")


# ─── check mode ───────────────────────────────────────────────────────────────

def run_check():
    step("Check Mode — Installation Status")

    os_name, machine = detect_platform()
    results = []

    # OS support
    supported = os_name == "linux" and (os_name, machine) in BINARY_MAP
    results.append(("platform", supported,
                    f"{os_name}/{machine}" if supported else f"{os_name}/{machine} (unsupported)"))

    # Local binary presence
    key = (os_name, machine)
    filename = BINARY_MAP.get(key, "")
    local_bin = SCRIPT_DIR / filename if filename else None
    ok = bool(local_bin and local_bin.exists())
    results.append(("local binary", ok,
                    str(local_bin) if ok else f"{filename} not found in {SCRIPT_DIR}"))

    # Installed binary
    ok = BINARY_DEST.exists() and os.access(str(BINARY_DEST), os.X_OK)
    detail = "missing"
    if ok:
        ver_r = subprocess.run([str(BINARY_DEST), "--version"],
                               capture_output=True, text=True)
        detail = ver_r.stdout.strip() or str(BINARY_DEST)
    results.append(("installed binary", ok, detail if ok else "missing"))

    # Config
    ok = CONFIG_DEST.exists()
    results.append(("config", ok, str(CONFIG_DEST) if ok else "missing"))

    # Log directory
    ok = LOG_DIR.is_dir()
    results.append(("log directory", ok, str(LOG_DIR) if ok else "missing"))

    # systemd unit
    ok = SYSTEMD_UNIT.exists()
    results.append(("systemd unit", ok, str(SYSTEMD_UNIT) if ok else "missing"))

    # Service enabled
    ok = run_ok(["systemctl", "is-enabled", "--quiet", SERVICE_NAME])
    results.append(("service enabled", ok, "yes" if ok else "no"))

    # Service active
    ok = run_ok(["systemctl", "is-active", "--quiet", SERVICE_NAME])
    results.append(("service active", ok, "running" if ok else "stopped"))

    pad = max(len(r[0]) for r in results) + 2
    print()
    for label, ok_flag, detail in results:
        status = f"{G}OK{W}" if ok_flag else f"{R}FAIL{W}"
        print(f"  {label:<{pad}} {status}  {detail}")

    failed = [r for r in results if not r[1]]
    print()
    if not failed:
        info(f"All checks passed. Service is installed and running.")
    else:
        warn(f"{len(failed)} item(s) not satisfied — run without --check to install.")
    return len(failed) == 0


# ─── post-install summary ─────────────────────────────────────────────────────

def post_install_summary():
    step("Post-Install Verification Summary")
    results = []

    ok = BINARY_DEST.exists() and os.access(str(BINARY_DEST), os.X_OK)
    results.append(("binary", ok, str(BINARY_DEST) if ok else "missing"))

    ok = CONFIG_DEST.exists()
    results.append(("config", ok, str(CONFIG_DEST) if ok else "missing"))

    ok = LOG_DIR.is_dir()
    results.append(("log directory", ok, str(LOG_DIR) if ok else "missing"))

    ok = SYSTEMD_UNIT.exists()
    results.append(("systemd unit", ok, str(SYSTEMD_UNIT) if ok else "missing"))

    ok = run_ok(["systemctl", "is-enabled", "--quiet", SERVICE_NAME])
    results.append(("service enabled", ok, "yes" if ok else "no"))

    ok = run_ok(["systemctl", "is-active", "--quiet", SERVICE_NAME])
    results.append(("service active", ok, "running" if ok else "not running"))

    pad = max(len(r[0]) for r in results) + 2
    print()
    for label, ok_flag, detail in results:
        status = f"{G}OK{W}" if ok_flag else f"{R}FAIL{W}"
        print(f"  {label:<{pad}} {status}  {detail}")

    failed = [r for r in results if not r[1]]
    print()
    if not failed:
        info(f"{G}Mole-Server installation complete.{W}")
        print(f"""
  {C}Next steps:{W}
    1. Review / edit config:  sudo nano {CONFIG_DEST}
    2. Restart after edits:   sudo systemctl restart {SERVICE_NAME}
    3. Live logs:             sudo journalctl -u {SERVICE_NAME} -f
    4. File logs:             ls {LOG_DIR}/
""")
    else:
        warn(f"{len(failed)} item(s) need attention (see above).")


# ─── argument parsing ─────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Installer for Mole-Server (proxysuite moled daemon)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  sudo python3 {Path(__file__).name}
  sudo python3 {Path(__file__).name} --config /path/to/server.yaml
  sudo python3 {Path(__file__).name} --check
  sudo python3 {Path(__file__).name} --uninstall
""",
    )
    p.add_argument(
        "--config",
        metavar="FILE",
        default=str(SCRIPT_DIR / "server.yaml"),
        help=f"Path to server.yaml to deploy (default: {SCRIPT_DIR / 'server.yaml'})",
    )
    p.add_argument(
        "--no-start",
        action="store_true",
        help="Install and enable service but do not start it now",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Report installation status and exit",
    )
    p.add_argument(
        "--uninstall",
        action="store_true",
        help="Stop and remove the service and binary (preserves config and logs)",
    )
    return p.parse_args()


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    banner()
    args = parse_args()

    if args.check:
        ok = run_check()
        sys.exit(0 if ok else 1)

    if args.uninstall:
        if os.geteuid() != 0:
            err("Must be run as root: sudo python3 Mole-Server-Install.py --uninstall")
            sys.exit(1)
        uninstall()
        sys.exit(0)

    # ── root check ────────────────────────────────────────────────────────────
    if os.geteuid() != 0:
        err("Must be run as root.")
        print(f"  Run: sudo python3 {Path(__file__).name}")
        sys.exit(1)

    # ── platform ──────────────────────────────────────────────────────────────
    os_name, machine = detect_platform()
    info(f"Platform: {os_name} / {machine}")

    binary_path, binary_filename = resolve_binary()
    info(f"Selected binary: {binary_filename}")

    # ── config source ─────────────────────────────────────────────────────────
    config_source = Path(args.config)
    if not config_source.exists():
        err(f"Config file not found: {config_source}")
        sys.exit(1)
    info(f"Config source: {config_source}")

    # ── run phases ────────────────────────────────────────────────────────────
    phase_binary(binary_path)
    phase_config(config_source)
    phase_logdir()
    phase_user()
    phase_ownership()
    phase_service()

    if not args.no_start:
        phase_start()

    post_install_summary()


if __name__ == "__main__":
    main()
