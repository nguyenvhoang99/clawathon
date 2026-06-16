# Clawathon — AI Agent Hackathon Project

A hackathon workspace for designing, building, and deploying an AI agent on [GreenNode AgentBase](https://aiplatform.console.vngcloud.vn/).

> **Agent purpose:** Vietnam team trip planner (~10 members) — multi-agent LangGraph orchestrator for stays, transport, activities, weather-aware itineraries, and budget planning.

## Project layout

```
agents/
├── weather-chatbot/   # Original weather Q&A agent (legacy)
├── trip-planner/      # Team trip planner (primary)
└── bill-splitter/     # Expense tracking + VietQR settlement

web/                   # Team trip demo website (see web/README.md)
```

See [agents/trip-planner/.env.example](agents/trip-planner/.env.example) for configuration.

## What This Repo Is For

This project is set up to go from **zero to a deployed agent** using GreenNode AgentBase — VNG Cloud's managed platform for agent identity, runtime, memory, LLM access, and observability.

The repo includes Cursor **Agent Skills** under `.cursor/skills/` that encode platform workflows. When working in Cursor, invoke these skills (e.g. `/agentbase-wizard`) instead of improvising API calls or setup steps from memory.

## Platform Overview

| Component | Purpose |
|-----------|---------|
| **Identity** | Agent identities and outbound auth (API keys, OAuth2) for external services |
| **Runtime** | Hosts Custom Agent Docker images or OpenClaw templates (Telegram / Zalo bots) |
| **Memory** | Short-term conversation history and long-term semantic memory |
| **LLM (AIP)** | OpenAI-compatible model access via GreenNode AI Platform |
| **Gateway (MCP)** | Managed proxy for MCP servers with inbound/outbound auth and policy |
| **Observability** | Runtime logs, endpoint logs, CPU/RAM metrics |

**Two deployment paths:**

- **Custom Agent** (default for this hackathon) — You write Python code, package it in Docker, deploy to `/agent-runtimes`.
- **OpenClaw** — Pre-built Telegram/Zalo bot templates; no custom Docker image required.

## Getting Started

### 1. Define the agent purpose

Before writing code, agree on:

- **Problem** — What user or team pain does the agent solve?
- **Inputs/outputs** — What triggers the agent and what does it return?
- **Integrations** — External APIs, databases, MCP tools, or internal services?
- **Memory needs** — Should it remember past sessions or user preferences?

Capture decisions in this README or a short `docs/` note as the scope firms up.

### 2. Set up platform credentials (local dev)

Local development and platform management APIs require a GreenNode IAM service account.

1. Create a service account in the [IAM Console](https://iam.console.vngcloud.vn/service-accounts).
2. Attach policies (recommended for full AgentBase access):
   - `AgentBaseFullAccess`
   - `vcrFullAccess`
   - `AiPlatformFullAccess`
3. Store credentials via environment variables or `.greennode.json`:

```bash
export GREENNODE_CLIENT_ID="<your-client-id>"
export GREENNODE_CLIENT_SECRET="<your-client-secret>"
```

> **Do not commit credentials.** Keep `.greennode.json`, `.env`, and `.agentbase/` out of version control.

When deployed on AgentBase Runtime, IAM credentials and agent identity are injected automatically — manual setup is only needed for local dev and platform API calls from your machine.

### 3. Scaffold and build with the wizard

In Cursor, start with:

```
/agentbase-wizard
```

The wizard walks through a 9-step lifecycle:

1. Check prerequisites (IAM credentials)
2. Scaffold project (`main.py`, `Dockerfile`, `requirements.txt`)
3. Set up memory (optional)
4. Set up identity & external auth (optional)
5. Customize agent code
6. Configure environment (`.env` — LLM keys, memory ID, etc.)
7. Test locally
8. Deploy (build, push image, create runtime)
9. Verify (health check, smoke test, logs)

**Standalone shortcuts:**

| Command | Use when |
|---------|----------|
| `/agentbase-wizard init [name] [--langchain\|--langgraph\|...]` | Scaffold only |
| `/agentbase-wizard test [validate\|local\|docker\|preflight]` | Test without full wizard |
| `/agentbase-wizard resume` | Continue after interruption |
| `/agentbase-wizard reset` | Clear wizard state and start over |

**Framework options** (choose during init):

- **Basic** — Simple request/response, no AI framework
- **LangChain** / **LangChain + Memory** — Recommended for tool-using agents
- **LangGraph** / **LangGraph + Memory** — Stateful graph workflows
- **Custom** — Any other framework (CrewAI, AutoGen, etc.) on top of `greennode-agentbase`

Requires **Python 3.10+**.

### 4. Deploy and monitor

After local testing:

```
/agentbase-deploy    # Build, push, create/update runtime
/agentbase-monitor   # Logs, metrics, debug deployed agents
```

### 5. Tear down when done

```
/agentbase-teardown  # Remove runtime, identity, memory, registry, API keys
```

Use this at the end of the hackathon or when resetting the environment. For deleting a single resource, use the dedicated skill instead.

## Cursor Skills Reference

Skills live in `.cursor/skills/`. Invoke them in chat with `/skill-name`.

| Skill | When to use |
|-------|-------------|
| `/agentbase-wizard` | **Start here to build an agent.** Full lifecycle, init, and test. |
| `/agentbase` | Platform overview, architecture, IAM setup, which skill to pick |
| `/agentbase-llm` | Platform LLM API keys, models, OpenAI-compatible endpoint |
| `/agentbase-memory` | Conversation history, long-term memory, LangChain/LangGraph integration |
| `/agentbase-identity` | Agent identity, outbound auth for **external** services (OpenAI, Slack, etc.) |
| `/agentbase-deploy` | Deploy Custom Agent or OpenClaw; manage runtimes and container registry |
| `/agentbase-gateway` | Resource Gateway (MCP proxy), inbound/outbound auth per target |
| `/agentbase-policy` | Authorization policies for Gateway resources |
| `/agentbase-monitor` | Logs, metrics, dashboard, debug deployed agents |
| `/agentbase-teardown` | Clean up all platform resources for the project |

**Routing tips:**

- Building or planning an agent → always `/agentbase-wizard` first
- "API key" without a service name → `/agentbase-llm` (platform LLM)
- API key for OpenAI, Google, Slack, etc. → `/agentbase-identity`
- Learn about the platform only → `/agentbase` (not the wizard)

## Project Conventions

These conventions come from the imported skills and should be followed throughout the hackathon.

### File boundaries

| File | Purpose |
|------|---------|
| `.greennode.json` | SDK credentials only (`client_id`, `client_secret`, `agent_identity`) |
| `.agentbase-state.json` | Wizard progress and resource IDs (`runtime_id`, `memory_id`, etc.) |
| `.env` | Application config — LLM keys, `MEMORY_ID`, feature flags |
| `.agentbase/` | Cached tokens and local tooling state |

### Scaffolding layout

Project files are created **flat in the repo root** (not in a subdirectory):

```
main.py              # Agent entrypoint (GreenNodeAgentBaseApp)
Dockerfile           # Container image for Custom Agent deploy
requirements.txt     # Python dependencies
.env                 # Local config (gitignored)
README.md            # This file
```

### Agent runtime contract

Custom agents must expose:

- `POST /invocations` — main handler
- `GET /health` — health check (returns `HEALTHY` or `HEALTHY_BUSY`)
- Default port **8080**

Use helper scripts under `.cursor/skills/agentbase/scripts/` for tokens and credential checks — do not hand-roll curl token flows.

### Interaction guidelines (when using AI assistance)

- **Confirm before significant actions** — deploy, create IAM accounts, delete resources
- **Invoke skills before API calls** — skills contain authoritative endpoints and procedures
- **Inspect API responses** — do not assume field names across services
- **Separate credential types** — IAM (platform) vs `.env` (LLM/app) vs identity auth (external APIs)

## Suggested Hackathon Phases

| Phase | Focus | Skills |
|-------|-------|--------|
| **Discover** | Define purpose, users, integrations | — |
| **Bootstrap** | Credentials, scaffold, LLM setup | `/agentbase`, `/agentbase-wizard init`, `/agentbase-llm` |
| **Build** | Core logic, tools, memory, external auth | `/agentbase-wizard`, `/agentbase-memory`, `/agentbase-identity` |
| **Integrate** | MCP gateway, policies (if needed) | `/agentbase-gateway`, `/agentbase-policy` |
| **Ship** | Local test → Docker → deploy | `/agentbase-wizard test`, `/agentbase-deploy` |
| **Demo** | Monitor, fix issues, document | `/agentbase-monitor` |
| **Cleanup** | Remove cloud resources | `/agentbase-teardown` |

## Prerequisites

- [Cursor](https://cursor.com/) with this repo open (skills load from `.cursor/skills/`)
- Python 3.10+
- Docker (for local container tests and image push)
- GreenNode / VNG Cloud account with IAM service account access
- Optional: Docker login to GreenNode Container Registry (handled by `/agentbase-deploy`)

## Useful Links

- [Agent Runtime Console](https://aiplatform.console.vngcloud.vn/agent-runtime?tab=runtime)
- [Memory Console](https://aiplatform.console.vngcloud.vn/memory)
- [IAM Service Accounts](https://iam.console.vngcloud.vn/service-accounts)
- [Access Control Console](https://aiplatform.console.vngcloud.vn/access-control)

## Weather Chatbot

LangChain agent with two tools:

- `get_current_weather(city)` — live temperature, humidity, wind, conditions
- `get_weather_forecast(city, days)` — up to 7-day forecast

Weather data comes from Open-Meteo (free, no API key). The LLM is powered by GreenNode AI Platform.

### Test locally

```bash
cp .env.example .env
# Fill in LLM_API_KEY and LLM_MODEL (see Environment Variables below)

python3 main.py

curl -X POST http://127.0.0.1:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in Hanoi today?"}'
```

### Deploy

```bash
/agentbase-deploy
```

Or confirm deployment in Cursor chat after setting credentials below.

## Environment Variables

### For local dev + deploy CLI (your machine)

Set these so AgentBase skills can call platform APIs:

```bash
export GREENNODE_CLIENT_ID="<from IAM service account>"
export GREENNODE_CLIENT_SECRET="<from IAM service account>"
```

Or fill in `.greennode.json` (gitignored).

Create a service account at [IAM Console](https://iam.console.vngcloud.vn/service-accounts) with `AgentBaseFullAccess`, `vcrFullAccess`, and `AiPlatformFullAccess`.

### For the agent runtime (`.env` passed at deploy)

Only LLM config is required — **do not** put `GREENNODE_*` vars in deploy `.env` (runtime auto-injects them):

| Variable | Required | Example / Notes |
|----------|----------|-----------------|
| `LLM_API_KEY` | Yes | Create via `/agentbase-llm api-keys create --name weather-chatbot-key` |
| `LLM_BASE_URL` | Yes | `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` |
| `LLM_MODEL` | Yes | Pick an ENABLED model via `/agentbase-llm models list` |

### Auto-injected at runtime (do NOT set manually)

| Variable | Description |
|----------|-------------|
| `GREENNODE_CLIENT_ID` | Runtime IAM service account |
| `GREENNODE_CLIENT_SECRET` | Runtime IAM secret |
| `GREENNODE_AGENT_IDENTITY` | Agent identity name |
| `GREENNODE_ENDPOINT_URL` | Public endpoint URL |

---

*Built for the Clawathon hackathon on GreenNode AgentBase.*
