# Local Startup Guide
> This file is local-only (not committed). Read this at the start of a session to re-establish context and get everything running.

---

## What Is Running Where

| Component | Where | Always on? |
|---|---|---|
| GKE Flask API | GCP us-central1-a · `34.44.129.194:80` | Yes — K8s keeps it up |
| Tailscale sidecar | Same GKE pod | Yes — sidecar container |
| Raspberry Pi 5 | Home network · Tailscale IP `100.103.122.25` | Needs to be powered on |
| Pi Flask API | Running on Pi · `:8080` | Yes — Docker `--restart always` |
| Dashboard | Local file · `dashboard/index.html` | Open manually |

---

## Step 1 — Verify GKE Pod Is Up

```bash
# Authenticate (if gcloud session expired)
gcloud auth login
gcloud container clusters get-credentials pi-agent-cluster --zone=us-central1-a --project=rodela-trial-project

# Check pod status — should show Running
kubectl get pods

# Check logs if something looks wrong
kubectl logs deployment/pi-api -c pi-api --tail=50
```

---

## Step 2 — API Key (X-API-Key)

```
c6dea99f1b4012500197ee898ed02dc43e8a9a98a04a7d2eb62600f032ca852b
```

Use this as the `X-API-Key` header when calling the API or authenticating the dashboard.
To re-fetch from Secret Manager if rotated:
```bash
gcloud secrets versions access latest --secret=gke-api-key --project=rodela-trial-project
```

Copy the output — you'll need it to authenticate the dashboard.

---

## Step 3 — Open the Dashboard

```bash
open dashboard/index.html
```

- Paste the API key into the auth box and click **Authenticate**
- It will probe the API and confirm it's live
- Pi status (CPU/memory/disk) should appear if Pi is on and Tailscale-connected

---

## Step 4 — Verify Pi Is Reachable

```bash
# Quick health check through the API
curl -H "X-API-Key: <key>" http://34.44.129.194/pi/status
```

Expected: `{"cpu_percent": ..., "memory": {...}, "disk": {...}}`

If you get a timeout or error: Pi is either off or Tailscale has dropped. SSH into Pi and check:

```bash
ssh rodela_asari@100.103.122.25
sudo tailscale status        # should show the GKE node as a peer
docker ps                    # should show pi-api running
```

---

## Step 5 — Run a Test Task

```bash
KEY=$(gcloud secrets versions access latest --secret=gke-api-key --project=rodela-trial-project)

# Submit task
TASK=$(curl -s -X POST http://34.44.129.194/tasks \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"description":"What is the current Pi CPU temperature?"}')

echo $TASK   # grab the task_id

# Stream results
curl -s -N -H "X-API-Key: $KEY" \
  http://34.44.129.194/tasks/<task_id>/stream
```

Or just type the task in the dashboard and watch the live feed.

---

## Key IDs & Endpoints

| Thing | Value |
|---|---|
| GCP Project | `rodela-trial-project` |
| GKE Cluster | `pi-agent-cluster` · `us-central1-a` |
| API endpoint | `http://34.44.129.194` |
| Pi Tailscale IP | `100.103.122.25` |
| Pi SSH user | `rodela_asari` |
| K8s deployment | `pi-api` |
| Artifact Registry | `us-central1-docker.pkg.dev/rodela-trial-project/pi-api-repo/pi-agent-api` |
| GitHub repo | `Asari-AI/rodela-trial-project` |

---

## Secrets in GCP Secret Manager

| Secret name | What it is |
|---|---|
| `gke-api-key` | X-API-Key for developer → GKE auth |
| `anthropic-api-key` | Claude API key |
| `pi-tunnel-url` | Pi's Tailscale URL |
| `pi-execute-token` | X-Pi-Token for GKE → Pi auth |
| `tailscale-auth-key` | Used by GKE Tailscale sidecar |

---

## If the GKE Pod Is Crashlooping

```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name> -c pi-api --previous
```

Common causes:
- Secret not found → check GCP Secret Manager values are set
- Tailscale auth key expired → generate new tagged key in Tailscale admin, update K8s secret:
  ```bash
  kubectl create secret generic tailscale-auth-key --from-literal=key=<new-key> --dry-run=client -o yaml | kubectl apply -f -
  kubectl rollout restart deployment/pi-api
  ```

---

## CI/CD — How Deploys Work

- Push to `main` → GitHub Actions builds Docker image, pushes `:latest` + `:<git-sha>` to Artifact Registry, runs `kubectl set image` to roll out
- Pi deploy only triggers if files in `pi-api/` are modified

---

## Presentation

```bash
open presentation.html   # 12-slide HTML deck, arrow keys to navigate
```
- Slide 11: Live Demo — click "Open Dashboard" to open dashboard/index.html
- Slide 12: Roadblocks — also has the live demo link
