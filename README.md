# CodePilot — Autonomous Software Engineering Agent

**Status: Phase 6 of 8** (see roadmap below). Adds the Next.js dashboard
and real-time streaming. This phase involved genuinely live-testing the
running application (backend + frontend, real Postgres/Redis, a local
mock LLM server standing in for real API credentials) rather than only
reviewing code — which is how the bugs below were actually found.

## What Phase 6 adds

1. **Real-time SSE streaming** (`GET /api/tasks/{id}/stream`): task
   execution now runs in a background thread (`app/api/routes.py`)
   instead of blocking the HTTP request, so there's something to actually
   stream *while it happens* — a real architectural gap in Phases 1-5,
   where the whole graph ran synchronously inside the request handler and
   any "streaming" endpoint could only ever replay history after the fact.
2. **Next.js 16 + TypeScript + Tailwind dashboard** (`frontend/`):
   - `/dashboard` — task list
   - `/tasks/new` — task creation form (repository path or GitHub URL,
     task description, branch name)
   - `/tasks/[id]` — the main task screen: left panel (plan + relevant
     files), center panel (live agent timeline + approval actions + final
     report), right panel (live log/event stream), bottom panel (diff
     viewer per changed file)
   - `/settings` — read-only view of the backend's non-secret config
   - `/projects`, `/projects/[id]` — honest placeholders (see Limitations)
3. **`GET /api/settings/public`**: new endpoint exposing non-secret config
   (LLM provider/model, retry limits, Docker sandbox status, whether
   GitHub is configured) for the Settings page.

## Four real bugs found by actually running this, not just reading it

All four were invisible from code review alone — they only showed up once
I stood up real Postgres, real Redis, a local mock OpenAI-compatible
server (no real API credentials available in this environment), and drove
the actual running FastAPI app with real HTTP requests and a real SSE
client:

1. **Streaming had nothing to stream.** The original design ran the whole
   LangGraph invocation synchronously inside `POST /api/tasks`, so by the
   time any client could open an SSE connection, the run was already
   over. Fixed by moving execution to a background thread with explicit
   `_running_tasks` bookkeeping (also used to reject a double-approve).
2. **A pub/sub race could silently drop events.** The first streaming
   design used Redis pub/sub, which doesn't buffer for late subscribers —
   an event published in the gap between "check if the task is still
   running" and "subscribe" would vanish. Replaced with polling the
   durable Redis *list* instead: every `publish_event()` is a persisted
   `RPUSH`, so a poll can never miss an entry, only see it slightly later.
3. **Backlog replay stopped at the wrong pause.** `task_paused_or_completed`
   fires on *every* pause, including the mid-task human-approval
   interrupt, not just final completion. Replaying event history after an
   approval was hitting the *original* approval-pause event in the
   backlog and stopping immediately, hiding every event that actually
   happened after approval. Fixed by never treating backlog replay as
   stoppable — only a live-tailed event ends the stream.
4. **`str(SomeEnum.MEMBER)` is not the enum's value.** For a
   `class X(str, Enum)`, Python's default `Enum.__str__` returns
   `"X.MEMBER"` (e.g. `"TaskStatus.AWAITING_APPROVAL"`), not the actual
   value (`"awaiting_approval"`) stored in the JSON snapshot. This had
   been silently shipping since Phase 5's rewrite of the approve/reject/
   create-pr endpoints to load from Postgres snapshots — every one of
   those endpoints' status comparisons was comparing against the wrong
   string and would **always** return 409, and every status field in API
   responses and SSE events showed the ugly `"TaskStatus.X"` form instead
   of the clean value. It was never caught earlier because prior tests
   exercised the graph directly (`codepilot_graph.invoke(...)`, comparing
   real enum objects) rather than going through the actual HTTP
   `approve_task`/`reject_task` functions with real loaded snapshots.
   Fixed with one `status_value()` helper (`app/state.py`) used
   consistently everywhere instead of scattered `str()` calls, then
   re-verified the full create → stream → approve → stream → complete
   flow end-to-end.

Also caught mid-build: registering `human_approval` and `finalize_report`
as plain (untimed) graph nodes meant they'd never emit
`agent_started`/`agent_completed` events, so the frontend's timeline would
show them stuck at "pending" forever even after the task finished. Found
by cross-checking the frontend's `AGENT_PIPELINE` list against
`graph.py`'s actual node registrations before trusting the UI — fixed by
wrapping both in the same `_timed()` decorator as every other node, then
re-verified live that all ten pipeline stages now emit correctly.

## Verification methodology (and its limits)

- **Backend**: fully live-tested against real Postgres, real Redis, and a
  purpose-built mock OpenAI-compatible server
  (`mock_llm_server.py`, not part of the shipped app) returning canned
  responses for the Planner/Explorer/Coder/Reviewer calls — this let me
  drive the *actual* FastAPI app with real HTTP requests end-to-end
  without needing real LLM credentials.
- **Frontend**: `npm run build` compiles cleanly with zero TypeScript
  errors across all 7 routes; `next start` was run and every route was
  hit with a real HTTP request to confirm correct status codes. Every
  field name and shape the frontend expects was cross-checked line-by-line
  against the actual backend Pydantic models and event-publishing sites
  (this is exactly how bug #4 above and the timeline bug were caught).
- **What's not verified**: actual browser rendering, click-through
  interaction, and hydration behavior. Headless-browser testing
  (Playwright) isn't feasible in this environment — its browser binaries
  download from hosts outside this sandbox's allowed network list.
  Recommend a manual click-through (create a task, watch the timeline
  update live, approve it, check the diff viewer) before trusting the UI
  fully; the API contract it depends on is verified, the rendering itself
  is not.
- A **CVE audit surfaced during `npm install`**: the originally-scaffolded
  Next.js 14.2.15 had multiple known high/critical vulnerabilities.
  Upgraded to Next.js 16.3.5 (and React 19) and fixed the resulting
  breaking change (`params` became a Promise in page components) —
  `npm audit` now reports zero vulnerabilities.

## Project layout (additions marked)

```
codepilot/
  backend/
    app/
      api/routes.py            # background execution, SSE endpoint, settings endpoint
      cache/redis_client.py     # + tail_events() (list-polling, race-free)
      graph.py                  # + status_value() usage, human_approval/finalize_report now timed
      state.py                  # + status_value() helper
  frontend/                     # NEW
    app/
      layout.tsx, globals.css
      dashboard/page.tsx
      projects/page.tsx, projects/[id]/page.tsx
      tasks/new/page.tsx
      tasks/[id]/page.tsx        # the main 4-panel live task view
      settings/page.tsx
    components/
      StatusBadge.tsx, AgentTimeline.tsx, DiffViewer.tsx, ApprovalPanel.tsx
    lib/
      types.ts                  # mirrors backend response shapes exactly
      api.ts                    # fetch client + EventSource SSE hook
  mock_llm_server.py             # test-only, not part of the shipped app
```

## Running it

```bash
# Backend (see Phase 5 section for Postgres/Redis setup)
cd backend
pip install -r requirements.txt --break-system-packages
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
cp .env.local.example .env.local
npm run dev   # http://localhost:3000
```

## Roadmap (unchanged from spec)

| Phase | Adds |
|---|---|
| 1 ✅ | Backend, LangGraph, Planner/Explorer/Coder/Test agents, local repo |
| 2 ✅ | Docker sandbox, Debugger agent, bounded retry loop |
| 3 ✅ | Code Reviewer agent, human approval checkpoint, diff viewer |
| 4 ✅ | Workspace isolation, Git operations, GitHub integration, PR creation, final report |
| 5 ✅ | PostgreSQL, Redis, persistent task history, Postgres-backed checkpointing |
| 6 ✅ | Next.js dashboard, real-time SSE streaming |
| 7 | LangSmith tracing, evaluation framework, metrics dashboard |
| 8 | Auth/authz, rate limiting, monitoring, Docker deployment, docs |

## Limitations (current phase)

- `/projects` and `/projects/[id]` are honest placeholders — the
  `Project`/`Repository` DB models exist but the API has no CRUD
  endpoints for them yet; every task is created directly against a
  repository path/URL without a project grouping.
- No Monaco Editor integration yet — the diff viewer is a plain, colored
  `<pre>` block, not a full code editor widget.
- No browser-level (Playwright/click-through) test coverage — see
  Verification methodology above.
- No auth on the API or frontend yet (Phase 8) — anyone who can reach
  either can see/act on any task.
- SSE reconnection is basic (`EventSource`'s built-in retry); no explicit
  resume-from-last-event-id handling if the connection drops mid-stream
  (the next page load's initial `getTask()` + fresh stream call covers
  this in practice, but a dropped connection isn't seamlessly resumed).





