# Day 2 — Agent Integration, Security & Infrastructure as Code

## Overview

Day 2 focused on wiring together the full E2E system: LLM agent integration, command
sandboxing for security, and Terraform IaC to make all infrastructure reproducible.

**Goal:** Get a working E2E flow where a developer submits a natural language task via
HTTP, an AI agent executes it on the Raspberry Pi, and results are returned.

**Environment:**
- GCP project: `rodela-trial-project`
- GKE cluster: `pi-agent-cluster` (us-central1-a)
- Pi: `192.168.1.36` (office network)
- API: `http://34.44.129.194`

---

## Phase 1 — GKE API v3/v4 Deployment

### What Was Built

Replaced the Day 1 proxy Flask app with a full API server:

| Feature | Details |
|---------|---------|
| Auth | `X-API-Key` header validated against Secret Manager |
| Task queue | In-memory queue with background worker thread |
| `POST /tasks` | Accepts natural language task, returns `task_id` |
| `GET /tasks/{id}` | Returns task status and result |
| `GET /tasks` | Lists all tasks |
| `GET /pi/status` | Proxies Pi CPU/memory/disk metrics to developer |

### Secrets Required

| Secret | Purpose |
|--------|---------|
| `gke-api-key` | Developer authentication |
| `pi-tunnel-url` | Cloudflare tunnel URL to reach Pi |
| `pi-execute-token` | Auth token for Pi `/execute` endpoint |
| `anthropic-api-key` | Anthropic API key for Claude agent |

### Errors & Fixes

- **Issue:** `anthropic-api-key` secret didn't exist — pod crashed on startup
  - **Fix:** Created placeholder secret, updated with real key later
- **Issue:** Secret named `pi-tunnel-url` but code referenced `cloudflare-tunnel-url`
  - **Fix:** Updated code to match existing secret name
- **Issue:** `gcloud` not installed on Mac — all Day 1 work was on the Pi
  - **Fix:** Used GCP Cloud Shell for all GCP/GKE operations

---

## Phase 2 — Pi API Update

### What Was Built

Updated Pi Flask API with two new endpoints:

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /execute` | `X-Pi-Token` | Run a shell command, return output |
| `GET /status` | `X-Pi-Token` | Return CPU, memory, disk metrics |

### Errors & Fixes

- **Issue:** `scp -r` created `~/pi-api/pi-api/` instead of overwriting `~/pi-api/`
  - **Fix:** Built Docker image from `~/pi-api/pi-api/` path
- **Issue:** Old Docker image cached — new `app.py` not picked up
  - **Fix:** `docker build --no-cache`

---

## Phase 3 — LLM Agent Integration

### How the Agent Works

```
Developer submits: "check how much memory is available"
    ↓
GKE worker thread calls agent.py
    ↓
Claude receives task + run_command tool definition
    ↓
Claude calls run_command("free -h") → not found
Claude calls run_command("cat /proc/meminfo | head -5") → success
    ↓
Claude summarizes output in human-readable format
    ↓
Result stored, developer polls GET /tasks/{id}
```

### Key Design Decisions

- **One tool (`run_command`)** — flexible, Claude decides what to run
- **10-round limit** — prevents infinite agent loops
- **Tool result injection** — Pi's stdout/stderr fed back into Claude's context as `tool_result`

---

## Phase 4 — E2E Verification

```bash
# Submit task
curl -X POST http://34.44.129.194/tasks \
  -H "X-API-Key: <key>" \
  -d '{"description": "check how much memory is available"}'
# {"task_id": "6055d538-...", "status": "queued"}

# Poll result
curl http://34.44.129.194/tasks/6055d538-... -H "X-API-Key: <key>"
# {"status": "done", "result": {"summary": "Total: 8GB, Available: 7.3GB...", "commands_run": [...]}}
```

Full E2E working. ✅

---

## Phase 5 — Command Sandboxing (Security)

### Problem

The `/execute` endpoint previously ran commands directly via `subprocess.run(shell=True)`
inside the pi-api container — no network isolation, no resource limits, runs as root.

### Solution

Each command now runs in a throwaway Docker container (Docker-in-Docker):

```python
sandbox_cmd = [
    "docker", "run", "--rm",
    "--network=none",     # no internet access
    "--memory=512m",      # memory cap
    "--cpus=0.5",         # CPU cap
    "--user=nobody",      # unprivileged user
    "--stop-timeout=55",  # force kill after 55s
    "python:3.11-slim",
    "sh", "-c", command,
]
```

Pi API container runs with Docker socket mounted:
```bash
docker run -v /var/run/docker.sock:/var/run/docker.sock ...
```

### Tests

| Test | Result |
|------|--------|
| Normal command (`cat /proc/meminfo`) | ✅ Works |
| Network blocked (`curl http://google.com`) | ✅ Blocked |
| Container auto-cleanup | ✅ No leftover containers |
| Memory limits | ⚠️ Not enforced — Pi OS cgroup v2 limitation |

### Known Limitation — Memory Limits

Raspberry Pi OS Bookworm uses cgroup v2. Docker's `--memory` flag requires cgroup memory
accounting which is not enabled by default. `cgroup_enable=memory cgroup_memory=1` is
present in `/boot/firmware/cmdline.txt` but switching Docker to `cgroupfs` driver did not
resolve it.

**Impact:** Memory limits are not enforced. All other sandboxing protections work.
**Fix:** Enable cgroup v1 via kernel boot parameters or upgrade to a kernel with full
cgroup v2 memory support.

---

## Phase 6 — Terraform IaC

### What's Defined

All GCP infrastructure codified in `terraform/`:

| Resource | File |
|----------|------|
| GKE cluster + node pool | `main.tf` |
| Artifact Registry | `main.tf` |
| Service account + IAM bindings | `main.tf` |
| Secret Manager secrets (4) | `main.tf` |
| API enabling (3 APIs) | `main.tf` |

### Verification

```bash
terraform init   # ✅ Initialized with GCS backend
terraform plan   # ✅ 13 resources to add — matches existing infrastructure
```

**Note:** Plan shows `+ create` for all resources because existing resources were created
manually before Terraform was introduced. Running `terraform apply` on a fresh GCP project
would recreate everything from scratch. To bring existing resources under Terraform
management, `terraform import` would be needed for each resource.

### Errors & Fixes

- **Issue:** `replication { auto {} }` syntax invalid for google provider v5
  - **Fix:** Expanded to multi-line block syntax
- **Issue:** GCS backend bucket didn't exist
  - **Fix:** `gsutil mb gs://rodela-trial-project-tfstate`

---

## Phase 7 — Tailscale (Replace Cloudflare)

### Problem with Cloudflare
- Tunnel URL changes on every Pi restart
- Mitigated by saving URL to Secret Manager but fragile
- HTTP relay through Cloudflare servers — not end-to-end encrypted
- HTTP only, no SSH support

### Tailscale Solution
- Pi joins Tailscale network → gets stable IP `100.103.122.25` (never changes)
- GKE pod runs Tailscale sidecar → joins same network
- Agent routes Pi traffic through Tailscale SOCKS5 proxy (`localhost:1055`)
- WireGuard encrypted peer-to-peer — no relay

### Steps
1. Installed Tailscale on Pi: `curl -fsSL https://tailscale.com/install.sh | sh`
2. Authenticated Pi to personal Tailscale account
3. Pi Tailscale IP: `100.103.122.25` (stable)
4. Created Tailscale auth key (reusable, ephemeral) → stored in Secret Manager
5. Created Kubernetes Secret for Tailscale auth key
6. Added Tailscale sidecar container to GKE deployment
7. Updated `pi-tunnel-url` secret to `http://100.103.122.25:8080`
8. Updated `agent.py` to pass SOCKS5 proxy only for Pi requests

### Errors & Fixes
- **Issue:** Pi authenticated to wrong Tailscale account (work email)
  - **Fix:** `sudo tailscale logout` then re-auth with personal account
- **Issue:** Tailscale sidecar failed — missing RBAC for K8s secret
  - **Fix:** Added `TS_KUBE_SECRET=""` to disable K8s state storage
- **Issue:** `ALL_PROXY` routed Anthropic API calls through SOCKS5 — httpx missing `socksio`
  - **Fix:** Removed `ALL_PROXY`, passed proxy explicitly only in `_execute_on_pi()`
- **Issue:** Old `ALL_PROXY` still set on running pod after deployment update
  - **Fix:** `kubectl set env deployment/pi-api ALL_PROXY="" NO_PROXY=""`

### Verification
```bash
# E2E through Tailscale
curl -X POST http://34.44.129.194/tasks \
  -H "X-API-Key: <key>" \
  -d '{"description": "check disk space on the device"}'
# Agent ran df -h + lsblk, returned full disk summary ✅
```

---

## Architecture (End of Day 2)

```
Developer
    │  POST /tasks + X-API-Key
    ▼
GCP Load Balancer (34.44.129.194:80)
    │
    ▼
Flask API — GKE Pod (v5)
    ├── Auth middleware (Secret Manager)
    ├── Task queue (in-memory)
    └── Background worker
            │  Anthropic API (direct)
            ▼
        Claude agent (run_command tool)
            │  SOCKS5 proxy → Tailscale sidecar
            ▼
        WireGuard (peer-to-peer encrypted)
            │
            ▼
        Pi Tailscale IP (100.103.122.25:8080)
            │  X-Pi-Token
            ▼
        Pi Flask API (Docker, port 8080)
            │
            ▼
        Sandbox container (python:3.11-slim)
            --network=none --cpus=0.5 --rm
```

---

## Remaining Work

- [ ] HTTPS on GKE LoadBalancer
- [ ] `terraform import` existing resources into state
- [ ] Update Terraform to include Tailscale secret
- [ ] Pi setup script end-to-end test
- [ ] Day 3 demo preparation
