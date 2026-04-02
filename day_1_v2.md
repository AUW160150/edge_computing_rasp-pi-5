# Day 1 (Part 2) — Codebase Setup & GKE v3 Deployment

## Overview

With the Pi inaccessible due to WiFi, this session focused on building out the full
codebase that was previously only set up manually, and deploying an upgraded GKE API
with authentication and task queuing.

**Environment:**
- Working from Mac (no Pi access)
- Cloud Shell for GCP/GKE operations
- GCP project: `rodela-trial-project`

---

## What Was Built

### Repository Structure

All infrastructure and application code committed to the repo for the first time:

```
rodela-trial-project/
  gke-api/
    app.py           — Flask API with auth, task queue, background worker
    agent.py         — Anthropic Claude agent with run_command tool
    Dockerfile       — AMD64 image for GKE
    requirements.txt

  pi-api/
    app.py           — Updated Pi Flask API with /execute and /status endpoints
    Dockerfile       — ARM64 image for Pi
    requirements.txt

  terraform/
    main.tf          — GKE cluster, Artifact Registry, IAM, Secret Manager secrets
    variables.tf
    outputs.tf

  pi-setup/
    setup.sh         — Full Pi setup from blank OS in one script
```

---

## Phase 1 — GKE API v3

### What Changed from v2

| Feature | v2 | v3 |
|---------|----|----|
| Auth | None | `X-API-Key` header checked against Secret Manager |
| Endpoints | `/`, `/ping` | `/`, `/tasks` (POST/GET), `/tasks/{id}` (GET) |
| Agent | None | Anthropic Claude with `run_command` tool |
| Task queue | None | In-memory queue with background worker thread |

### Secrets Required

| Secret Name | Purpose |
|-------------|---------|
| `gke-api-key` | API key for developer auth |
| `pi-tunnel-url` | Cloudflare tunnel URL to reach Pi |
| `pi-execute-token` | Token for Pi `/execute` endpoint auth |
| `anthropic-api-key` | Anthropic API key for agent (placeholder for now) |

### Errors & Fixes

- **Issue:** `gcloud` not installed on Mac — all Day 1 work was done on the Pi
  - **Fix:** Used GCP Cloud Shell (browser terminal) for all GCP operations
- **Issue:** `gh repo clone` failed — not authenticated
  - **Fix:** Ran `gh auth login` in Cloud Shell first
- **Issue:** `./gke-api` not found during docker build
  - **Fix:** Code was only on Mac, not pushed to GitHub yet — committed and pushed first
- **Issue:** Pod would crash on startup — `anthropic-api-key` secret didn't exist
  - **Fix:** Created placeholder secret in Secret Manager; will update with real key tomorrow
- **Issue:** Secret named `pi-tunnel-url` but code used `cloudflare-tunnel-url`
  - **Fix:** Updated code to match existing secret name

---

## Phase 2 — Verification

```bash
# Health check
curl http://34.44.129.194/
# {"service":"pi-agent-api","status":"ok"}

# Auth check (no key)
curl http://34.44.129.194/tasks
# {"error":"Unauthorized"}

# Auth check (with key)
curl http://34.44.129.194/tasks -H "X-API-Key: <key>"
# []
```

All checks passed. ✅

---

## Architecture (Current State)

```
Developer
    ↓  HTTP + X-API-Key header
GCP Load Balancer (34.44.129.194)
    ↓
Flask API in GKE pod (v3)
    ├── Auth middleware
    ├── Task queue (in-memory)
    └── Background worker
            ↓  Anthropic API (placeholder key)
        Claude agent
            ↓  POST /execute + X-Pi-Token
        Cloudflare tunnel URL (from Secret Manager)
            ↓
        cloudflared on Pi
            ↓
        Flask API in Docker on Pi (port 8080) ← NOT YET UPDATED
```

---

## Remaining for Day 2

- [ ] Get Pi access — redeploy pi-api with `/execute` and `/status` endpoints
- [ ] Add real Anthropic API key to Secret Manager
- [ ] Test full E2E: POST /tasks → agent → Pi → response
- [ ] Terraform: provision GCS bucket for state, run `terraform init` and `terraform plan`
