# System Design Architecture

## Overview

A cloud-to-edge AI agent platform. Developers submit natural language tasks via HTTP to a GKE-hosted API. A Claude AI agent interprets the task, executes shell commands on a physical Raspberry Pi 5 through a Tailscale WireGuard mesh, and streams results back in real time.

---

## Architecture Diagram

```mermaid
graph TD
    DEV["👨‍💻 Developer\n(curl / dashboard)"]

    subgraph GCP["GCP — us-central1-a"]
        LB["🌐 GCP Load Balancer\n34.44.129.194:80"]

        subgraph GKE["GKE Pod"]
            API["Flask API\n├── X-API-Key auth\n├── Task queue\n├── Pi liveness monitor\n└── SSE stream"]
            AGENT["Claude Agent\n(claude-opus-4-6)\nrun_command tool"]
            TS_SIDE["Tailscale Sidecar\ntag:gke\nSOCKS5 :1055"]
        end

        subgraph IAM["IAM & Secrets"]
            SM["Secret Manager\ngke-api-key\npi-tunnel-url\npi-execute-token\nanthropic-api-key\ntailscale-auth-key"]
            WI["Workload Identity\nFederation\n(GitHub Actions CI)"]
        end

        AR["Artifact Registry\npi-api-repo"]
    end

    subgraph ANTHROPIC["Anthropic Cloud"]
        LLM["Claude API\napi.anthropic.com"]
    end

    subgraph TAILNET["Tailscale Network (WireGuard)"]
        MESH["Encrypted Mesh\nACL: tag:gke → tag:pi:8080"]
    end

    subgraph OFFICE["Office Network (NAT)"]
        subgraph PI["Raspberry Pi 5\n100.103.122.25"]
            TS_PI["Tailscale\ntag:pi"]
            PI_API["Pi Flask API\n:8080\nX-Pi-Token auth"]
            SANDBOX["Docker Sandbox\npython:3.11-slim\n--network=none\n--cpus=0.5\n--user=nobody\n--rm"]
        end
    end

    subgraph CI["GitHub Actions CI/CD"]
        GHA["deploy.yml\nWorkload Identity\nFederation"]
    end

    DEV -->|"POST /tasks\nX-API-Key"| LB
    LB --> API
    API -->|"load secrets"| SM
    API --> AGENT
    AGENT -->|"messages.create()"| LLM
    LLM -->|"tool_use: run_command"| AGENT
    AGENT -->|"SOCKS5 proxy"| TS_SIDE
    TS_SIDE <-->|"WireGuard"| MESH
    MESH <-->|"WireGuard"| TS_PI
    TS_PI --> PI_API
    PI_API -->|"docker run"| SANDBOX
    SANDBOX -->|"stdout/stderr"| PI_API
    PI_API -->|"JSON response"| AGENT
    AGENT -->|"SSE events"| API
    API -->|"SSE stream\nthought/command/output/result"| DEV

    GHA -->|"kubectl set image"| GKE
    GHA -->|"docker push"| AR
    WI --> GHA
    AR --> GKE
```

---

## Request Lifecycle (Sequence)

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant API as GKE Flask API
    participant SM as Secret Manager
    participant Claude as Claude (Anthropic)
    participant TS as Tailscale SOCKS5
    participant Pi as Pi Flask API
    participant Box as Docker Sandbox

    Dev->>API: POST /tasks {description} + X-API-Key
    API->>SM: validate X-API-Key
    SM-->>API: key valid
    API-->>Dev: {task_id, status: queued} 202

    Dev->>API: GET /tasks/{id}/stream (SSE)

    Note over API: Worker thread picks up task

    API-->>Dev: SSE: system — worker started

    loop Agent Loop (max 10 rounds)
        API->>Claude: messages.create(task + tools)
        API-->>Dev: SSE: system — calling Anthropic

        Claude-->>API: tool_use: run_command(cmd)
        API-->>Dev: SSE: system — Anthropic responded
        API-->>Dev: SSE: thought — Claude's reasoning
        API-->>Dev: SSE: command — shell command

        API->>TS: POST via SOCKS5 proxy
        API-->>Dev: SSE: system — routing through Tailscale

        TS->>Pi: POST /execute {command} + X-Pi-Token
        Pi->>Box: docker run --network=none ... sh -c cmd
        Box-->>Pi: stdout/stderr
        Pi-->>TS: {output, exit_code}
        TS-->>API: response

        API-->>Dev: SSE: system — Pi responded
        API-->>Dev: SSE: output — command output

        API->>Claude: tool_result (Pi output)
    end

    Claude-->>API: end_turn + summary
    API-->>Dev: SSE: summary
    API-->>Dev: SSE: status — done
    API-->>Dev: SSE: result — full result object
```

---

## Security Layers

```mermaid
graph LR
    L1["Layer 1\nX-API-Key\nDeveloper → GKE"]
    L2["Layer 2\nTailscale ACL\ntag:gke → tag:pi:8080 only"]
    L3["Layer 3\nX-Pi-Token\nGKE Agent → Pi API"]
    L4["Layer 4\nDocker Sandbox\n--network=none\n--user=nobody\n--rm"]
    L5["Layer 5\nGCP Secret Manager\nNo hardcoded credentials"]

    L1 --> L2 --> L3 --> L4
    L5 -.- L1
    L5 -.- L3
```

---

## Infrastructure as Code Coverage

```mermaid
graph TD
    TF["terraform/main.tf"]

    TF --> A["GKE Cluster + Node Pool"]
    TF --> B["Artifact Registry"]
    TF --> C["GCP APIs\n(container, artifactregistry,\nsecretmanager, iam)"]
    TF --> D["Secret Manager Secrets\n(5 secrets — values set manually)"]
    TF --> E["IAM Bindings\nGKE node SA roles"]
    TF --> F["GitHub Actions SA"]
    TF --> G["Workload Identity Pool\n+ Provider"]
    TF --> H["WI → SA Binding\n(Asari-AI/rodela-trial-project)"]

    K8S["gke-api/\ndeployment.yaml\nservice.yaml"]
    K8S --> I["GKE Deployment\n(pi-api + tailscale sidecar)"]
    K8S --> J["LoadBalancer Service\n:80 → :8080"]
```
