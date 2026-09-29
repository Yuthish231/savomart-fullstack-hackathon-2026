# Savo SiteScout — Savomart Expansion Intelligence Platform

_One-line pitch: [e.g. "Turns Chennai's public data into a ranked, explainable map of where Savomart should open next, and carries every property from first sighting to catchment sign-off."]_

Built for the Savomart Full Stack Engineer 48-hour hackathon (28–30 Sep 2026).

---

## Contents

- [Demo](#demo)
- [Quick Start](#quick-start)
- [Demo Credentials](#demo-credentials)
- [Architecture Overview](#architecture-overview)
- [Data Model & Schema](#data-model--schema)
- [Data Sources & Processing](#data-sources--processing)
- [Scoring & AI — How It Works, and Stays Grounded](#scoring--ai--how-it-works-and-stays-grounded)
- [Tech & Library Choices](#tech--library-choices)
- [Design Decisions & Trade-offs](#design-decisions--trade-offs)
- [Known Issues & What We'd Improve](#known-issues--what-wed-improve)
- [AI Tool Usage](#ai-tool-usage)
- [Milestone Status](#milestone-status)

---

## Demo

- **Video walkthrough (3–5 min):** [TODO — Google Drive link, "Anyone with the link can view"]
- **Live deployment (optional bonus):** [TODO — URL, or "Not deployed; run locally, see Quick Start"]

---

## Quick Start

### Prerequisites

- Python 3.12
- Node.js 20
- Docker (for PostgreSQL 16 + PostGIS 3.4; exposed on port **5433** so it won't clash with a local Postgres)
- Optional: a Groq API key (free at console.groq.com). Without it, the app runs with template narratives.

### 1. Clone and configure

```bash
git clone <repo-url>
cd savomart-fullstack-hackathon-2026
cp .env.example .env   # add LLM_API_KEY (and STORES_API_TOKEN for ingestion)
docker compose up -d db
```

### 2. Backend (API + worker)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
alembic upgrade head
python -m scripts.seed          # demo personas
uvicorn app.main:app --port 8000 --reload
# in a second terminal (same venv):
python -m app.jobs.worker       # processes reports, evaluations, study jobs
```

API runs at `http://localhost:8000` (interactive docs at `/docs`).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` (it proxies `/api` to the backend).

### 4. Data ingestion (if not bundled with seed data)

```bash
[script to fetch/process OSM, Census, pincode data, etc.]
```

> Large raw datasets are fetched by script, not committed. See [Data Sources & Processing](#data-sources--processing).

---

## Demo Credentials

**No typing needed:** the login screen lists every seeded persona, and one click enters as that user. Once inside, the avatar menu (top right) switches persona at any time. Roles are still enforced by the API on every request (JWT + role guards); the switcher simply gets a token for a seeded user while `DEMO_MODE` is on.

For password login (`POST /api/v1/auth/login`), every seeded user shares the password `DEMO_PASSWORD` in [`backend/scripts/seed.py`](backend/scripts/seed.py).

| Persona | Username | Notes |
| --- | --- | --- |
| BD Manager | `bdm.priya` | Desktop-first |
| BD Executive | `bde.arjun`, `bde.divya` | Two executives, so scouting can be assigned |
| Survey Manager | `sm.karthik` | Desktop-first |
| Survey Executive | `se.meena`, `se.rahul`, `se.farhan` | Three surveyors, so survey work can be split |

---

## Architecture Overview

> Full design with diagrams (system context, containers, ER model, sequence and state diagrams): **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**

```
 React + TS PWA (MapLibre, TanStack Query, Dexie outbox)
        │ REST /api/v1 (JWT, role guards)
 FastAPI ── domain services (scoring · evaluation · pipeline · splitter · reuse · rollup)
        │                      ▲ claim jobs (SKIP LOCKED)
        ▼                      │
 PostgreSQL + PostGIS ◄──── Worker ──► Groq (gpt-oss-120b) via OpenAI-compatible adapter
  ref.* (OSM, pincodes, census, stores, H3 features)   app.* (areas, reports, properties, studies, jobs)
        ▲
 ingest/ (Overpass · OGD · Census · Stores API → clean → H3 precompute)
```

- **Frontend:** React 18 + TypeScript + Vite, Tailwind + shadcn/ui, TanStack Query; PWA for phone-first field flows.
- **Backend:** FastAPI + SQLAlchemy 2 / GeoAlchemy2 + Alembic; typed DTOs and auto OpenAPI docs.
- **Database:** PostgreSQL 16 + PostGIS 3.4 (Docker) — spatial queries, transactions and the job queue in one store.
- **Background processing:** Postgres-backed job table + worker process; checkpointed steps, heartbeat, retry-from-failed-step; UI polls step progress.
- **LLM integration:** Groq `openai/gpt-oss-120b` through an OpenAI-compatible adapter (`LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`); narrates precomputed facts only, enforced by a grounding validator.
- **Map layer:** MapLibre GL + OpenFreeMap vector tiles; H3 hexes rendered client-side with h3-js.

---

## Data Model & Schema

_[Entity list + brief explanation of relationships — Areas, Reports, Properties, PipelineEvents, CatchmentStudies, Lanes, Users/Roles, etc.]_

| Entity | Purpose | Key fields |
| --- | --- | --- |
| `[Area]` | | |
| `[AreaFitnessReport]` | | |
| `[Property]` | | |
| `[PipelineEvent]` | Audit trail of stage moves | |
| `[CatchmentStudy]` | | |
| `[Lane]` | Unit of survey work | |

_[Link to a schema diagram or migration files if useful.]_

---

## Data Sources & Processing

Everything is loaded by a re-runnable pipeline into the `ref` schema. Every dataset writes a provenance row to `ref.data_source` (URL, licence, as-of date, row count, `is_mock`), and reports cite those rows.

```bash
cd backend
python -m ingest.fetch_osm   # Overpass downloads, tiled + cached in data/raw/osm (about 10 min, once)
python -m ingest.run_all     # boundaries → pincodes → stores → OSM → population → H3 grid → rents
```

| Source | Used for | How we processed it |
| --- | --- | --- |
| **OpenStreetMap via Overpass API** (ODbL) | POIs (shops, schools, hospitals, transit, offices, worship, parks), ~380k buildings, road network | Tiled queries over the CMA bbox with on-disk cache, mirror fallback and adaptive tile splitting when servers time out. De-duplicated across tiles and between node/way mappings of the same place (same name ≤ 30 m). Clipped to the CMA polygon. POIs classified by [`ingest/categories.py`](backend/ingest/categories.py) into footfall weights and grocery competitor tiers (organised chain / supermarket / kirana), including brand-name regexes that tolerate misspellings. Roads split at every intersection and into ≤ 250 m **lane segments** with stable ids (`<way>:<seq>`) for survey work and reuse. |
| **DataMeet Municipal Spatial Data** (CC BY 4.0) | CMA boundary (1,188 km²), 200 GCC ward polygons | The 107 wards in zones IV, V, VI, VIII, IX, X, XIII form the pre-2011 city (172.7 km², which matches the historic 174 km²), used as the footprint of Census 2011 "Chennai (M Corp.)". |
| **All India Pincode Boundary** (data.gov.in / India Post; OGD licence) | Pincode selection, labels, rent bands | Read from the GeoParquet mirror in [`yashveeeeeeer/india-geodata`](https://github.com/yashveeeeeeer/india-geodata). Multi-part pincodes unioned, kept if ≥ 5% inside the CMA (124 pincodes). |
| **Census of India 2011** | Population baseline | Control totals: Chennai (M Corp.) 4,646,732 and Chennai UA 8,653,521. **Dasymetric allocation:** each zone's population is spread over OSM buildings by residential weight (floors × residential likelihood). This is a 2011 baseline, so scores use city-relative percentiles and M3 lane surveys override it. |
| **Savomart Stores API** (internal) | Nearest-store distance, cannibalisation, network gap | Filtered to `zone == CHN` (11 stores). A committed snapshot is used when no token is configured. Coordinates are treated as authoritative: 2 stores' address pincodes disagree with where their coordinates fall (e.g. Thiruvanmiyur lists 600068 but sits in 600041). |
| **Nominatim** (runtime) | Locality search | 1 req/s, identifying User-Agent, results cached. |
| **MOCK rent bands** | Rent sanity check in property evaluation | No public commercial-rent source exists. Generated per pincode from distance to the central retail belt. `is_mock = true` in the DB and **shown with a MOCK badge in the UI**. |

**Precomputed H3 grid:** every H3 res-9 cell (~0.1 km²) in the CMA stores population, buildings, footfall points, competitors by tier, road length and distance to the nearest Savomart store. Each cell also stores a *neighbourhood* view (the cell plus 2 rings, ~2 km², about the size of a locality) whose densities form the city-wide percentile tables used by scoring.

---

## Scoring & AI — How It Works, and Stays Grounded

_[Explain the Area Fitness scoring model: which signals feed it, how they're weighted, what's rule-based vs LLM-generated.]_

_[Explain how the property evaluation combines public + field data.]_

**How we stop the AI from inventing numbers:**
- [e.g. "The LLM only ever summarizes/reasons over numbers we've already computed and pass into its prompt — it never generates a data point itself."]
- [e.g. "Every claim in a report links back to its source dataset and as-of date."]
- [Any other grounding strategy: retrieval, structured prompts, validation checks, etc.]

---

## Tech & Library Choices

| Choice | Why |
| --- | --- |
| [Backend framework] | |
| [Database] | |
| [Map library] | |
| [LLM provider] | |
| [UI library] | |
| [Notable open-source libraries used] | |

---

## Design Decisions & Trade-offs

_[The open-ended calls the brief left to you — be explicit about why, not just what:]_

- **Pipeline stages (M2):** [what stages you chose and why]
- **Catchment splitting (M3):** [how you split work into fair, non-overlapping chunks]
- **Reuse threshold (M3):** [what "close enough and fresh enough" means in your implementation]
- **Offline/weak-network handling (M3):** [what happens to a half-filled survey]
- **What we deliberately left out, and why**

---

## Known Issues & What We'd Improve

- [ ] [Known bug or rough edge]
- [ ] [Feature that's stubbed/mocked and why]
- [ ] [What you'd build next with another 48 hours]

---

## AI Tool Usage

_[Disclose which AI tools you used (Claude, ChatGPT, Cursor, Copilot, Claude Code, etc.) and how — e.g. scaffolding, debugging, data-cleaning scripts, README drafting.]_

Full AI chat sessions / history: see [`/ai-sessions`](./ai-sessions) or [TODO — linked exports].

---

## Milestone Status

- [ ] **M1 — Area Intelligence:** map selection (pincode / locality / grid cells), Area Fitness Report, save/compare/timestamp
- [ ] **M2 — Property Scouting:** mobile onboarding, auto-evaluation, pipeline with audit trail
- [ ] **M3 — Catchment Study:** request → split → assign → lane capture → roll-up, reuse logic
- [ ] Bonus: _[which one(s), if any]_

---

_© 2026 SAVOmart, an entity of Ebono Private Limited. Built by [Your Name] for the Full Stack Engineer hackathon._
