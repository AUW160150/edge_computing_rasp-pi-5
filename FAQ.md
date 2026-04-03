Which code deploys the GKE cluster and hosts the HTTP API server?

Infrastructure: terraform/main.tf  
- Lines 57–95: GKE cluster pi-agent-cluster, zone us-central1-a, e2-small nodes, autoscaling 1–10  
- Lines 101–112: IAM bindings → nodes can pull from Artifact Registry + read secrets  

Kubernetes: gke-api/deployment.yaml (line 1–55) + gke-api/service.yaml  
- deployment.yaml: declares the pod with pi-api container (port 8080) + Tailscale sidecar  
- service.yaml: type: LoadBalancer, maps :80 → :8080 → assigns GCP external IP 34.44.129.194  

The API server code: gke-api/app.py  
- Flask app, listens on port 8080  
- Entrypoint: CMD ["python", "app.py"] in gke-api/Dockerfile  

Which portion runs AI agents? Is an agent spawned per developer HTTP request?

Yes — one agent per task.

Flow:  
1. Developer hits POST /tasks → gke-api/app.py:156–183  
2. Task is added to task_queue (Python Queue) → app.py:176  
3. Single background worker() thread pulls from queue → app.py:90–136  
4. Worker calls run_agent(...) from gke-api/agent.py:112  
5. run_agent() runs the Claude agent loop → agent.py:8–104  

The agent is not a separate process or pod — it runs as a function call inside the worker thread. One task at a time  
(single worker, serial queue).  


Q3: Are results returned to the developer through the API?

Yes, via Server-Sent Events (SSE).

- Developer connects to GET /tasks/{task_id}/stream → app.py:232–277  
- Polling loop every 0.5s checks task logs array  
- Emits all log entries (system trail, thoughts, commands, output) as SSE events  
- Emits final result event when task reaches done/error/cancelled  
- Developer can also poll GET /tasks/{task_id} for the full task object → app.py:186–192  

Event types emitted: system, thought, command, output, summary, status, result  

---

Q4: Are only internal developers able to access the API?

Partially — API key gates access, but the endpoint is public.

- require_auth decorator → app.py:47–55  
- Checks X-API-Key header against secret fetched from GCP Secret Manager (gke-api-key)  
- Returns 401 if missing or wrong  
- Applied to: POST /tasks, GET /tasks, GET /tasks/{id}, DELETE /tasks/{id}, GET /pi/status, GET /tasks/{id}/stream  
- /health and / are public (no auth)  

Gap: The LoadBalancer IP is publicly reachable — anyone on the internet can attempt requests. There is no IP allowlist, VPN  
requirement, or rate limiting.  

---

Q5: Are only authorized agents able to connect to the Pi?

Yes — two enforcement layers.

Layer 1 — Tailscale ACL (system_design_architecture.md / Tailscale admin console):  
"grants": [{"src": ["tag:gke"], "dst": ["tag:pi"], "ip": ["tcp:8080"]}]  
Only devices tagged tag:gke can reach the Pi on port 8080. No other Tailscale devices can.  

Layer 2 — X-Pi-Token (pi-api/app.py:11–18):  
- require_token decorator checks X-Pi-Token header  
- Token loaded from env var PI_EXECUTE_TOKEN at startup  
- Set via GCP Secret Manager secret pi-execute-token  

Both must pass. Network-level (Tailscale ACL) blocks the connection before any HTTP auth is checked.  

---

Q6: How are agents specifically authorized vs other agents in the cluster?

The GKE pod is the only entity that runs agents. Authorization is enforced by:

1. Tailscale tagged auth key: The sidecar uses a key with tag:gke → deployment.yaml:36 (TS_AUTHKEY from K8s Secret). Only  
this specific tagged key can connect to the Tailnet and reach the Pi.  
2. Pi token uniqueness: pi-execute-token is a single shared secret stored in GCP Secret Manager. Only the GKE pod reads it  
at startup (agent.py receives it as argument from app.py). No other pod in the cluster has access unless it's been granted  
roles/secretmanager.secretAccessor.  

There is no per-agent identity — the token is shared by all requests processed by the single GKE pod. If you scaled to  
multiple replicas, all would share the same token.  

---

Q7: Can we recreate the entire setup from IaC? Which file?

Most of it, yes.

File to read: terraform/main.tf (216 lines)  
- GCP APIs, GKE cluster, Artifact Registry, IAM bindings, Secret Manager secrets, GitHub Actions WI  
- Run order: terraform init → terraform apply → creates everything in GCP  

After Terraform (manual steps, not yet in IaC):  
1. Set secret values in Secret Manager (Terraform creates the secret shells, not the values)  
2. Create K8s Secret for tailscale-auth-key: kubectl create secret generic tailscale-auth-key --from-literal=key=<key>  
3. Apply K8s manifests: kubectl apply -f gke-api/deployment.yaml -f gke-api/service.yaml  
4. Bootstrap Pi: bash pi-setup/setup.sh <PI_EXECUTE_TOKEN> <TAILSCALE_AUTH_KEY>  

CI/CD (.github/workflows/deploy.yml): Handles all future image builds and deployments automatically on push to main.  

The K8s tailscale-auth-key secret is the only IaC gap (noted as known limitation in day_2.md).  

---

Q8: Do we have visibility into what's happening on the Pi? Can developers see task status?

Yes — multiple layers.

Real-time task visibility:  
- GET /tasks/{id}/stream → SSE stream with live events as the agent runs  
- Events include: which command Claude decided to run, what output came back, Pi response time  
- agent.py:54–92 emits system/thought/command/output events throughout execution  

Pi health visibility:  
- GET /health → app.py:144–153 → returns {"api": "ok", "pi": {"online": true/false, "last_checked": ..., "error": ...}}  
- GET /pi/status → app.py:214–229 → proxies to Pi, returns CPU%, memory (GB + %), disk (GB + %)  

Logs:  
- kubectl logs deployment/pi-api -c pi-api → structured Python logging to stdout → ingested by GCP Cloud Logging  
- Task-level logs stored in tasks[id]["logs"] array in memory  
- Log events include: task queued, task started, each command run, task completed/failed, unauthorized access attempts  

Dashboard: dashboard/index.html — frontend that surfaces all of the above in a browser UI with SSE live feed, Pi metrics  
panel, task history.  

---

Q9: Handling concurrent requests? Is there a queuing system?

Yes — Python Queue with a single worker thread.

Queue: task_queue = Queue() → app.py:22  
- POST /tasks enqueues: task_queue.put(task) → app.py:176  
- Tasks are added instantly, developer gets 202 Accepted with task_id  

Worker: worker() function → app.py:90–136  
- Single daemon thread started at app.py:282  
- Blocks on task_queue.get() — picks up next task when current one finishes  
- Processes one task at a time (serial)  

What this means for concurrency:  
- Multiple developers can submit tasks simultaneously — all get a task_id immediately  
- Tasks execute one at a time in FIFO order  
- All developers can stream their task's progress in parallel via SSE (that part is concurrent)  
- No task is dropped — queue is unbounded in memory  

---

Q10: Task prioritization and preventing Pi resource conflicts?

No prioritization. Resource conflict prevention via serial execution.

Prioritization: Not implemented. Python Queue is strictly FIFO. There is no priority queue, no VIP task lanes, no  
preemption.  

Resource conflict prevention:  
- Single worker thread = only one agent runs at a time = only one command executes on Pi at a time → app.py:282  
- Pi health check blocks new tasks if Pi is offline: app.py:164–167 returns 503 → prevents queueing work that can't run  
- Docker sandbox limits per-command resource usage on Pi: --cpus=0.5 --memory=512m → pi-api/app.py:47–56  
- 10-round agent limit prevents runaway tasks: agent.py:50  

What's NOT protected:  
- Queue depth: unbounded — many tasks can pile up  
- Long-running tasks can starve others (no timeout on total task duration, only per-command 60s)  
- If Pi goes offline mid-task, the task errors but remaining queued tasks will also fail until Pi recovers  
