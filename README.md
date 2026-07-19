# FinSight AI

[简体中文](./readme_cn.md)

FinSight AI is an evidence-driven financial research workspace built with **Vue 3 + FastAPI**. It helps a personal researcher answer four daily questions:

- What changed today?
- Why does it matter?
- Which symbol, report, risk item, alert, or note is affected?
- Where should I review the evidence next?

The project is not positioned as a trading or commercial product. It provides research review suggestions only, not buy/sell advice.

![FinSight Today Workspace](./images/today-workspace.png)

> Screenshots use clearly labeled Demo Mode data for product illustration. They do not represent live quotes or investment advice.

## Current Mainline

```text
Browser
  -> frontend-vue  (Vue 3 + Vite + ECharts)
  -> backend       (FastAPI + research services + optional LLM/RAG)
  -> local data / PostgreSQL in Docker
```

Legacy React and Spring migration experiments are no longer part of the active runtime path.

## Latest Repository Update (2026-07-19)

- Internal health now reports `degraded` when the LangGraph runner or checkpointer is not ready, instead of returning a false healthy status.
- Docker build contexts now exclude pytest temporary directories and local `tmp/` artifacts.
- The local Compose deployment was rebuilt and verified with `postgres`, `backend`, and `frontend` all reporting `healthy`.
- The frontend entry point and proxied `/health` endpoint were verified with HTTP 200 responses.
- GitHub-facing screenshots and both README variants now reflect the active seven-entry Vue workspace.

## Product Tour

| Symbol research dossier | Stock discovery |
| --- | --- |
| ![AAPL symbol research dossier](./images/symbol-dossier.png) | ![CN stock discovery](./images/stock-discovery.png) |
| Portfolio management | Reports library |
| ![Portfolio management](./images/portfolio-management.png) | ![Reports library](./images/reports-library.png) |
| Research notebook | AI research assistant |
| ![Research notebook](./images/research-notebook.png) | ![AI research assistant](./images/ai-assistant.png) |

## Highlights

- **Today Workspace**: daily summary, portfolio snapshot, watchlist, alerts, reports to review, and next actions.
- **Dashboard**: high-density market dossier with quote, chart, technical, valuation, sentiment, risk, news, and AI insight areas.
- **Chat Research Console**: streaming answer experience with execution trace, report mode, evidence panel, and Markdown export.
- **Portfolio Risk Lens**: position risk scoring, concentration hints, trend snapshots, and review routing.
- **Research Notebook**: Markdown notes with image upload, ticker filtering, search, soft delete, and note timeline integration.
- **Evidence Timeline**: unified event stream across reports, alerts, notes, risks, and watchlist signals.
- **What Changed**: rule-based top changes, deduplicated and ranked with reasons and target routes.
- **Research Quality**: health score, stale report detection, low citation warnings, review status, and challenged conclusions.

## Repository History Note

Early development happened mostly in local workspaces and AI-agent sessions. This repository uses a clean local history rebuilt for release hygiene. The real project timeline is documented in [`docs/PROJECT_TIMELINE.md`](./docs/PROJECT_TIMELINE.md) with evidence sources and confidence labels instead of fabricated commit dates.

## Quick Start

### Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend-vue
npm install
npm run dev
```

Open the local Vite URL shown in the terminal. The frontend defaults to the FastAPI backend at `127.0.0.1:8000` in local development.

### Docker Compose

After configuring `.env.server`, build and start the complete local stack:

```powershell
docker compose up -d --build
docker compose ps
```

Open `http://localhost/`. The default Compose stack keeps FastAPI and PostgreSQL on the internal Docker network and exposes the nginx frontend on port 80.

## Configuration

Copy the example files and fill in local-only values:

```powershell
Copy-Item .env.example .env
Copy-Item .env.server.example .env.server
```

Do not commit real secrets. Required production blockers are tracked in [`docs/RELEASE_READINESS.md`](./docs/RELEASE_READINESS.md):

- `JWT_SECRET`
- `API_AUTH_KEYS`
- valid `OPENAI_COMPATIBLE_API_KEY` or compatible LLM provider key

## Validation

```powershell
python -m pytest -q
cd frontend-vue
npm run typecheck
npm run build
npm run test:e2e
```

GitHub Actions runs frontend lint/build/E2E checks, the backend pytest suite, retrieval and RAG quality gates, and Docker smoke validation.

## Documentation

- [`docs/DOCS_INDEX.md`](./docs/DOCS_INDEX.md): documentation map.
- [`docs/DELIVERY_OVERVIEW.md`](./docs/DELIVERY_OVERVIEW.md): Phase 4-9 delivery summary.
- [`docs/PROJECT_TIMELINE.md`](./docs/PROJECT_TIMELINE.md): evidence-based timeline.
- [`docs/RELEASE_READINESS.md`](./docs/RELEASE_READINESS.md): current release readiness and blockers.
- [`docs/API_CONTRACT_CURRENT.md`](./docs/API_CONTRACT_CURRENT.md): current API contract and demo/live behavior.
- [`docs/archive/PHASE_DELIVERY_ARCHIVE.md`](./docs/archive/PHASE_DELIVERY_ARCHIVE.md): Phase 4-9 source report archive.
- [`docs/01_ARCHITECTURE.md`](./docs/01_ARCHITECTURE.md): architecture overview.

## Safety Boundaries

- No trading recommendations are generated by rule-based modules.
- What Changed and Risk Lens provide research review routes, not buy/sell instructions.
- Secrets, databases, uploaded files, logs, local memories, and Playwright artifacts are ignored by default.
