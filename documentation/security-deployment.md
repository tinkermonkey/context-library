# Security & Cross-Machine Deployment Guide

This document covers the security requirements and configuration options for deploying `RemoteAdapter` and Mac-side adapter services across a network. It documents three supported deployment models with concrete configuration examples.

## Table of Contents

1. [Network Architecture Overview](#network-architecture-overview)
2. [Deployment Models](#deployment-models)
3. [Bind Address Requirements](#bind-address-requirements)
4. [Configuration Parameters](#configuration-parameters)
5. [End-to-End Configuration Example](#end-to-end-configuration-example)
6. [Security Risks and Mitigations](#security-risks-and-mitigations)
7. [Troubleshooting](#troubleshooting)

---

## Network Architecture Overview

The Context Library supports distributed adapter services across machines using the `RemoteAdapter` client and `serve_adapter` server components:

- **Linux Backend (client side):** Runs the main application with local adapters and `RemoteAdapter` instances that consume remote services
- **Mac Services (server side):** Runs `serve_adapter` wrappers that expose adapters over HTTP for remote consumption

The connection between Linux and Mac can be secured using three different models, detailed below.

---

## Deployment Models

### Model 1: Bearer Token over LAN/VPN (Minimum Viable)

**Recommended for:** Home networks, isolated LANs, or deployments within a VPN tunnel (WireGuard, Tailscale, etc.)

**Security posture:** Simple shared secret authentication; bearer token transmitted in Authorization header.

**When to use this model:**
- Deploying within a trusted home network
- Services connected via VPN (WireGuard, Tailscale, OpenVPN)
- Short-term testing and development on isolated networks

**Configuration:**

**Mac side (`serve_adapter` server):**

```python
from context_library.adapters import ObsidianAdapter, AppleRemindersAdapter
from context_library.adapters.serve import serve_adapter

# Obsidian Notes adapter
obsidian = ObsidianAdapter(vault_path="/Users/me/Documents/Obsidian")
serve_adapter(
    obsidian,
    host="0.0.0.0",      # Accept connections from any interface
    port=8001,
    api_key="vault-key-c7f2a9e8b3d1f4e6"  # Shared secret token
)

# Apple Reminders adapter on a different port
from context_library.adapters import AppleRemindersAdapter
reminders = AppleRemindersAdapter(
    api_url="http://127.0.0.1:7123",
    account_id="default"
)
serve_adapter(
    reminders,
    host="0.0.0.0",
    port=8002,
    api_key="reminders-key-a1b2c3d4e5f6g7h8"  # Different secret per service
)
```

**Linux side (`RemoteAdapter` client):**

```python
from context_library.adapters import RemoteAdapter, FilesystemAdapter
from context_library.storage.models import Domain

adapters = [
    # Local adapter for filesystem notes
    FilesystemAdapter(root="/home/user/notes"),

    # Remote Mac service: Obsidian notes
    RemoteAdapter(
        service_url="http://mac.local:8001",        # Mac hostname/IP on LAN
        domain=Domain.NOTES,
        adapter_id="obsidian:vault-main",
        api_key="vault-key-c7f2a9e8b3d1f4e6",       # Must match Mac side
    ),

    # Remote Mac service: Apple Reminders
    RemoteAdapter(
        service_url="http://mac.local:8002",
        domain=Domain.TASKS,
        adapter_id="apple_reminders:default",
        api_key="reminders-key-a1b2c3d4e5f6g7h8",   # Must match Mac side
    ),
]
```

**Security considerations:**
- Bearer token is transmitted in the `Authorization: Bearer <token>` header
- Token is NOT encrypted over plain HTTP; only safe on isolated LANs or within VPN tunnels
- Use a cryptographically generated token (recommended: 32+ random characters)
- Rotate tokens periodically
- Each service should use a distinct API key

---

### Model 2: mTLS (Client Certificate Authentication)

**Recommended for:** Cross-network deployments without VPN, internet-facing services, high-security environments.

**Security posture:** Mutual TLS with client and server certificate verification; no shared secrets transmitted in the clear.

**Prerequisites:**
- CA certificate (Certificate Authority)
- Server certificate and private key (for Mac side)
- Client certificate and private key (for Linux side)

**Certificate setup:**

Generate a CA, server cert, and client cert:

```bash
# 1. Generate CA private key and certificate
openssl genrsa -out ca.key 4096
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
  -subj "/CN=Context-Library-CA/O=ContextLibrary/C=US"

# 2. Generate server certificate (Mac side)
openssl genrsa -out server.key 4096
openssl req -new -key server.key -out server.csr \
  -subj "/CN=mac.example.com/O=ContextLibrary/C=US"
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt -extensions SAN \
  -extfile <(printf "subjectAltName=DNS:mac.example.com,DNS:*.mac.local")

# 3. Generate client certificate (Linux side)
openssl genrsa -out client.key 4096
openssl req -new -key client.key -out client.csr \
  -subj "/CN=linux-backend/O=ContextLibrary/C=US"
openssl x509 -req -days 365 -in client.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out client.crt
```

**Mac side configuration (`serve_adapter`):**

```python
from context_library.adapters import ObsidianAdapter
from context_library.adapters.serve import serve_adapter
import ssl

obsidian = ObsidianAdapter(vault_path="/Users/me/Documents/Obsidian")

# Configure HTTPS with mTLS
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(
    certfile="/etc/context-library/server.crt",
    keyfile="/etc/context-library/server.key",
)
ssl_context.load_verify_locations("/etc/context-library/ca.crt")
ssl_context.verify_mode = ssl.CERT_REQUIRED  # Require client certificate

serve_adapter(
    obsidian,
    host="0.0.0.0",
    port=8001,
    ssl_context=ssl_context,  # Note: Uvicorn/Starlette parameter
)
```

**Linux side configuration (`RemoteAdapter`):**

```python
from context_library.adapters import RemoteAdapter
from context_library.storage.models import Domain
import httpx

# Create HTTP client with mTLS configuration
mtls_client = httpx.Client(
    cert=("/home/user/.context-lib/client.crt", "/home/user/.context-lib/client.key"),
    verify="/home/user/.context-lib/ca.crt",
)

adapter = RemoteAdapter(
    service_url="https://mac.example.com:8001",
    domain=Domain.NOTES,
    adapter_id="obsidian:vault-main",
    # RemoteAdapter will use the configured client for connections
)
```

**Security benefits:**
- No shared secrets transmitted in cleartext
- Server authenticates client via certificate
- Client verifies server certificate (prevents man-in-the-middle)
- Suitable for deployments across untrusted networks or the internet
- Supports certificate rotation and expiration policies

---

### Model 3: SSH Tunnel / WireGuard (Transport Layer Encryption)

**Recommended for:** Existing SSH infrastructure, quick secure connections, simple deployment.

**Security posture:** Encrypts the entire connection at the transport layer; services run on localhost only.

**When to use this model:**
- You already manage SSH keys for server access
- Simple setup without certificate infrastructure
- Leveraging existing WireGuard/VPN networks

#### Option A: SSH Tunnel

**Setup:**

On the Linux backend, establish an SSH tunnel to the Mac:

```bash
# Forward local port 8001 to Mac's port 8001 through SSH
ssh -L 8001:localhost:8001 user@mac.example.com &

# For multiple services, forward multiple ports
ssh -L 8001:localhost:8001 -L 8002:localhost:8002 user@mac.example.com &
```

Alternatively, add to SSH config (`~/.ssh/config`):

```
Host mac-adapter
  HostName mac.example.com
  User myuser
  LocalForward 8001 localhost:8001
  LocalForward 8002 localhost:8002
  IdentityFile ~/.ssh/context-lib-key
  StrictHostKeyChecking accept-new
```

Then connect:

```bash
ssh -N mac-adapter &  # -N means no shell, just port forwarding
```

**Mac side (`serve_adapter`):**

```python
from context_library.adapters import ObsidianAdapter
from context_library.adapters.serve import serve_adapter

obsidian = ObsidianAdapter(vault_path="/Users/me/Documents/Obsidian")

# Bind only to localhost (SSH tunnel handles remote access)
serve_adapter(
    obsidian,
    host="127.0.0.1",      # Only localhost, tunnel provides remote access
    port=8001,
    api_key="vault-key-c7f2a9e8b3d1f4e6"  # Optional, can still use bearer token
)
```

**Linux side (`RemoteAdapter`):**

```python
from context_library.adapters import RemoteAdapter
from context_library.storage.models import Domain

adapter = RemoteAdapter(
    service_url="http://localhost:8001",   # Connect through SSH tunnel
    domain=Domain.NOTES,
    adapter_id="obsidian:vault-main",
    api_key="vault-key-c7f2a9e8b3d1f4e6",
)
```

#### Option B: WireGuard VPN

Alternatively, use WireGuard or Tailscale to create a virtual network:

```bash
# (Assumes WireGuard is already configured on both Mac and Linux)
# Mac and Linux are on the WireGuard network (e.g., 10.0.0.0/8)

# Mac IP on WireGuard: 10.0.0.2
# Linux IP on WireGuard: 10.0.0.3
```

**Mac side:**

```python
serve_adapter(
    obsidian,
    host="0.0.0.0",        # Can accept from any interface on WireGuard
    port=8001,
)
```

**Linux side:**

```python
RemoteAdapter(
    service_url="http://10.0.0.2:8001",  # Mac's WireGuard IP
    domain=Domain.NOTES,
    adapter_id="obsidian:vault-main",
)
```

**Security benefits:**
- SSH tunnel uses established SSH infrastructure
- WireGuard provides lightweight, high-performance encryption
- No additional certificate management required
- Services remain localhost-only on Mac (minimal exposure)
- Easy to audit and revoke (SSH keys, VPN configuration)

---

## Bind Address Requirements

### Key Principle

**Services must bind to `0.0.0.0` to accept remote connections. Binding to `127.0.0.1` restricts access to localhost only.**

### Localhost-Only Binding (`127.0.0.1`)

```python
serve_adapter(adapter, host="127.0.0.1", port=8001)
# Accepts connections from:
# - localhost
# - 127.0.0.1
# Rejects connections from:
# - Any remote IP (including 192.168.x.x, mac.local, etc.)
```

**Use for:**
- Services protected by SSH tunnel (remote access via tunnel)
- Services protected by VPN (remote access via VPN interface)
- Local-only services with no remote access

### Accept All Interfaces (`0.0.0.0`)

```python
serve_adapter(adapter, host="0.0.0.0", port=8001)
# Accepts connections from:
# - localhost (127.0.0.1)
# - All network interfaces (LAN, WAN, etc.)
```

**Use for:**
- Bearer token model on trusted LANs
- mTLS deployments (certificate authentication protects connections)
- Any model requiring remote connections without VPN/tunnel

### Specific Interface Binding

```python
serve_adapter(adapter, host="192.168.1.10", port=8001)
# Accepts connections from:
# - 192.168.1.10 only (useful for multi-homed systems)
```

---

## Configuration Parameters

### Mac-Side: `serve_adapter()` Parameters

**Core parameters:**

```python
serve_adapter(
    adapter,                    # BaseAdapter instance (required)
    host="0.0.0.0",            # Bind address; use "127.0.0.1" for localhost-only
    port=8001,                 # Port number (required)
    api_key=None,              # Optional Bearer token for authentication
    request_body_limit=10485760, # Request body size limit (10 MB default)
)
```

**Parameter details:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `adapter` | `BaseAdapter` | — | The adapter instance to serve |
| `host` | `str` | `"0.0.0.0"` | Bind address. Use `"0.0.0.0"` for remote access, `"127.0.0.1"` for localhost-only |
| `port` | `int` | — | Port number (1024–65535; <1024 requires elevated privileges) |
| `api_key` | `str \| None` | `None` | Optional Bearer token; if set, all requests must include `Authorization: Bearer <token>` |
| `request_body_limit` | `int` | 10 MB | Maximum request body size to prevent memory exhaustion attacks |

### Linux-Side: `RemoteAdapter()` Parameters

**Core parameters:**

```python
RemoteAdapter(
    service_url="http://mac.local:8001",  # HTTP endpoint (required)
    domain=Domain.NOTES,                  # Semantic domain (required)
    adapter_id="obsidian:vault-main",     # Unique identifier (required)
    api_key=None,                         # Optional Bearer token (must match Mac side)
    timeout=30,                           # Request timeout in seconds
)
```

**Parameter details:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `service_url` | `str` | — | Full HTTP(S) URL to the remote service (required) |
| `domain` | `Domain` | — | Domain (MESSAGES, NOTES, EVENTS, TASKS) |
| `adapter_id` | `str` | — | Unique identifier for this adapter instance |
| `api_key` | `str \| None` | `None` | Bearer token; must match the `api_key` on Mac side |
| `timeout` | `int` | 30 | Request timeout in seconds |

---

## End-to-End Configuration Example

This example demonstrates a complete deployment with:
- A local filesystem adapter (Linux)
- Obsidian notes service (Mac)
- Apple Reminders service (Mac)
- All configured with Bearer token authentication over a LAN

### Mac Service Setup

Create a service launcher script on the Mac (`~/bin/start_adapters.py`):

```python
#!/usr/bin/env python3
"""
Launcher script for Context Library adapters on Mac.

Starts:
1. Obsidian notes adapter on port 8001
2. Apple Reminders adapter on port 8002

Both services bind to 0.0.0.0 to accept remote connections
over the LAN, protected by Bearer tokens.
"""

from context_library.adapters import (
    ObsidianAdapter,
    AppleRemindersAdapter,
)
from context_library.adapters.serve import serve_adapter
import threading

def start_obsidian_adapter():
    """Serve Obsidian vault over HTTP."""
    adapter = ObsidianAdapter(
        vault_path="/Users/me/Documents/Obsidian"
    )
    serve_adapter(
        adapter,
        host="0.0.0.0",
        port=8001,
        api_key="obsidian-vault-secret-5f2a9e8b3d1c4f6e",
    )

def start_reminders_adapter():
    """Serve Apple Reminders over HTTP."""
    adapter = AppleRemindersAdapter(
        api_url="http://127.0.0.1:7123",
        account_id="default",
    )
    serve_adapter(
        adapter,
        host="0.0.0.0",
        port=8002,
        api_key="reminders-secret-a1b2c3d4e5f6g7h8",
    )

if __name__ == "__main__":
    # Start both adapters in background threads
    obsidian_thread = threading.Thread(target=start_obsidian_adapter, daemon=True)
    reminders_thread = threading.Thread(target=start_reminders_adapter, daemon=True)

    obsidian_thread.start()
    reminders_thread.start()

    print("✓ Obsidian adapter listening on 0.0.0.0:8001")
    print("✓ Reminders adapter listening on 0.0.0.0:8002")

    # Keep main thread alive
    try:
        obsidian_thread.join()
        reminders_thread.join()
    except KeyboardInterrupt:
        print("Shutting down adapters...")
```

Run the launcher:

```bash
chmod +x ~/bin/start_adapters.py
python3 ~/bin/start_adapters.py
# Output:
# ✓ Obsidian adapter listening on 0.0.0.0:8001
# ✓ Reminders adapter listening on 0.0.0.0:8002
```

### Linux Backend Setup

On the Linux backend, configure `RemoteAdapter` instances that consume the Mac services:

```python
from context_library.adapters import (
    RemoteAdapter,
    FilesystemAdapter,
)
from context_library.storage.models import Domain
from context_library.storage.document_store import DocumentStore

# Initialize document store
store = DocumentStore(db_path="/home/user/.context-lib/context.db")

# Configure local and remote adapters
adapters = [
    # Local adapter: Filesystem notes on Linux
    FilesystemAdapter(
        root="/home/user/notes",
    ),

    # Remote adapter: Obsidian vault from Mac
    RemoteAdapter(
        service_url="http://mac.local:8001",
        domain=Domain.NOTES,
        adapter_id="obsidian:vault-main",
        api_key="obsidian-vault-secret-5f2a9e8b3d1c4f6e",  # Must match Mac side
        timeout=30,
    ),

    # Remote adapter: Apple Reminders from Mac
    RemoteAdapter(
        service_url="http://mac.local:8002",
        domain=Domain.TASKS,
        adapter_id="apple_reminders:default",
        api_key="reminders-secret-a1b2c3d4e5f6g7h8",  # Must match Mac side
        timeout=30,
    ),
]

# Register adapters with document store
for adapter in adapters:
    source_id = adapter.register(store)
    print(f"Registered {adapter.adapter_id}: {source_id}")

# Perform initial ingestion
for adapter in adapters:
    store.ingest_from_adapter(adapter)
```

### Deployment Checklist

Before deploying, verify:

- [ ] **Mac side:**
  - [ ] Bind address is `0.0.0.0` (not `127.0.0.1`)
  - [ ] Ports 8001, 8002 are free and not firewalled
  - [ ] Each adapter has a unique `api_key`
  - [ ] Adapters are started before Linux backend attempts connection
  - [ ] Firewall allows inbound traffic on service ports

- [ ] **Linux side:**
  - [ ] Service URLs are reachable from Linux (test: `curl http://mac.local:8001/health`)
  - [ ] API keys match the Mac-side configuration
  - [ ] Network path is trusted (LAN or VPN)

- [ ] **Security:**
  - [ ] API keys are cryptographically generated (use `secrets.token_urlsafe(32)`)
  - [ ] API keys are stored in a secure location (e.g., environment variables, config file with restricted permissions)
  - [ ] Bearer tokens are rotated periodically
  - [ ] Services only accept connections from trusted networks

---

## Security Risks and Mitigations

### Bearer Token Over Plain HTTP

**Risk:** The API key is transmitted in the HTTP `Authorization` header without encryption. An attacker on the network can capture the token and impersonate the Linux backend.

**Affected deployments:**
- Model 1 (Bearer token over LAN/VPN) without VPN protection
- Any deployment using `http://` (not `https://`)

**Mitigation:**
1. **Use only on trusted networks:**
   - Isolated home LANs
   - Corporate LANs with network segmentation
   - VPN-protected connections (WireGuard, Tailscale, OpenVPN)

2. **Or switch to a secure model:**
   - Model 2 (mTLS) for cross-network deployments
   - Model 3 (SSH tunnel) if you have SSH infrastructure

3. **Monitor token usage:**
   - Audit adapter requests in logs
   - Rotate tokens if compromised
   - Use short-lived tokens if supported

### Service Port Exposure

**Risk:** If `host="0.0.0.0"`, the service accepts connections from any interface. An attacker on the internet can attempt to connect if the port is not firewalled.

**Mitigation:**
1. **Always use authentication:**
   - Set `api_key` on all exposed services
   - Use mTLS for untrusted networks

2. **Firewall the ports:**
   - Block inbound traffic on service ports from untrusted networks
   - Use host firewall rules (iptables, pfctl, Windows Firewall)
   - Use network firewall (router, cloud security group)

3. **Use SSH tunnel or VPN:**
   - Bind to `127.0.0.1` and access via SSH tunnel
   - Bind to `0.0.0.0` but only accept connections from VPN network

### Token Storage

**Risk:** API keys in plaintext in configuration files or code can be stolen if files are compromised.

**Mitigation:**
1. **Never hardcode tokens in source code**
2. **Use environment variables:**
   ```python
   import os
   api_key = os.environ.get("OBSIDIAN_API_KEY")
   serve_adapter(adapter, api_key=api_key)
   ```

3. **Use secure configuration management:**
   - systemd environment files (with restricted permissions)
   - Kubernetes secrets
   - Vault, 1Password, or similar secret storage

4. **Restrict file permissions:**
   ```bash
   chmod 600 /etc/context-lib/config.env  # Owner read/write only
   ```

### Certificate Expiration (mTLS)

**Risk:** Expired certificates will cause connection failures; if not monitored, the service may silently stop accepting connections.

**Mitigation:**
1. **Monitor certificate expiration:**
   ```bash
   openssl x509 -enddate -noout -in server.crt
   # notAfter=Mar 12 2026 ...
   ```

2. **Set up renewal automation:**
   - Use Let's Encrypt with auto-renewal for internet-facing services
   - Set calendar reminders for self-signed cert renewal

3. **Log certificate errors:**
   - Monitor HTTP 401/403 errors
   - Alert on SSL handshake failures

---

## Troubleshooting

### "Connection refused" on RemoteAdapter

**Check:**
1. Mac service is running:
   ```bash
   # On Mac
   ps aux | grep start_adapters
   ```

2. Port is listening:
   ```bash
   # On Mac
   lsof -i :8001  # or netstat -tlnp | grep 8001
   ```

3. Firewall allows the connection:
   ```bash
   # On Mac
   System Preferences > Security & Privacy > Firewall
   # Ensure port 8001 is allowed
   ```

4. Service is bound to `0.0.0.0` (not `127.0.0.1`):
   ```bash
   # On Mac, check binding
   netstat -tlnp | grep 8001
   # Should show 0.0.0.0:8001 (not 127.0.0.1:8001)
   ```

5. Connectivity from Linux:
   ```bash
   # On Linux
   ping mac.local
   curl http://mac.local:8001/health  # Should return 200 + JSON
   ```

### "401 Unauthorized" on fetch

**Check:**
1. API key is set on Mac side:
   ```python
   serve_adapter(adapter, api_key="your-secret-key")  # Must be set
   ```

2. API key matches on Linux side:
   ```python
   RemoteAdapter(service_url="...", api_key="your-secret-key")  # Must match
   ```

3. Bearer token is in the request:
   ```bash
   curl -H "Authorization: Bearer your-secret-key" \
        http://mac.local:8001/health
   ```

### "certificate verify failed" (mTLS)

**Check:**
1. CA certificate is correct on Linux:
   ```python
   httpx.Client(verify="/path/to/ca.crt")  # CA file must contain the root cert
   ```

2. Server certificate is signed by the CA:
   ```bash
   openssl verify -CAfile ca.crt server.crt
   # Should output: OK
   ```

3. Server certificate Subject Alternative Name (SAN) matches the service URL:
   ```bash
   openssl x509 -text -noout -in server.crt | grep -A1 "Subject Alternative Name"
   # Should include: DNS:mac.example.com or DNS:*.mac.local
   ```

### Service crashes with "OSError: [Errno 48] Address already in use"

**Check:**
1. Another process is using the port:
   ```bash
   lsof -i :8001  # Show what's using port 8001
   ```

2. Previous service didn't clean up socket:
   ```bash
   # Wait 30 seconds for TIME_WAIT socket to close
   # Or restart with SO_REUSEADDR if framework supports it
   ```

### Slow requests or timeouts

**Check:**
1. Network latency:
   ```bash
   ping mac.local  # Measure round-trip time
   ```

2. Adapter fetch is slow:
   - Check Mac adapter logs
   - Verify the underlying source (Obsidian, Apple services) is responsive

3. Request timeout setting:
   ```python
   RemoteAdapter(service_url="...", timeout=60)  # Increase from default 30s
   ```

---

## Summary

| Model | Security | Setup Complexity | Use Case |
|-------|----------|------------------|----------|
| **Bearer Token** | Medium (requires trusted network) | Low | Home LAN, VPN-protected |
| **mTLS** | High (certificate-based) | High | Cross-network, internet-facing |
| **SSH Tunnel** | High (leverages SSH) | Medium | Existing SSH infrastructure |
| **WireGuard** | High (VPN encryption) | Medium | Lightweight VPN setup |

Choose the deployment model based on your network security requirements and infrastructure:
- **Home/Lab:** Bearer token on LAN or SSH tunnel
- **Cross-network:** mTLS with certificate management
- **VPN-protected:** Bearer token via WireGuard/Tailscale

Always verify that:
1. Services bind to `0.0.0.0` for remote access (or `127.0.0.1` for tunnel/VPN)
2. API keys are unique, cryptographically generated, and securely stored
3. Network paths are trusted or encrypted
4. Services are firewalled from untrusted networks
