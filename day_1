  # Day 1 — Raspberry Pi 5 Setup & GCP Infrastructure

  ## Overview

  This document covers the full setup of a Raspberry Pi 5 as an edge compute device connected to GCP, including all errors
  encountered and how they were resolved.

  **Goal:** Set up the Pi as an edge compute sandbox, deploy an HTTP API server to GKE, and establish communication between GKE
  agents and the Pi over a Cloudflare tunnel.

  **Environment:**
  - Device: Raspberry Pi 5
  - OS: Raspberry Pi OS (64-bit)
  - Remote access: SSH from Mac
  - Cloud: GCP project `rodela-trial-project`

  ---

  ## Phase 1 — Verify the Coding Environment

  ### Steps
  1. Opened LXTerminal on the Pi desktop
  2. Confirmed Python version: `python3 --version` → `Python 3.13.5`
  3. Ran a Hello World one-liner: `python3 -c "print('Hello, World')"`
  4. Created `hello.py` in Geany, saved to Desktop, ran from terminal: `python3 ~/Desktop/hello.py`

  ### Errors & Fixes
  - **Issue:** Accidentally opened Python interactive shell and couldn't exit
    - **Fix:** Use `Ctrl+D` to exit Python interactive shell
  - **Issue:** Wrong quote style in `python3 -c` command broke execution
    - **Fix:** Use double quotes on outside, single quotes inside: `python3 -c "print('Hello, World')"`

  ---

  ## Phase 2 — Enable SSH

  ### Steps
  1. Enabled SSH via Raspberry Pi Configuration → Interfaces → SSH
  2. Found Pi's local IP: `hostname -I` → `192.168.1.36`
  3. Connected from Mac: `ssh rodela_asari@192.168.1.36`

  ### Errors & Fixes
  - **Issue:** `ssh: connect to host 192.168.136 port 22: Connection refused`
    - **Fix:** Typo in IP address — correct IP is `192.168.1.36`

  ---

  ## Phase 3 — Docker Container Isolation

  ### Steps
  1. Installed Docker: `curl -sSL https://get.docker.com | sh`
  2. Added user to Docker group: `sudo usermod -aG docker rodela_asari`
  3. Logged out and back in via SSH
  4. Verified: `docker --version` → `Docker version 29.3.1`
  5. Tested with hello-world: `docker run hello-world`
  6. Created project folder with `hello.py` and a `Dockerfile`
  7. Built and ran container: confirmed isolated Python execution

  ### Key Concepts
  - `--rm` flag removes the container after it runs
  - Dockerfile = recipe for what goes inside the container
  - `COPY hello.py .` inside Dockerfile copies from host into container

  ---

  ## Phase 4 — GCP Authentication

  ### Steps
  1. Installed gcloud CLI: `curl https://sdk.cloud.google.com | bash`
  2. Verified: `gcloud --version` → `Google Cloud SDK 563.0.0`
  3. Authenticated: `gcloud auth login --no-launch-browser`
  4. Set project: `gcloud config set project rodela-trial-project`
  5. Verified: `gcloud config list`

  ---

  ## Phase 5 — Cloudflare Tunnel (NAT/Firewall Solution)

  ### Problem
  Pi has a private IP (`192.168.1.36`) behind office NAT. GCP cannot initiate connections to it directly.

  ### Solution
  Cloudflare Tunnel — Pi initiates outbound connection to Cloudflare, which acts as a relay. GKE calls the Cloudflare public URL,
  which forwards traffic through the tunnel to the Pi.

  ### Steps
  1. Installed cloudflared on Pi
  2. Tested quick tunnel: `cloudflared tunnel --url http://localhost:8080`
  3. Created systemd service for permanent tunnel

  ### systemd service `/etc/systemd/system/cloudflared.service`
  [Unit]
  Description=Cloudflare Tunnel
  After=network.target

  [Service]
  ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:8080
  ExecStartPost=/bin/bash -c 'sleep 15 && /home/rodela_asari/update-tunnel-url.sh'
  Restart=always                              
  User=rodela_asari                       
                                                                                                                                    
  [Install]                                                                                                                         
  WantedBy=multi-user.target                                                                                                        
                                                                                                                                    
  ### Errors & Fixes                                        
  - **Issue:** `cloudflared service install` failed — requires named tunnel with domain
    - **Fix:** Created systemd service manually
  - **Issue:** Cloudflare URL changes on every restart                                                                              
    - **Fix:** Created `update-tunnel-url.sh` to save current URL to GCP Secret Manager automatically
                                                                                                                                    
  ---                                                       
                                                                                                                                    
  ## Phase 6 — Flask API Server on Pi                                                                                               
                                                                                                                                    
  ### Steps                                                                                                                         
  1. Created Python venv: `python3 -m venv ~/rodela`        
  2. Activated: `source ~/rodela/bin/activate`
  3. Installed Flask: `pip3 install flask`
  4. Created `~/pi-api/app.py` with `/` and `/ping` endpoints
  5. Created `Dockerfile` and `requirements.txt`                                                                                    
  6. Built Docker image: `docker build -t pi-api ~/pi-api`
  7. Ran container: `docker run -d -p 8080:8080 --name pi-api --restart always pi-api`                                              
  8. Tested via Cloudflare URL → confirmed `pong` response                                                                          
                                                                                                                                    
  ### Errors & Fixes                                                                                                                
  - **Issue:** `pip3 install flask` → `externally-managed-environment` error                                                        
    - **Fix:** Use a Python virtual environment                                                                                     
  - **Issue:** `IndentationError` in app.py                                                                                         
    - **Fix:** Python is strict about indentation — used `cat > file << 'EOF'` to write cleanly                                     
  - **Issue:** `address already in use` on port 8080                                                                                
    - **Fix:** `sudo fuser -k 8080/tcp`   
  - **Issue:** Container name conflict                                                                                              
    - **Fix:** `docker rm pi-api` before re-running                                                                                 
                                              
  ---                                                                                                                               
                                                            
  ## Phase 7 — GCP Artifact Registry & GKE                                                                                          
                                                            
  ### Steps                                                                                                                         
  1. Enabled APIs: `gcloud services enable container.googleapis.com artifactregistry.googleapis.com`
  2. Created Artifact Registry repo in `us-central1`
  3. Configured Docker auth: `gcloud auth configure-docker us-central1-docker.pkg.dev`                                              
  4. Tagged and pushed image to GCP       
                                                                                                                                    
  ### Errors & Fixes                                                                                                                
  - **Issue:** Multi-line gcloud commands broke with `unrecognized arguments`
    - **Fix:** Always run gcloud commands as a single line                                                                          
                                                            
  ---
                                                                                                                                    
  ## Phase 8 — GKE Cluster Setup
                                                                                                                                    
  ### Cluster creation command                              
  gcloud container clusters create pi-agent-cluster
    --zone=us-central1-a                           
    --num-nodes=1                                                                                                                   
    --machine-type=e2-small
    --scopes=cloud-platform                                                                                                         
    --enable-autoscaling                                    
    --min-nodes=1                         
    --max-nodes=10
                                                                                                                                    
  ### Steps
  1. Installed kubectl and gke-gcloud-auth-plugin                                                                                   
  2. Connected kubectl to cluster                           
  3. Deployed image: `kubectl create deployment pi-api --image=...`
  4. Exposed: `kubectl expose deployment pi-api --type=LoadBalancer --port=80 --target-port=8080`
                                                                                                                                    
  ### Errors & Fixes
  - **Issue:** `ImagePullBackOff` — GKE couldn't pull from Artifact Registry                                                        
    - **Fix:** Granted IAM role `roles/artifactregistry.reader` to compute service account
  - **Issue:** `no match for platform in manifest` — Pi is ARM64, GKE is AMD64                                                      
    - **Fix:** Rebuilt image for AMD64 using `docker buildx build --platform linux/amd64`
    - Required: `docker run --privileged --rm tonistiigi/binfmt --install all`                                                      
  - **Issue:** GKE cached old `latest` image  
    - **Fix:** Use explicit version tags (`v2`, `v3`) instead of `latest`                                                           
  - **Issue:** `PERMISSION_DENIED: insufficient authentication scopes` for Secret Manager
    - **Fix:** Recreated cluster with `--scopes=cloud-platform` — OAuth scopes cannot be changed after cluster creation             
                                                            
  ---                                                                                                                               
                                                            
  ## Phase 9 — Connecting GKE to Pi via Secret Manager                                                                              
                                                            
  ### Problem                                                                                                                       
  GKE needs the Pi's Cloudflare URL, but it changes on every restart.
                                              
  ### Solution                            
  Store the URL in GCP Secret Manager. Pi updates it on restart. GKE reads it dynamically.
                                                                                                                                    
  ### Steps
  1. Enabled Secret Manager API                                                                                                     
  2. Created `~/update-tunnel-url.sh` on Pi                 
  3. Added `ExecStartPost` to cloudflared service to run script on startup
  4. Granted GKE access: `roles/secretmanager.secretAccessor`
  5. Updated GKE `app.py` to read URL from Secret Manager                                                                           
  6. Rebuilt as `v2`, redeployed          
                                                                                                                                    
  ### Errors & Fixes                                                                                                                
  - **Issue:** After recreating cluster, Secret Manager had stale URL
    - **Fix:** Manually run `~/update-tunnel-url.sh` after any tunnel restart                                                       
                                                            
  ---                                                                                                                               
                                                            
  ## Final Architecture                       
                                          
  Developer / Browser
          ↓                                                                                                                         
  GCP Load Balancer (34.44.129.194)
          ↓                                                                                                                         
  Flask API in GKE pod                                      
          ↓  reads URL from Secret Manager
  Cloudflare tunnel URL
          ↓
  cloudflared on Pi (office network)          
          ↓                               
  Flask API in Docker on Pi (port 8080)
          ↓                                                                                                                         
  Response back up the chain
                                                                                                                                    
  ---                                                       

  ## Key Files on the Pi

  | File | Location | Purpose |               
  |---|---|---|                           
  | app.py | `~/pi-api/app.py` | Flask API server |
  | Dockerfile | `~/pi-api/Dockerfile` | Container recipe |                                                                         
  | requirements.txt | `~/pi-api/requirements.txt` | Python dependencies |
  | update-tunnel-url.sh | `~/update-tunnel-url.sh` | Saves Cloudflare URL to Secret Manager |                                      
  | cloudflared.service | `/etc/systemd/system/cloudflared.service` | Permanent tunnel service |
                                              
  ---                                                                                                                               
  
  ## Operational Checklist                                                                                                          
                                                            
  1. Check tunnel:          sudo systemctl status cloudflared                                                                       
  2. Update URL:            ~/update-tunnel-url.sh          
  3. Check Docker:          docker ps         
  4. Check GKE pod:         kubectl get pods

  ---                                                                                                                               
                                          
  ## Remaining Work                                                                                                                 
                                                                                                                                    
  - [ ] Stable Cloudflare URL (requires domain on Cloudflare)
  - [ ] CI/CD pipeline (automate build, push, deploy)                                                                               
  - [ ] Authentication on the API                           
  - [ ] GKE agent with real workload   
