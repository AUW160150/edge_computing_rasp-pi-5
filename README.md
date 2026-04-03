# Edge Compute Infrastructure Mini Project

## Scenario

Configuring a brand-new, blank Raspberry Pi 5 and build the infrastructure that allows our internal developers to interact with it through AI agents.

We'll give you:
- One Raspberry Pi 5 (8GB RAM, 4 CPUs, ARM64)
- One blank microSD card (128GB)

You'll see our existing fleet of ~10 Pis in the office rack, but you won't have access to them. Your Pi is independent — you set it up from scratch.

### Current State: Blank Hardware

The Raspberry Pi is brand new out of the box. There's no OS installed, no network configuration, no remote access. You need to turn it into a usable edge compute sandbox that developers can interact with from the cloud.

```
                    ┌─────────────────────────────────────────┐
                    │           Internal Developers           │
                    │              (team of ~10)              │
                    └────────────────────┬────────────────────┘
                                         │
                                    HTTP Requests
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │              GKE Cluster                │
                    │  ┌───────────────────────────────────┐  │
                    │  │          HTTP API Server          │  │
                    │  │   (request handling, queueing)    │  │
                    │  └─────────────────┬─────────────────┘  │
                    │                    │                    │
                    │                    ▼                    │
                    │  ┌───────────────────────────────────┐  │
                    │  │          Agent Runtime            │  │
                    │  │        (LLM-powered agents)       │  │
                    │  └─────────────────┬─────────────────┘  │
                    └────────────────────┼────────────────────┘
                                         │
                               Secure Connection
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │           Raspberry Pi 5               │
                    │      (physical device in office)       │
                    │          [Your Sandbox]                │
                    └─────────────────────────────────────────┘
```

**Your mission**:
1. **Set up** the Raspberry Pi as a usable sandbox environment
2. **Build** cloud infrastructure in GCP that hosts an HTTP API server with agent capabilities
3. **Connect** the cloud agents to the physical Raspberry Pi securely
4. **Enable** internal developers to run AI-assisted tasks on the edge hardware

## Requirements

### Core Requirements

1. **Raspberry Pi Setup**
   - Install an OS and configure the device from a blank state
   - Enable remote access capabilities for agent interactions
   - Set up container isolation (Docker) so agent workloads don't affect the host OS
   - The device should be able to execute compute tasks initiated by agents (Python scripts, shell commands, etc.)

2. **GCP Infrastructure**
   - Deploy a GKE cluster in the provided project
   - Host an HTTP API server that accepts requests from internal developers
   - Run AI agents within the cluster that can process developer requests
   - Agents must be able to connect to and interact with the Raspberry Pi

3. **Agent Integration**
   - When a developer sends an HTTP request to the API server, an agent should be spawned or assigned
   - The agent uses the provided LLM access to understand and execute the task
   - The agent must be able to perform operations on the Raspberry Pi (run commands, transfer files, etc.)
   - Return results back to the developer through the API

4. **Security**
   - Only internal developers should be able to access the API server
   - Only authorized agents should be able to connect to the Raspberry Pi
   - No credentials or secrets should be hardcoded or exposed

5. **Infrastructure as Code**
   - All infrastructure must be defined in code and reproducible
   - We should be able to tear down and recreate your entire setup from your IaC definitions
   - Include clear instructions for provisioning from scratch

### Advanced Requirements

6. **Task Management**
   - Support concurrent requests from multiple developers (~10 people)
   - Implement a queueing system to manage task execution
   - Handle task prioritization and prevent resource conflicts on the Raspberry Pi

7. **Observability**
   - Provide visibility into what's happening on the Raspberry Pi
   - Developers should be able to see the status of their tasks
   - Surface logs, metrics, or resource information (CPU, memory, disk) from the edge device

8. **Internal Frontend** (Stretch)
   - Build a simple web interface for developers to:
     - Submit tasks
     - View task queue and status
     - See real-time activity on the Raspberry Pi

## What We Provide

- **GCP Project**: `mini_project` ([Console Link](https://console.cloud.google.com/iam-admin/iam?referrer=search&hl=en&project=rodela-trial-project))
- **Your GCP Role**: Project Owner (you'll need to set up additional permissions and resources yourself)
- **Raspberry Pi 5**: Blank device + blank microSD card, available in the office (coordinate with @Jack for physical access)
- **LLM Access**: Anthropic API key (will be provided separately)
- **Network**: Office WiFi details will be shared on Day 1. The office also has a PoE Ethernet switch available.
- **This repository**: Starting point for your infrastructure code

## What You Need to Figure Out

These are the challenges we expect you to work through:

**Device Setup**:
- How do you go from a blank Pi + blank SD card to a functional, remotely accessible device?
- What OS configuration, packages, and services are needed?
- How do you isolate agent workloads from the host OS?

**Connectivity**:
- How will agents running in GKE connect to a device on our office network?
- The Pi is behind a NAT/firewall — it doesn't have a public IP. How do you solve this?
- What are the security implications and how do you mitigate them?

**Architecture**:
- How do you design the API server to handle multiple concurrent users?
- How do you manage agent lifecycles — one agent per request, or a pool?
- How do you prevent multiple agents from conflicting on the single Pi?

**Reliability**:
- What happens if the connection to the Raspberry Pi is lost?
- How do you handle long-running tasks?
- What if the agent crashes mid-task?

**Developer Experience**:
- How do developers know their task is being processed?
- How do they retrieve results?
- How do you provide useful error messages?

## What We're Evaluating

This is NOT a test of whether you can write Kubernetes YAML or follow tutorials.

We're evaluating:

1. **Infrastructure design** — Can you architect a system that connects cloud to edge reliably?
2. **Security thinking** — Do you consider access control, network security, and secrets management?
3. **Systems integration** — Can you wire multiple systems together (GKE, agents, physical hardware)?
4. **Problem-solving** — What do you do when things don't work? This is a novel setup.
5. **Communication** — Can you explain your decisions and trade-offs?
6. **Operational thinking** — How do you handle failures, monitoring, and multi-user scenarios?

## Deliverables

### Daily Standups (15 min, end of day)

- Screen share your progress
- Explain what's working and what's not
- Discuss blockers and your plan for the next day

### Final Presentation (Day 3, 30 min)

1. **Architecture walkthrough** (5 min) — Explain your infrastructure design
2. **Live demo** (15 min):
   - Send a request to your API server
   - Show the agent processing the request
   - Demonstrate the agent executing something on the Raspberry Pi
   - Show results returned to the developer
3. **Security review** (5 min) — Explain your access control approach
4. **Q&A** (5 min) — Be prepared to discuss trade-offs and alternative approaches

## Evaluation Criteria

| Criteria | Weight | What We Look For |
|----------|--------|------------------|
| **Working E2E System** | 25% | Request → API → Agent → Raspberry Pi → Response works reliably |
| **Infrastructure as Code** | 20% | All infrastructure reproducible from code; clear provisioning instructions |
| **Security** | 20% | Access control implemented, secure connectivity approach |
| **Infrastructure Quality** | 15% | Proper GCP setup, resource management, no hardcoded secrets |
| **Multi-User Support** | 10% | Handles concurrent requests, task management works |
| **Architecture Decisions** | 5% | Can justify choices, considered alternatives |
| **Communication** | 5% | Clear standups, explains trade-offs |

**Minimum Bar**: Working E2E system where an agent can execute a task on the Raspberry Pi via HTTP API, with basic access control and reproducible infrastructure.

## Stretch Goals

- Real-time task status updates (websockets, SSE)
- Web frontend for task submission and monitoring
- Auto-scaling based on request queue depth
- Comprehensive observability dashboard for the Raspberry Pi
- Graceful handling of Raspberry Pi disconnection/reconnection
- Container image management for different workload types

