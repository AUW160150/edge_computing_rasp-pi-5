# Provisioning Guide

Complete instructions for recreating this infrastructure from scratch on a new GCP project and Raspberry Pi.

## Prerequisites

- [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Docker](https://docs.docker.com/get-docker/)
- A [Tailscale](https://tailscale.com) account
- An Anthropic API key

---

## 1. Bootstrap Terraform State

Terraform stores state in GCS. Create the bucket before running `terraform init`:

```bash
gsutil mb gs://rodela-trial-project-tfstate
```

---

## 2. Apply Terraform

This creates the GKE cluster, Artifact Registry, IAM bindings, and Secret Manager secrets (empty shell — values set in step 3).

```bash
cd terraform
terraform init
terraform apply
```

Takes ~5 minutes. Outputs the cluster name, zone, registry URL, and node service account.

---

## 3. Populate GCP Secrets

All secrets are created empty by Terraform. Populate each with a real value:

```bash
# API key for developers — generate a random string
openssl rand -hex 32 | gcloud secrets versions add gke-api-key --data-file=-

# Tailscale IP of the Pi (get this after Pi setup in step 6)
echo -n "http://100.x.x.x:8080" | gcloud secrets versions add pi-tunnel-url --data-file=-

# Auth token for Pi /execute endpoint — must match what you pass to setup.sh
openssl rand -hex 32 | gcloud secrets versions add pi-execute-token --data-file=-

# Anthropic API key
echo -n "sk-ant-..." | gcloud secrets versions add anthropic-api-key --data-file=-

# Tailscale auth key — create a reusable key at https://login.tailscale.com/admin/settings/keys
echo -n "tskey-auth-..." | gcloud secrets versions add tailscale-auth-key --data-file=-
```

---

## 4. Configure kubectl

```bash
gcloud container clusters get-credentials pi-agent-cluster --zone=us-central1-a --project=rodela-trial-project
```

---

## 5. Create Kubernetes Secret for Tailscale

The Tailscale sidecar in the GKE pod reads its auth key from a K8s secret:

```bash
TSKEY=$(gcloud secrets versions access latest --secret=tailscale-auth-key)
kubectl create secret generic tailscale-auth-key --from-literal=key="$TSKEY"
```

---

## 6. Build and Deploy GKE API

```bash
# Configure Docker for Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build and push (AMD64 for GKE)
docker build --platform linux/amd64 \
  -t us-central1-docker.pkg.dev/rodela-trial-project/pi-api-repo/pi-agent-api:latest \
  ./gke-api
docker push us-central1-docker.pkg.dev/rodela-trial-project/pi-api-repo/pi-agent-api:latest

# Deploy
kubectl apply -f gke-api/deployment.yaml
kubectl apply -f gke-api/service.yaml
kubectl rollout status deployment/pi-api
```

After deploying, get the external IP:

```bash
kubectl get svc pi-api
```

---

## 7. Set Up the Raspberry Pi

### 7a. Flash OS

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Flash **Raspberry Pi OS Lite (64-bit)** to the microSD card
3. In Imager settings: enable SSH, set username/password, configure WiFi or use Ethernet

### 7b. Run Setup Script

SSH into the Pi, then from the repo root:

```bash
# Get the pi-execute-token you set in step 3
PI_TOKEN=$(gcloud secrets versions access latest --secret=pi-execute-token)
TSKEY=$(gcloud secrets versions access latest --secret=tailscale-auth-key)

scp -r pi-setup/ pi-api/ <pi-user>@<pi-ip>:~/setup/
ssh <pi-user>@<pi-ip> "bash ~/setup/pi-setup/setup.sh $PI_TOKEN $TSKEY"
```

The script installs Docker, joins Tailscale, and starts the pi-api container.

### 7c. Get the Pi's Tailscale IP

After setup, find the Pi's stable Tailscale IP:

```bash
ssh <pi-user>@<pi-ip> tailscale ip -4
```

Update the `pi-tunnel-url` secret with this IP (if different from what you set in step 3):

```bash
echo -n "http://100.x.x.x:8080" | gcloud secrets versions add pi-tunnel-url --data-file=-
```

Then restart the GKE pod to pick up the new secret:

```bash
kubectl rollout restart deployment/pi-api
```

---

## 8. CI/CD Setup (GitHub Actions)

The deploy workflow uses Workload Identity Federation. These are one-time manual steps:

### 8a. Create Service Account

```bash
gcloud iam service-accounts create github-actions-sa \
  --display-name="GitHub Actions"

gcloud projects add-iam-policy-binding rodela-trial-project \
  --member="serviceAccount:github-actions-sa@rodela-trial-project.iam.gserviceaccount.com" \
  --role="roles/container.developer"

gcloud projects add-iam-policy-binding rodela-trial-project \
  --member="serviceAccount:github-actions-sa@rodela-trial-project.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

### 8b. Create Workload Identity Pool

```bash
gcloud iam workload-identity-pools create github-pool \
  --location=global

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --workload-identity-pool=github-pool \
  --location=global \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"

gcloud iam service-accounts add-iam-policy-binding github-actions-sa@rodela-trial-project.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/1004672478893/locations/global/workloadIdentityPools/github-pool/attribute.repository/rodela/rodela-trial-project"
```

### 8c. Add GitHub Secrets

In the GitHub repo settings → Secrets, add:

| Secret | Value |
|--------|-------|
| `TAILSCALE_AUTHKEY` | Tailscale reusable auth key |
| `PI_SSH_KEY` | Private SSH key for Pi access |
| `PI_EXECUTE_TOKEN` | Same token as `pi-execute-token` in Secret Manager |

---

## Verification

```bash
# Health check
curl http://<EXTERNAL-IP>/

# Pi status (tests full Tailscale connectivity)
curl -H "X-API-Key: <gke-api-key>" http://<EXTERNAL-IP>/pi/status

# End-to-end agent task
curl -X POST http://<EXTERNAL-IP>/tasks \
  -H "X-API-Key: <gke-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"description": "What OS is running on the Pi?"}'
```

---

## Architecture

```
Developer
    │  POST /tasks + X-API-Key
    ▼
GCP Load Balancer (port 80)
    │
    ▼
Flask API — GKE Pod
    ├── Auth middleware (Secret Manager)
    ├── In-memory task queue
    └── Background worker thread
            │  Anthropic API (direct)
            ▼
        Claude agent (run_command tool)
            │  SOCKS5 proxy → Tailscale sidecar (localhost:1055)
            ▼
        WireGuard peer-to-peer (encrypted)
            │
            ▼
        Pi Tailscale IP (100.103.122.25:8080)
            │  X-Pi-Token
            ▼
        Pi Flask API (Docker, port 8080)
            │
            ▼
        Sandbox container (python:3.11-slim)
            --network=none --cpus=0.5 --memory=512m --rm
```
