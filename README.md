# BuildMind AI

BuildMind AI is an autonomous software engineering workspace that turns a repo and a task into a structured AI-driven development flow. It plans the work, explores the codebase, generates patches, runs tests, reviews results, waits for human approval, and finalizes the outcome with git-aware reporting.

<p align="center">
  <img src="https://img.shields.io/badge/Status-Production%20Prototype-blue" alt="Status" />
  <img src="https://img.shields.io/badge/Stack-Next.js%20%2B%20FastAPI-orange" alt="Stack" />
  <img src="https://img.shields.io/badge/AI-LangGraph%20Workflow-purple" alt="Workflow" />
</p>

## Overview

BuildMind AI is built for developers who want an AI coding assistant that behaves like a real engineering workflow rather than a single prompt-response tool.

It includes:

- a planner agent to break the task down
- a repository explorer to find relevant files
- a coder agent to implement changes
- a tester and debugger loop
- a reviewer for validation
- a human approval gate before finalizing work
- a live dashboard for task monitoring and diffs

## Why BuildMind AI

Most AI coding tools generate code in one shot. BuildMind AI follows a multi-step engineering workflow that makes the process observable and controllable.

This gives you:

- clearer task progression
- better traceability of agent activity
- human-in-the-loop review before final output
- better debugging and test validation
- a structured task dashboard for ongoing work

## Features

- Create tasks from a local repo or GitHub repository URL
- Real-time task timeline and execution logs
- Agent-by-agent status tracking
- Code change review with diff viewer
- Automated test execution and debugging retry flow
- Human approval and revision handling
- Git-oriented workflow and summary reporting
- Next.js dashboard UI for managing tasks and monitoring progress

## Architecture

```text
Frontend (Next.js)
    │
    ▼
Backend (FastAPI + LangGraph)
    │
    ├── Planner
    ├── Explorer
    ├── Coder
    ├── Tester
    ├── Debugger
    ├── Reviewer
    ├── Human Approval
    ├── Git Manager
    ├── GitHub PR
    └── Final Report

Storage / runtime
    ├── PostgreSQL
    ├── Redis
    └── Local repository workspace
```

## Tech stack

- Frontend: Next.js 16, TypeScript, Tailwind CSS
- Backend: Python, FastAPI, LangGraph
- Database: PostgreSQL
- Event streaming: Redis
- AI layer: OpenAI-compatible LLM provider
- Version control: Git / GitHub integration

## Project structure

```text
buildmind-ai/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── api/
│   │   ├── cache/
│   │   ├── db/
│   │   ├── llm/
│   │   ├── tools/
│   │   ├── config.py
│   │   ├── graph.py
│   │   ├── main.py
│   │   └── state.py
│   ├── requirements.txt
│   ├── .env
│   └── .env.example
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── package.json
├── mock_llm_server.py
├── README.md
└── .gitignore
```

## Prerequisites

Before starting the app locally, make sure you have:

- Python 3.11+
- Node.js 18+
- PostgreSQL installed and running
- Redis installed and running
- Git installed

## Local setup

### 1) Start the backend

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

On Windows PowerShell:

```powershell
cd backend
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 2) Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:3000
```

## Environment variables

The backend uses environment variables for AI and infrastructure settings.

Example:

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.6-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=your_api_key
DATABASE_URL=postgresql+psycopg2://codepilot:codepilot_dev_password@localhost:5432/codepilot
REDIS_URL=redis://localhost:6379/0
WORKSPACE_ROOT=/tmp/codepilot_workspaces
```

For local testing, you can also point the app to a mock OpenAI-compatible local server instead of a live provider.

## Workflow example

A typical task goes through this lifecycle:

1. User creates a task with a repo URL or local path
2. Planner creates a plan
3. Explorer finds relevant files
4. Coder makes changes
5. Tester validates the result
6. Debugger handles failures
7. Reviewer checks the patch
8. Human approves or requests changes
9. Final report and git workflow complete the task

## Deployment

This project is split between a frontend and a backend, so the recommended deployment pattern is:

- Frontend: deploy to Vercel
- Backend: deploy separately to Render, Railway, Azure App Service, or a similar Python host
- Connect them via environment variables

Example frontend env value:

```env
NEXT_PUBLIC_API_URL=https://your-backend-url.com
```

## Notes

- This project is designed for local AI workflow experimentation and guided engineering automation.
- Human approval is intentionally included in the workflow before finalizing code.
- The backend depends on PostgreSQL and Redis to work correctly in a real environment.

## License

This project is currently intended for development and experimentation. Add or update the license file before public distribution or commercial use.

## Contributing

Contributions are welcome. If you want to improve the workflow, UI, agent logic, or deployment path, open a pull request with a clear description of the change and expected behavior.





