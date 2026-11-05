# Mole-Server

Pre-built server-side daemon for the **Mole** SOCKS5 + DNS transparent proxy suite.

`moled` is the server component. It accepts tunnelled TCP connections via SOCKS5 and resolves DNS queries on behalf of Mole clients, allowing client machines on restricted networks to reach the open internet with full DNS bypass.

---


> **[View full documentation on the Codex Wiki](https://wiki.pr0t31n.com/tools/mole-server)** — detailed features, CLI reference, findings catalogue, and integration guides.

## How It Fits Together

```
┌──────────────── RESTRICTED NETWORK ─────────────────────┐
│                                                          │
│  ┌────────────────────────┐                              │
│  │  CLIENT MACHINE        │      ┌──────────────────┐   │
│  │                        │ VPN  │  THIS SERVER     │   │
│  │  Any app → TCP         │══════│                  │   │
│  │   ↓ intercepted        │      │  moled :1080     │   │
│  │  Transparent proxy     │      │   ↓ SOCKS5       │   │
│  │   ↓ SOCKS5 tunnel      │      │  → internet      │   │
│  │                        │      │                  │   │
│  │  Any app → DNS query   │      │  DNS proxy :5353 │   │
│  │   ↓ intercepted        │      │   ↓ 1.1.1.1      │   │
│  │  DNS proxy :53         │      └──────────────────┘   │
│  │   ↓ SOCKS5 tunnel      │                              │
│  └────────────────────────┘                              │
│  Network DNS: COMPLETELY BYPASSED                        │
└──────────────────────────────────────────────────────────┘
```

The client (a separate tool) intercepts all outbound TCP and DNS traffic transparently — applications need no configuration. `moled` is the exit point: it forwards TCP and resolves DNS against a public upstream resolver.

---

## Contents

| File | Description |
|------|-------------|
| `moled_linux_amd64` | Server binary — Linux x86_64 |
| `moled_linux_arm64` | Server binary — Linux aarch64 / armv7l |
| `server.yaml` | Configuration template |
| `Mole-Server-Install.py` | Installer — detects arch, deploys binary and service |

---

## Requirements

- **Linux** with systemd (Debian, Ubuntu, Kali, RHEL, Fedora, etc.)
- **Root** to run the installer
- Inbound firewall access on the SOCKS5 and DNS ports (default: TCP 1080, TCP/UDP 5353)
- The server must be reachable from clients over a VPN tunnel

---

## Quick Start

### 1. Edit the configuration

```bash
nano server.yaml
```

At minimum, set `bind_address` to the VPN interface IP clients will connect to:

```yaml
server:
  bind_address: "10.8.0.1"   # VPN IP clients reach this server on
  socks5_port: 1080
  dns_port: 5353
```

See [Configuration Reference](#configuration-reference) for all options.

### 2. Run the installer

```bash
sudo python3 Mole-Server-Install.py
```

The installer:
- Detects the host architecture and selects the correct binary
- Installs `moled` to `/usr/local/bin/moled`
- Deploys the config to `/etc/proxysuite/server-config.yaml`
- Creates the `proxysuite` system user
- Creates `/var/log/proxysuite/` with correct ownership
- Writes and enables the `proxysuite-server` systemd service
- Starts the service

### 3. Open the firewall

```bash
# ufw
sudo ufw allow 1080/tcp comment "Mole SOCKS5"
sudo ufw allow 5353/tcp comment "Mole DNS TCP"
sudo ufw allow 5353/udp comment "Mole DNS UDP"

# firewalld
sudo firewall-cmd --permanent --add-port=1080/tcp
sudo firewall-cmd --permanent --add-port=5353/tcp
sudo firewall-cmd --permanent --add-port=5353/udp
sudo firewall-cmd --reload

# iptables directly
sudo iptables -A INPUT -p tcp --dport 1080 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 5353 -j ACCEPT
sudo iptables -A INPUT -p udp --dport 5353 -j ACCEPT
```

### 4. Verify

```bash
sudo systemctl status proxysuite-server
sudo journalctl -u proxysuite-server -f
```

---

## Configuration Reference

Config is deployed to `/etc/proxysuite/server-config.yaml`. After editing, restart the service:

```bash
sudo systemctl restart proxysuite-server
```

```yaml
# ── Network binding ───────────────────────────────────────────────────────────
server:
  # IP to listen on. Use "0.0.0.0" for all interfaces (when behind a firewall),
  # or the VPN interface IP (e.g. "10.8.0.1") to restrict access.
  bind_address: "0.0.0.0"

  # SOCKS5 port — clients tunnel TCP here.
  # Must be open in the firewall (TCP inbound).
  socks5_port: 1080

  # DNS port — clients send DNS-over-TCP here via the SOCKS5 tunnel.
  # Must be open in the firewall (TCP + UDP inbound).
  # Use 5353 or higher to avoid requiring root (port 53 requires root).
  dns_port: 5353

# ── Authentication ────────────────────────────────────────────────────────────
# SOCKS5 username/password sub-negotiation (RFC 1929).
# Credentials are plaintext over the wire — only enable over an encrypted VPN.
auth:
  enabled: false     # Set true to require credentials
  username: ""
  password: ""

# ── Upstream DNS ──────────────────────────────────────────────────────────────
# The resolver moled contacts to answer client DNS queries.
# Common choices: 1.1.1.1:53 (Cloudflare), 8.8.8.8:53 (Google), 9.9.9.9:53 (Quad9)
upstream_dns: "1.1.1.1:53"

# ── Logging ───────────────────────────────────────────────────────────────────
logging:
  dir: "/var/log/proxysuite"
  verbose: true                # false → only errors to stdout; all events to files
  connection_retain_days: 90   # days to keep connection logs (0 = forever)
  error_retain_days: 30        # days to keep error logs (0 = forever)
```

---

## Service Management

```bash
# Status
sudo systemctl status proxysuite-server

# Live logs (journald)
sudo journalctl -u proxysuite-server -f

# Start / stop / restart
sudo systemctl start   proxysuite-server
sudo systemctl stop    proxysuite-server
sudo systemctl restart proxysuite-server

# Enable / disable on boot
sudo systemctl enable  proxysuite-server
sudo systemctl disable proxysuite-server
```

---

## Log Files

Logs are written to `/var/log/proxysuite/` and rotate daily at midnight UTC.

| File | Retention | Content |
|------|-----------|---------|
| `server_connections_YYYY-MM-DD.log` | 90 days | CONNECT / DISCONNECT events with bytes transferred |
| `server_errors_YYYY-MM-DD.log` | 30 days | All errors |

```bash
# Tail today's connection log
tail -f /var/log/proxysuite/server_connections_$(date +%Y-%m-%d).log

# Tail today's error log
tail -f /var/log/proxysuite/server_errors_$(date +%Y-%m-%d).log
```

---

## Installer Options

```
sudo python3 Mole-Server-Install.py [OPTIONS]

  --config FILE    Path to server.yaml to deploy
                   (default: ./server.yaml alongside the installer)
  --no-start       Install and enable the service but do not start it yet
  --check          Report installation status without making changes
  --uninstall      Stop/disable service and remove binary; preserves config and logs
```

### Check mode

```bash
sudo python3 Mole-Server-Install.py --check
```

Reports platform compatibility, binary presence, config, log directory, systemd unit state, and whether the service is active — without making any changes.

### Uninstall

```bash
sudo python3 Mole-Server-Install.py --uninstall
```

Stops and disables the service, removes the unit file and binary. Config (`/etc/proxysuite/`) and logs (`/var/log/proxysuite/`) are preserved. To remove them entirely:

```bash
sudo rm -rf /etc/proxysuite /var/log/proxysuite
sudo userdel proxysuite
```

---

## Troubleshooting

**Service fails to start**
```bash
sudo journalctl -u proxysuite-server -n 50 --no-pager
```
Most common cause: `bind_address` in config does not match any interface on this host.

**Client cannot connect**
```bash
# From the client, test the SOCKS5 port
nc -zv <server-ip> 1080

# From the client, test the DNS port
nc -zv <server-ip> 5353
```
Check that the firewall allows inbound TCP on 1080 and TCP/UDP on 5353.

**DNS queries not resolving**
```bash
# On the server, verify upstream is reachable
dig @1.1.1.1 google.com
```
If the upstream resolver is unreachable from the server, change `upstream_dns` in the config.

**Check what moled is listening on**
```bash
ss -tulpn | grep moled
```

---

## Attribution

`moled` is built on the following open-source libraries.

| Library | Author | Link |
|---------|--------|------|
| `github.com/miekg/dns` | Miek Gieben | https://github.com/miekg/dns |
| `golang.org/x/net/proxy` | The Go Authors / Google | https://pkg.go.dev/golang.org/x/net/proxy |
| `golang.org/x/sys` | The Go Authors / Google | https://pkg.go.dev/golang.org/x/sys |
| `gopkg.in/yaml.v3` | Canonical Ltd / go-yaml team | https://github.com/go-yaml/yaml |
