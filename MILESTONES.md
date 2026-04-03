# Project Milestones

This document outlines the expected progression through the project.
Use it to gauge your progress and prioritize your time.

## Day 1: Setup & Exploration

### Milestone 1.1: Understand the Environment

**Goal**: Familiarize yourself with all components.

Tasks:
- Access your GCP project and explore available resources
- Unbox the Raspberry Pi 5 and understand its hardware (ports, storage, power)
- Understand the office network setup (WiFi, Ethernet switch)
- Identify what permissions and resources you need to create

**Checkpoint**: You can access GCP and have a plan for setting up the Pi and cloud infrastructure.

### Milestone 1.2: Raspberry Pi Setup

**Goal**: Configure the Raspberry Pi as a usable sandbox.

Tasks:
- Install Raspberry Pi OS on the blank microSD card
- Configure the device for headless remote access (SSH)
- Connect it to the office network (WiFi or Ethernet)
- Install Docker for workload isolation
- Verify you can run compute tasks on it (Python, shell commands inside containers)
- Document the device's capabilities and constraints (4 CPUs, 8GB RAM, ARM64)

**Checkpoint**: You can remotely connect to the Pi and run commands inside Docker containers.

### Milestone 1.3: GCP Foundation

**Goal**: Set up the core GCP infrastructure using Infrastructure as Code.

Tasks:
- Configure necessary IAM permissions
- Set up networking components
- Create a GKE cluster
- **All infrastructure must be defined in code** (not manually through console)
- Verify cluster is operational

**Checkpoint**: GKE cluster is running, deployable via IaC, and you can deploy workloads to it.

---

## Day 2: Build & Connect

### Milestone 2.1: API Server

**Goal**: Deploy an HTTP API server that accepts developer requests.

Tasks:
- Design the API interface (endpoints, request/response format)
- Implement the API server
- Deploy to GKE
- Test that it accepts and responds to HTTP requests

**Checkpoint**: You can send HTTP requests to your API server and receive responses.

### Milestone 2.2: Agent Integration

**Goal**: Agents can process requests using LLM capabilities.

Tasks:
- Integrate the provided LLM access (Anthropic API)
- Implement agent logic that can understand and plan tasks
- Connect agent lifecycle to API requests
- Test agent can reason about tasks

**Checkpoint**: When you send a task to the API, an agent processes it and returns a result.

### Milestone 2.3: Edge Connectivity

**Goal**: Agents can interact with the Raspberry Pi.

Tasks:
- Establish secure connectivity between GKE and the Raspberry Pi
- The Pi is behind a NAT/firewall — you need to solve this (VPN, tunnel, reverse proxy, etc.)
- Give agents the ability to execute commands on the device
- Handle connection failures gracefully
- Test E2E: API → Agent → Raspberry Pi → Response

**Checkpoint**: An agent can successfully execute a task on the Raspberry Pi and return results.

---

## Day 3: Harden & Demo

### Milestone 3.1: Security Implementation

**Goal**: Lock down access to authorized users only.

Tasks:
- Implement access control for the API server
- Secure the connection to the Raspberry Pi
- Ensure no credentials are exposed
- Review and address security gaps

**Checkpoint**: Only authorized developers can access the system; unauthorized access is blocked.

### Milestone 3.2: Multi-User Support

**Goal**: System handles concurrent requests from multiple developers.

Tasks:
- Implement task queueing
- Handle concurrent execution appropriately
- Prevent resource conflicts on the Raspberry Pi (it has only 4 CPUs and 8GB RAM)
- Test with simulated multiple users

**Checkpoint**: Multiple developers can submit tasks without conflicts or data loss.

### Milestone 3.3: Observability (if time permits)

**Goal**: Developers can see what's happening.

Tasks:
- Surface task status through the API
- Provide visibility into Raspberry Pi activity (CPU, memory, running processes)
- Add logging and monitoring

**Checkpoint**: Developers can track their task status and see system activity.

### Milestone 3.4: Infrastructure Reproducibility

**Goal**: Ensure all infrastructure can be reproduced from code.

Tasks:
- Verify all infrastructure is defined in IaC (not created manually)
- Test that infrastructure can be torn down and recreated
- Write clear provisioning instructions
- Commit all IaC definitions to the repository

**Checkpoint**: Another engineer could recreate your entire infrastructure from your code and instructions.

### Milestone 3.5: Documentation & Presentation

**Goal**: Ready to demo and explain the system.

Tasks:
- Document your architecture and decisions
- Prepare demo scenarios
- Anticipate questions about trade-offs
- Ensure system is stable for live demo

**Checkpoint**: You can demo the full E2E flow and explain your design decisions.

---

## Evaluation Summary

| Level | What You've Achieved |
|-------|---------------------|
| **Does Not Pass** | E2E not working, infrastructure not reproducible from code, cannot demo agent interacting with Raspberry Pi, or major security gaps |
| **Pass** | E2E works: HTTP → Agent → Raspberry Pi → Response. Infrastructure defined in IaC and reproducible. Basic access control. Can explain architecture. |
| **Good** | Above + multi-user support, proper queueing, secure connectivity, observability basics |
| **Excellent** | Above + production-ready infrastructure, comprehensive security, graceful error handling, clear documentation |
| **Exceptional** | Above + stretch goals, novel solutions to connectivity challenges, deep systems thinking |

All infrastructure must be reproducible from your IaC definitions.
