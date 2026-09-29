# Savo SiteScout: Savomart Expansion Intelligence Platform

**Turns Chennai's public data into a ranked, explainable map of where Savomart should open next, then carries every property from first sighting to a ground-surveyed catchment sign-off.**

Built for the Savomart Full Stack Engineer 48-hour hackathon (28–30 Sep 2026).

---

## What it does

Today a new store starts with BD executives driving around looking for vacant shops. SiteScout flips that around: the data points the team at the right areas first, and one shared workflow takes a site from "which area?" to "which property?" to "is the catchment right?". It is built for four personas, and each one gets a view shaped around their job.

| Milestone | Who | What they can do |
| --- | --- | --- |
| **M1 Area Intelligence** | BD Manager | Pick any part of Chennai by pincode, locality or map grid cells and get an **Area Fitness Report**: a grade, six explainable sub-scores (demand, homes, footfall, competition, Savomart network fit, access), "scout here first" hotspots, and a summary that can only use numbers from the data. Reports are timestamped and can be compared. A **city-wide opportunity heatmap** shows the strongest pockets. |
| **M2 Property Scouting** | BD Manager, BD Executive | Assign hotspots to executives, who onboard properties from their phone (pin, details, photos). Each property is **automatically evaluated** (60% location from public data, 40% site checks) with insights, risks and a proceed / review / reject recommendation. Wrong pins, missing rent and likely duplicates are flagged. The manager moves properties through a pipeline with a full audit trail. |
| **M3 Catchment Study** | BD Manager, Survey Manager, Survey Executive | Request a lane-by-lane ground survey for a property or an area. The system **reuses recent surveys** of the same lanes, splits the rest into fair, connected chunks of walking, and lets surveyors capture lanes on their phone with **offline drafts that sync later**. Results roll up into catchment insights and automatically re-evaluate the property. |

**Built on real Chennai data:** OpenStreetMap (about 376k buildings, 11.7k points of interest, 208k street segments), India Post pincode boundaries (data.gov.in), Census 2011 population, DataMeet ward boundaries and the live Savomart stores list. Commercial rents have no public source, so they are **mock data and labelled MOCK** everywhere they appear.

**Stack:** FastAPI + PostgreSQL/PostGIS (Docker) · React + TypeScript + MapLibre · H3 hexagon grid · a Postgres-backed job queue · Groq `openai/gpt-oss-120b` behind a swappable, OpenAI-compatible adapter.

---

## Contents

- [How to Run](#how-to-run)
- [Demo](#demo)
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

## How to Run

### Prerequisites

- **Python 3.12**, **Node.js 20**, **Docker Desktop**
- Optional: a **Groq API key** (free at [console.groq.com](https://console.groq.com)). Without one, everything works and summaries are rule-based instead of AI-written.

> Commands use Windows paths (`.venv/Scripts/python`). On macOS/Linux use `.venv/bin/python`.

### First-time setup (about 20 minutes, mostly the one-off data download)

```bash
git clone https://github.com/Yuthish231/savomart-fullstack-hackathon-2026.git
cd savomart-fullstack-hackathon-2026
cp .env.example .env              # optional: put your Groq key in LLM_API_KEY
docker compose up -d db           # PostgreSQL 16 + PostGIS on port 5433

cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m alembic upgrade head          # create the schema
.venv/Scripts/python -m scripts.seed                  # demo users (4 personas)

.venv/Scripts/python -m ingest.fetch_osm              # download Chennai OSM data (about 15 min, cached)
.venv/Scripts/python -m ingest.run_all                # load, clean, precompute (about 90 s)
.venv/Scripts/python -m ingest.verify                 # should end with "all checks passed"
.venv/Scripts/python -m scripts.demo_seed --reset     # demo story: reports, properties, studies

cd ../frontend
npm install
```

### Start the app (every time)

The app needs four things running: the database, the API, the background worker and the web app. From the repo root, use one terminal per step:

```bash
docker compose up -d db                                                   # 1. database (skip if already running)
```

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000    # 2. API
```

```bash
cd backend && .venv/Scripts/python -m app.jobs.worker                     # 3. worker: reports, evaluations, study roll-ups
```

```bash
cd frontend && npm run dev                                                # 4. web app
```

Then open **http://localhost:5173** and click a persona to sign in (no password needed). API docs are at http://localhost:8000/docs.

**Tips**
- Without the worker running, reports and evaluations stay "queued".
- On Windows, run uvicorn **without** `--reload`: the reloader can hang and keep port 8000 busy. Restart the API after backend changes.
- To put the demo back to its starting state (e.g. before a walkthrough): `cd backend && .venv/Scripts/python -m scripts.demo_seed --reset`.
- Tests: `cd backend && .venv/Scripts/python -m pytest -q`.

### What the demo data contains

`scripts.demo_seed` runs the real code paths in-process and creates:
- 4 area reports: Velachery, Anna Nagar, Thiruvanmiyur, T. Nagar.
- Scouting tasks, and 7 properties across the pipeline, including a likely duplicate, a reject for being too close to an existing store, and a "review" for a good area with a poor unit.
- **CS-0001**, a completed catchment study.
- **CS-0002**, an area study half-way through fieldwork, so the survey screens have work to show.

CS-0001's lane surveys are **synthetic**: homes per lane come from real OSM building density, the other fields are random but plausible. They are flagged `is_seed`, and the app says "Includes synthetic demo survey data".

**To see survey reuse live:** as the BD Manager, open **Lakshmi Towers** (in Negotiation, about 110 m from CS-0001's site) and choose **Request catchment study**. Most of its lanes were already surveyed, so it completes in seconds without new fieldwork.

> Large raw datasets are fetched by script, not committed. See [Data Sources & Processing](#data-sources--processing).

---

## Demo

- **Video walkthrough (3–5 min):** [TODO — Google Drive link, "Anyone with the link can view"]
- **Live deployment (optional bonus):** Not deployed; run locally, see [How to Run](#how-to-run).
- **Walkthrough script:** [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) lists each scene, what to click and what it shows, so you can replay the demo yourself.

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

Two schemas: **`ref`** holds re-ingestable public data (it can be rebuilt without touching user data) and **`app`** holds workflow data. The ER diagram is in [docs/ARCHITECTURE.md §6.3](docs/ARCHITECTURE.md), and the migrations are in [`backend/alembic/versions`](backend/alembic/versions).

| Entity | Purpose | Key fields |
| --- | --- | --- |
| `ref.h3_cell` | Precomputed features per H3 res-9 cell (~0.1 km²) | population, buildings, footfall, competitors by tier, road length, nearest Savomart, `nbhd` densities, `opportunity` |
| `ref.lane_segment` | Road network split at intersections, ≤ 250 m; **stable ids** `<way>:<seq>` make reuse an exact join | highway, length_m, start/end node, geom |
| `ref.metric_stats` | City-wide p0..p100 breakpoints per metric | used for percentile scoring |
| `ref.data_source` | Provenance of every dataset | url, licence, as_of, is_mock |
| `app.area` / `app.area_report` | A selection (pincode / locality / cells → polygon + cells) and immutable report snapshots | sub_scores, hotspots, facts, narrative, data_sources, confidence |
| `app.job` | Postgres job queue | steps (checkpointed), status, heartbeat, attempts |
| `app.scouting_task` | BDM directs a BDE to a hotspot | report, hotspot, assignee, status |
| `app.property` | Onboarded site | pin + GPS fix, details, flags, stage, latest score |
| `app.property_evaluation` | **Versioned** evaluations (created / edited / catchment / manual) | location + site score, checks, insights, risks, facts, narrative |
| `app.pipeline_event` | Insert-only audit trail | kind, from → to, actor, reason, at |
| `app.catchment_study` | A study request against a property or area report | geom, status, reuse_mode/coverage, insight |
| `app.work_chunk` / `app.study_lane` | Partition of the study's lanes and per-lane progress | chunk assignee, lane status (todo / draft / done / skipped / reused) |
| `app.lane_survey` | One observation of one lane | phone `client_uuid` (unique), version, status, data, `is_seed` |

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
| **Census of India 2011** | Population baseline | Control totals: Chennai (M Corp.) 4,646,732 and Chennai UA 8,653,521. **Dasymetric allocation:** each zone's population is spread over OSM buildings by residential weight (residential likelihood; apartments ×4; generic buildings on industrial, port, rail, campus or commercial land down-weighted), then capped at 60,000 people/km² per hex with the excess redistributed within the zone. Floor counts are *not* used: only 1.8% of Chennai buildings carry them, a third of those in one zone, which had pushed George Town to an implausible 627k residents. **Check:** the population allocated to the 200 GCC wards (6.85M) lands within ~2% of the independent GCC 2011 figure. This is a 2011 baseline, so scores use city-relative percentiles and M3 lane surveys override it. |
| **Savomart Stores API** (internal) | Nearest-store distance, cannibalisation, network gap | Filtered to `zone == CHN` (11 stores). A committed snapshot is used when no token is configured. Coordinates are treated as authoritative: 2 stores' address pincodes disagree with where their coordinates fall (e.g. Thiruvanmiyur lists 600068 but sits in 600041). |
| **Nominatim** (runtime) | Locality search | 1 req/s, identifying User-Agent, results cached. |
| **MOCK rent bands** | Rent sanity check in property evaluation | No public commercial-rent source exists. Generated per pincode from distance to the central retail belt. `is_mock = true` in the DB and **shown with a MOCK badge in the UI**. |

**Precomputed H3 grid:** every H3 res-9 cell (~0.1 km²) in the CMA stores population, buildings, footfall points, competitors by tier, road length and distance to the nearest Savomart store. Each cell also stores a *neighbourhood* view (the cell plus 2 rings, ~2 km², about the size of a locality) whose densities form the city-wide percentile tables used by scoring.

---

## Scoring & AI — How It Works, and Stays Grounded

### Area Fitness model (`scoring_version = v1`, [`app/services/scoring.py`](backend/app/services/scoring.py))

**All scoring is deterministic, rule-based arithmetic.** The LLM never scores anything.

| Sub-score | Weight | Metric | How it becomes 0–100 |
|---|:-:|---|---|
| Demand | 25% | residents / km² | Chennai percentile |
| Residential fabric | 15% | residential buildings / km² | Chennai percentile |
| Footfall generators | 15% | weighted schools, hospitals, offices, transit, markets / km² | Chennai percentile |
| Competition | 20% | grocery competitors per 10k residents (chain ×3, supermarket ×2, kirana ×1), area + ~500 m ring | 100 − Chennai percentile |
| Savomart network fit | 15% | km to nearest Savomart store | distance band: < 2 km cannibalises, 3–8 km ideal, very far strains supply |
| Access | 10% | road km / km² (arterials weighted double) | Chennai percentile |

- **Percentiles are against every inhabited ~2 km² neighbourhood in the CMA**, precomputed at ingest. "Demand 82" literally means denser than 82% of Chennai. Ties use mid-rank, so sparse data isn't mistaken for a perfect score.
- **Grade:** A ≥ 75, B ≥ 60, C ≥ 45, D below.
- **Confidence (High / Medium / Low)** comes from data coverage: the share of street cells with mapped buildings, resident count, and whether any grocery shops are mapped. It is shown with its reasons.
- **Hotspots:** the best-scoring res-9 cells inside the area, at least ~600 m apart, each with its nearest named road and its two strongest signals.
- **The city-wide opportunity heatmap** uses the *same function* on every cell's neighbourhood, so the map and the reports can never disagree.
- **Explainability:** every sub-score card shows raw value → Chennai percentile → weight → points contributed, plus a plain-English definition.

### How we stop the AI from inventing numbers ([`app/llm/grounding.py`](backend/app/llm/grounding.py))

1. **The LLM only receives a fact table** (id, label, value, unit, source) built from the computed report, plus the hotspot list. It is told to use only those values and to cite fact ids for every reason and risk.
2. **A validator checks every number in the output** against the fact values. It allows legitimate display forms (48,213 → "48.2k" / "0.48 lakh", 0.42 → "42%", 1,250 m → "1.3 km") within rounding tolerance. It also rejects unknown fact ids and hotspot ids.
3. **On a violation, one retry** tells the model exactly which numbers were not allowed. If it still fails, or the LLM is down or unconfigured, the report keeps its **deterministic template narrative** and is marked `partial` with a visible "Rule-based summary" badge.
4. **The UI shows the provenance.** Fact citations are hoverable chips (value, unit, source), and every report lists the datasets it used with as-of dates and MOCK flags.
5. **Provider-agnostic:** Groq `openai/gpt-oss-120b` by default through an OpenAI-compatible adapter (`LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`), in JSON mode.

_Property evaluation (M2) and catchment roll-ups (M3) reuse the same fact-table + validator pattern._

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

- **Pipeline stages (M2):** Sighted → Evaluated → Shortlisted → Site visit → Negotiation → Catchment study → Final review → Approved, plus On hold / Rejected from any active stage. This mirrors how a BD team actually moves a site: desk evaluation before anyone travels, a physical visit before money is discussed, and the catchment study only once terms look viable (surveys cost field time). Transitions are a declarative table ([`services/pipeline.py`](backend/app/services/pipeline.py)) with role guards. Reject, hold and "skip study" require a reason. Executives can only report their own site visit. Every move writes an insert-only `pipeline_event` in the same transaction as the stage change.
- **Property evaluation (M2):** 60% location (the M1 model on ~1 km around the pin) + 40% site checks (size vs the 1,500–4,000 sq ft target, floor, frontage, delivery access, visibility, parking, rent vs the MOCK local band). Blockers force "reject" (under 800 sq ft, no vehicle access, under 0.8 km from an existing Savomart store). Unresolved data-quality flags (pin more than 150 m from the phone's GPS, suspected duplicate) keep it at "review". Every edit or re-run creates a new evaluation version, and the change is shown.
- **Bad field input (M2):** the wizard pre-checks the pin (inside the CMA, pincode, rent band, look-alikes within 50 m by distance + trigram name similarity) *before* submit. Missing rent is allowed and marked "incomplete" rather than blocking. Drafts persist on the phone across reloads and dropped networks. Photos are compressed on-device, then type- and magic-byte-checked on the server.
- **Catchment (M3):** a property's catchment is a 500 m radius (roughly a 6–7 minute walk, the core draw of a neighbourhood grocery). An area study samples 500 m around the report's top 3 hotspots rather than a whole 5–7 km² area, which would be weeks of fieldwork. Lanes are the pre-split OSM lane segments (≤ 250 m, residential/service/tertiary) whose midpoint falls inside.
- **Catchment splitting (M3):** [`services/splitter.py`](backend/app/services/splitter.py) partitions lanes into chunks of similar walking *effort* (length, busier roads ×1.5). It uses farthest-point seeds, then balanced region growing along the street graph (always extending the lightest chunk with its nearest adjacent lane), then boundary rebalancing and a merge of hemmed-in chunks. Every lane lands in exactly one chunk, so chunks can't overlap. A real-data finding: surveyable lanes alone fall apart into islands at every main road and at the circle's edge. So arterials and streets just outside the catchment act as *connectors* (union-find over their nodes). On real Chennai catchments this gives a max/min effort ratio of 1.2–1.5, and every chunk is contiguous except where a genuinely isolated island exists. The Survey Manager picks the effort per chunk (2–5 km) and can re-split until fieldwork starts.
- **Reuse threshold (M3):** *close enough* is measured on the actual lanes, not the distance between centroids. Each lane's latest submitted or skipped observation from any other study is reused if it is **under 180 days old**. If reused lanes cover **≥ 80% of the catchment's lane length**, no fieldwork happens and the insight is rolled up immediately (our demo: 88% reuse, insight in about 3 s). Otherwise only the uncovered lanes go to the field ("partial"). Managers can override with "Resurvey anyway" (a reason is required), e.g. after demolition or new construction.
- **Offline / weak network (M3):** every tap on the lane form is written to IndexedDB (Dexie) immediately, so a half-filled lane is a local *draft* that survives reloads, dead batteries and app switches. An outbox syncs on reconnect, every 20 s and on focus, using an idempotent `PUT /lane-surveys/{client_uuid}` (the UUID is generated on the phone), so retries can't duplicate. A `base_version` check returns 409 with the server copy if the lane changed elsewhere, and the conflict is flagged rather than silently overwritten. Opened chunks are cached on the phone and reopen with no signal. A header badge shows "Offline · N to sync". Drafts sync to the server too, so the Survey Manager sees "in progress" lanes and the last sync time per chunk.
- **Survey → evaluation (M3):** the roll-up extrapolates households over unsurveyed lane length (skipped lanes count as no homes) and compares the result with the Census-based model *for the same 500 m circle*. That survey/model **ratio** (not the dense core's raw density) is carried into the property's ~1 km evaluation, and surveyed kirana counts can only *raise* competition above what OSM mapped. The property is re-evaluated (new version, delta shown) and moves to Final Review.
- **What we deliberately left out, and why:** a service worker for a fully offline app shell (the data layer is offline-first; the shell must be opened once online), OSRM drive-time isochrones (straight-line distances are labelled), notifications, photo EXIF location checks, a real rent source (none is public), and the conversational analyst bonus. The M1–M3 loop came first.

---

## Known Issues & What We'd Improve

**Data limitations (found during ingestion, surfaced in the product rather than hidden):**
- **OSM building tags are ~98% generic** (`building=yes`) in Chennai, so "residential fabric" is effectively building density × floors. It correlates with demand. With more time: use OSM `landuse=residential` polygons or ISRO Bhuvan land-use/land-cover as a residential mask.
- **OSM under-maps kiranas.** The median Chennai neighbourhood has zero *mapped* grocery competitors. Scoring uses mid-rank percentiles, so "no mapped shops" is not rewarded as "no competition". Reports flag it in the confidence notes, and M3 lane surveys capture real kirana counts.
- **Population is a Census 2011 baseline** (the latest census with published town totals), redistributed by building footprint. Scores are city-relative percentiles, so uniform growth since 2011 does not change rankings, but uneven suburban growth (e.g. OMR) is under-represented.
- **Distances are straight-line**, not drive time. OSRM isochrones are the obvious upgrade.
- **Rents are MOCK** (no public source) and always badged as such.

**Engineering rough edges:**
- [ ] Uvicorn `--reload` on Windows can hang when files outside `app/` change. Restart the API manually after backend edits.
- [ ] [What you'd build next with another 48 hours]

---

## AI Tool Usage

_[Disclose which AI tools you used (Claude, ChatGPT, Cursor, Copilot, Claude Code, etc.) and how — e.g. scaffolding, debugging, data-cleaning scripts, README drafting.]_

Full AI chat sessions / history: see [`/ai-sessions`](./ai-sessions) or [TODO — linked exports].

---

## Milestone Status

- [x] **M1 — Area Intelligence:** map selection (pincode / locality / grid cells), Area Fitness Report, save/compare/timestamp
- [x] **M2 — Property Scouting:** hotspot → scouting task, mobile onboarding wizard, auto-evaluation (versioned), pipeline with audit trail
- [x] **M3 — Catchment Study:** request (property or area) → lane-level reuse check → split → assign → offline-first lane capture → roll-up → property re-evaluation
- [x] Bonus: **city-wide opportunity map** (every ~0.7 km² hex scored with the same model)
- [~] Bonus: **offline-first field capture** (IndexedDB drafts + idempotent sync outbox + cached chunks; no service worker for the app shell yet)

---

_© 2026 SAVOmart, an entity of Ebono Private Limited. Built by [Your Name] for the Full Stack Engineer hackathon._
