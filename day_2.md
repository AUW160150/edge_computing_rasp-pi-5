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
Flask API — GKE Pod
    ├── Auth middleware (Secret Manager)
    ├── Task queue (in-memory, serialized — one agent at a time)
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

## Phase 8 — Terraform: Full Import & Workload Identity

### Problem
All resources were created manually before Terraform was introduced. Running `terraform plan`
showed all resources as `+ create` — Terraform had no state.

### Solution
Imported all existing resources into Terraform state via `terraform import`:

```bash
terraform import google_container_cluster.pi_agent ...
terraform import google_container_node_pool.pi_agent_nodes ...
terraform import google_artifact_registry_repository.pi_agent ...
# ... all secrets, IAM bindings, APIs
```

Also added Workload Identity Federation resources to `main.tf` (previously manual):

| Resource | Purpose |
|----------|---------|
| `google_service_account.github_actions` | SA for GitHub Actions CI |
| `google_iam_workload_identity_pool.github` | WI pool — trusts GitHub OIDC |
| `google_iam_workload_identity_pool_provider.github` | WI provider with `attribute_condition` restricting to `Asari-AI/rodela-trial-project` |
| `google_service_account_iam_member.github_actions_wi` | Binds repo to SA |
| `google_project_iam_member.github_actions_*` | GKE deploy + AR push permissions |

### Result
```bash
terraform plan  # No changes. Your infrastructure matches the configuration. ✅
```

### Key Fixes
- **Issue:** Node pool `lifecycle { ignore_changes = all }` needed — service_account field mismatch between `"default"` and full SA email caused destroy plan
- **Issue:** WI provider `attribute_condition` must be preserved — removing it would allow any GitHub repo to authenticate
- **Issue:** WI binding repo was `Asari-AI/rodela-trial-project` not `rodela/rodela-trial-project`

---

## Phase 9 — Observability

### Phase 9.1 — Structured Logging

Added Python `logging` to `app.py` and `agent.py`. GKE ships stdout to Cloud Logging automatically.

Key log events:
- Task queued, started, completed, failed
- Each agent command run on Pi
- Unauthorized access attempts (IP logged)
- Pi connectivity errors

```bash
kubectl logs deployment/pi-api -c pi-api -f
# 2026-04-02 21:10:56 INFO Task fa20b26a queued: check CPU temperature
# 2026-04-02 21:10:56 INFO Task fa20b26a started
# 2026-04-02 21:10:59 INFO Task fa20b26a agent running command: vcgencmd measure_temp
# 2026-04-02 21:11:07 INFO Task fa20b26a completed successfully
```

### Phase 9.2 — Real-time SSE Agent Progress

Updated SSE stream to emit granular agent events as they happen:

| Event type | When emitted | Content |
|-----------|-------------|---------|
| `system` | Infrastructure hops | GKE received, worker started, Anthropic called, Tailscale routing, Pi responded |
| `thought` | Claude reasons | Agent's planning text |
| `command` | Before Pi call | Command string |
| `output` | After Pi responds | stdout/stderr |
| `summary` | Task complete | Claude's final summary |
| `status` | State change | queued/running/done/error/cancelled |
| `result` | Terminal | Full result object |

Developer connects once to `/tasks/{id}/stream` and receives the full infrastructure trail in real time.

### Phase 9.3 — Pi Liveness Monitor

Added background thread in GKE pod that pings Pi every 30 seconds:

- `pi_health` dict tracks `{online, last_checked, error}`
- `GET /health` exposes API + Pi status (no auth required)
- `POST /tasks` rejects immediately with 503 if Pi is known offline — no point queuing

```bash
curl http://34.44.129.194/health
# {"api": "ok", "pi": {"online": true, "last_checked": 1775167683.4, "error": null}}
```

---

## Phase 10 — Security Hardening

### Tailscale ACLs

Configured access control policy in Tailscale admin console:

```json
{
  "tagOwners": {
    "tag:gke": ["autogroup:admin"],
    "tag:pi": ["autogroup:admin"]
  },
  "grants": [
    {"src": ["tag:gke"], "dst": ["tag:pi"], "ip": ["tcp:8080"]},
    {"src": ["autogroup:member"], "dst": ["autogroup:self"], "ip": ["*"]}
  ]
}
```

- Pi tagged as `tag:pi`
- GKE pod uses a tagged auth key → auto-joins as `tag:gke`
- Only `tag:gke` can reach `tag:pi` on port 8080 — all other tailnet devices blocked

### Additional Security Items
- `service.yaml` added to repo (was missing — LoadBalancer existed only in GCP)
- `pi-setup/setup.sh` updated to use Tailscale instead of Cloudflare

---

## Phase 11 — Task Cancellation

Added `DELETE /tasks/{id}` endpoint:

- Sets `task["cancelled"] = True`
- Agent checks flag between rounds — stops cleanly after current Pi command completes
- Status transitions to `"cancelled"`, result set to `{"summary": "Task was cancelled."}`
- SSE stream emits the cancellation event

```bash
curl -X DELETE http://34.44.129.194/tasks/<task_id> -H "X-API-Key: <key>"
# {"task_id": "...", "status": "cancelling"}
```

---

## Phase 12 — Developer Frontend

Built a single-page dashboard at `dashboard/index.html` (served via `python3 -m http.server 8000`):

| Panel | Description |
|-------|-------------|
| Auth | API key input, connection validation, session storage |
| Task Form | Natural language task submission, Pi-offline guard |
| Live Feed | Real-time SSE stream — system trail, agent thoughts, commands, output |
| Result Panel | Final summary + commands table, vertically resizable |
| Pi Status | CPU/memory/disk progress bars, auto-refreshed |
| Task History | All tasks with status, click to reload stream |
| Header | Pi online/offline pill, health polling |

Key implementation detail: `EventSource` doesn't support custom headers — used `fetch()` + `ReadableStream` to manually parse SSE frames with `X-API-Key` header.

CORS enabled on GKE API (`flask-cors`) to allow browser requests from localhost.

---

## Phase 13 — CI/CD Fix

Fixed hardcoded image tag `v4` in `deployment.yaml`:
- CI now pushes both `:<git-sha>` (traceability) and `:latest` (fresh provisioning)
- `deployment.yaml` updated to use `:latest`

---

## Architecture (End of Day 2 — Updated)

```
Developer (browser / curl)
    │  POST /tasks + X-API-Key
    ▼
GCP Load Balancer (34.44.129.194:80)
    │
    ▼
Flask API — GKE Pod
    ├── Auth middleware (Secret Manager)
    ├── Pi liveness monitor (background thread, 30s interval)
    ├── Task queue (serialized — prevents Pi resource conflicts)
    └── Background worker
            │  emit() → SSE stream (system trail + agent events)
            │  Anthropic API (direct, no proxy)
            ▼
        Claude agent — run_command tool (max 10 rounds, cancellable)
            │  SOCKS5 proxy (localhost:1055) → Tailscale sidecar
            ▼
        WireGuard peer-to-peer (tag:gke → tag:pi ACL enforced)
            │
            ▼
        Pi Flask API (100.103.122.25:8080, X-Pi-Token auth)
            │
            ▼
        Docker sandbox (python:3.11-slim)
            --network=none --cpus=0.5 --memory=512m --user=nobody --rm
```

---

## Known Limitations

| Limitation | Impact | Production Fix |
|-----------|--------|----------------|
| Memory limits not enforced on Pi | Sandbox can use unlimited RAM | Enable cgroup v1 or upgrade kernel |
| Tasks in-memory only | Lost on pod restart | Redis / Cloud Firestore |
| HTTP not HTTPS | API key in plaintext | GCP managed cert + Ingress |
| Single worker thread | Tasks queue serially | Correct for single Pi — add mutex if scaling |
| K8s `tailscale-auth-key` secret manual | Not in Terraform | Add Kubernetes Terraform provider |

---

## Completed ✅

- [x] Terraform fully imported — `terraform plan` clean
- [x] Workload Identity in Terraform
- [x] Tailscale ACLs configured
- [x] Structured logging
- [x] Real-time SSE agent trail
- [x] Pi liveness monitor + /health
- [x] Task cancellation endpoint
- [x] Developer frontend dashboard
- [x] PROVISIONING.md written
- [x] service.yaml in repo
- [x] CI/CD image tag fixed
