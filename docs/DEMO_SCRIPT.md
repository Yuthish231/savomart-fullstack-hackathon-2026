# Demo Video Script

A recording guide for the 3–5 minute walkthrough the brief asks for: the core loop across all four personas, plus a short explanation of the architecture and key decisions.

- **Section 1:** get the app into a known state before recording.
- **Section 2:** the scene-by-scene script, with what to click and what to say.
- **Section 4:** the longer feature tour, only for an optional extended cut.
- **Form values:** what to type into every form is in [DEMO_FORM_VALUES.md](DEMO_FORM_VALUES.md).

---

## 1. Before you record (about 15 minutes)

### 1.1 Reset the demo data

Every scene below assumes a fresh seed. The seed takes a few minutes because it writes about 15 AI summaries inside Groq's free-tier rate limit.

```powershell
cd backend
.\.venv\Scripts\python -m scripts.demo_seed --reset
```

When it finishes it prints the property list. It should look like this:

| Code | Property | Stage | Why it's in the demo |
| --- | --- | --- | --- |
| SS-CHN-0001 | Sri Venkateswara Complex, ground floor | Final Review | Catchment study CS-0001 finished; evaluation v2 carries the survey data |
| SS-CHN-0002 | Lakshmi Towers retail unit | Negotiation | **The live reuse moment** (Scene 7); it's about 110 m from CS-0001 |
| SS-CHN-0003 | Balaji Arcade ground floor | Shortlisted | Strong location, truck access |
| SS-CHN-0004 | Balaji Arcade | Evaluated | Duplicate of 0003 suspected; no GPS, no rent |
| SS-CHN-0005 | Anna Nagar 2nd Avenue corner unit | Site Visit | Large corner unit |
| SS-CHN-0006 | Kamaraj Salai shop | Evaluated · **Reject** | About 0.4 km from the Savomart Thiruvanmiyur store, so it would take customers from our own store |
| SS-CHN-0007 | Usman Road first-floor unit | Evaluated · **Review** | Great area, poor unit (first floor, 950 sq ft, two-wheeler access) |

It also prints the studies: **CS-0001** COMPLETED and **CS-0002** (Anna Nagar area study) IN_PROGRESS.

> **The reuse moment only works once per seed.** Re-run `demo_seed --reset` before every retake.

### 1.2 Start the app (3 terminals, Docker Desktop running)

```powershell
docker compose up -d db
```
```powershell
cd backend; .\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```
```powershell
cd backend; .\.venv\Scripts\python -m app.jobs.worker
```
```powershell
cd frontend; npm run dev
```

Open **http://localhost:5173**.

### 1.3 Browser setup (Chrome)

- **Zoom:** 90–100%. Hide the bookmarks bar (Ctrl+Shift+B) and close other tabs.
- **Phone view** (BD Executive and Survey Executive scenes): press F12, then **Ctrl+Shift+M**, then choose *iPhone 12 Pro*. Practise toggling this once.
- **Offline test:** DevTools → **Network** tab → throttling dropdown (*No throttling*) → **Offline**.
- Dock DevTools to the **right** so the phone frame and the app both fit on screen.

### 1.4 Checks before you press record

- [ ] Open the Velachery report: the Assessment badge should say **"AI summary · … · numbers verified"**. If it says *Rule-based summary*, wait a minute (rate limit) and click **Retry**.
- [ ] After seeding, wait about **60 s** before triggering anything live, so Groq's per-minute token budget has recovered.
- [ ] Log in once as each persona you'll use, so the first page load isn't cold.
- [ ] Turn off Windows notifications (Focus assist).

### 1.5 Recording tool

- **Loom** or **OBS Studio**, if you want a webcam bubble.
- **Win+Alt+R** (Xbox Game Bar), or **Clipchamp** (built into Windows 11, also good for trimming).
- **Settings:** 1080p with a mic, and a quiet room.
- Do **one full dry run**, then reset and record for real.

---

## 2. The script (about 5:00)

Timings are targets. Trim dead time (loading, typing) in editing.

### Scene 1: Intro · 0:00–0:20 · Login screen

**Show:** the login screen listing the four personas. Click **Priya Raman, BD Manager**.

**Say:**
> "This is Savo SiteScout. Today a new Savomart store starts with BD executives driving around looking for vacant shops. SiteScout flips that: public data points the team at the right areas first. Then one workflow takes a site from *which area*, to *which property*, to *is the catchment right*, across four personas. Everything runs on real Chennai data."

### Scene 2: M1 Explore · 0:20–0:55 · BD Manager

**Show:**
1. The **Explore** map with the **Opportunity heatmap** on. Point out:
   - the purple Savomart store pins, mostly in the north and west;
   - the yellow-outlined top pockets in central and south Chennai.
2. The three selection tabs: **Pincode / Locality / Grid cells**.
3. Click a pincode on the map, or type one (for example **600020 · Adyar**), then click **Run Area Fitness Report**.

**Say:**
> "Every ~0.7 km² hexagon in Chennai is scored with the same model as the report. It's built from about 376 thousand OpenStreetMap buildings, Census 2011 population, pincode boundaries and our live store list. A manager can select an area by pincode, by locality name, or by clicking grid cells."

### Scene 3: M1 Area Fitness Report · 0:55–1:45

**Show, top to bottom:**
1. **The live steps:** *Gathering area data → Scoring and finding hotspots → Writing the summary*. Scores appear before the text is written.
2. **The score dial, grade (A/B/C/D) and confidence badge**, with reasons such as OSM coverage.
3. **Assessment:** the **"AI summary · openai/gpt-oss-120b · numbers verified"** badge. Hover one of the small purple **fact chips** to show the exact value and source behind a claim.
4. **"How the score was reached":** the six cards (demand, residential, footfall, competition, network gap, access). Read one across: *raw value → Chennai percentile → weight → points*.
5. **The map and "Scouting hotspots"**, named by nearest road, with distance to the nearest Savomart.
6. **"Data used":** each source with its as-of date and the **MOCK** badge on rents.

**Say:**
> "Rules calculate every number. The AI only writes the explanation, and a validator rejects any number that isn't in the facts, so it can't invent data. If it fails twice we fall back to a rule-based summary. Percentiles compare this area against every neighbourhood in Chennai, so 82 means denser than 82% of the city. Rents have no public source, so they're mock and labelled that way."

**Optional (10 s):** **Reports** → tick **Velachery** and **Anna Nagar** → **Compare**, showing sub-scores side by side.

### Scene 4: M2 Direct an executive · 1:45–2:00

**Show:** open the **Velachery (600042)** report. On hotspot **#3**, click **Assign** → choose **Arjun Kumar** (the picker shows each executive's open-task count) → add a note → **Assign**.

**Say:**
> "The manager turns hotspots into scouting tasks for executives."

### Scene 5: M2 Field onboarding · 2:00–2:50 · BD Executive, phone view

**Show:**
1. Avatar menu (top right) → **Switch persona → Arjun Kumar**. Turn on the phone view (Ctrl+Shift+M). Point out the bottom tab bar.
2. **My tasks:** the task just assigned, with the hotspot map, **Directions**, and **Add property here**.
3. **Add property here → Step 1 · Pin.** Tap the map to move the pin. The check card updates with:
   - locality and pincode;
   - the typical rent band, marked **MOCK**;
   - a **"Is this the same place?"** warning if the pin is near an existing property.
4. **Step 2 · Details:**
   - Name (e.g. *Demo shop*) and carpet area **2000**.
   - Rent **180000**. Point at the live **"≈ ₹90/sq ft"** hint.
   - Chips: *Ground*, *Truck*, *Main road*.
5. **Step 3 · Photos:** optional; mention that photos are compressed on the phone.
6. **Submit for evaluation.** The property page shows *evaluating…* for a few seconds, then the score and recommendation.

**Say:**
> "It's phone-first. Drafts are saved on the phone, so nothing is lost when the app closes, and photos are compressed before upload. On submit it's evaluated automatically: 60% location from public data around the pin, 40% site checks such as size, rent, floor and access. A pin far from the phone's GPS, missing rent and look-alike duplicates are flagged for the manager."

### Scene 6: M2 Decide · 2:50–3:30 · BD Manager, desktop view

**Show:**
1. Switch back to **Priya** and turn the phone view off. Open **Pipeline**, which shows the banner *"N newly evaluated properties need your decision"*.
2. **Kamaraj Salai shop (SS-CHN-0006):** recommendation **REJECT**. The high-severity risk says it's only ~0.4 km from the Savomart Thiruvanmiyur store, so it would take customers from our own store.
3. **Usman Road first-floor unit (SS-CHN-0007):** **REVIEW**. The location score is excellent, but open **Site checks**: first floor, 950 sq ft, 12 ft frontage, two-wheeler-only access.
4. **Balaji Arcade (SS-CHN-0004):** the **Duplicate suspected** flag linking to SS-CHN-0003, plus *No GPS* and *Rent missing*.
5. On Kamaraj Salai, click **Reject**. Show that a **reason is required**, type *Too close to existing store*, and confirm. Scroll to **History** to show who did what, when, and why.

**Say:**
> "The decision card is built to take about 30 seconds: score, recommendation, what's in its favour against the risks, and a map of competitors and our own stores. Stage moves follow fixed rules, need a reason where it matters, and everything is logged."

### Scene 7: M3 Catchment study and reuse · 3:30–4:15

**Show:**
1. **Pipeline → Lakshmi Towers (SS-CHN-0002, Negotiation) → Request catchment study.** Open the new study from the property page.
2. It shows **full reuse**: about **88%** of the lane length was already surveyed within 180 days by **CS-0001**. It completes in seconds and the property moves to **Final Review**. No new fieldwork was needed.
3. Switch to **Karthik Subramanian (Survey Manager)** → **Studies → CS-0002** (Anna Nagar, in progress). Show:
   - the lane map coloured **by chunk**;
   - the chunk list with assignee, progress bar and last sync time;
   - the map toggled to **Colour by status** (surveyed, skipped, pending).
4. Switch to **Meena Lakshmi (Survey Executive)** and turn on the phone view. **My assignments** → open chunk **A**, then show the lane map and the lane list.
5. Tap a pending lane. Fill it in:
   - housing type and homes on this lane;
   - the **kirana** +/− stepper;
   - building condition, vehicles, footfall.
6. Offline test:
   1. DevTools → Network → **Offline**, then tap **Done · next lane**.
   2. The header badge changes to **"Offline · 1 to sync"**.
   3. Switch back to **No throttling**. The badge goes to **"Synced"**.

**Say:**
> "A catchment study splits the lanes within 500 m into fair, connected chunks of walking, grown along the real street network. Surveys are reused lane by lane: if 80% of the lane length was surveyed in the last 180 days, there's no new fieldwork. On the phone every tap is saved locally, so a half-filled lane survives a dead network and syncs later. Uploads are idempotent, so retries never create duplicates, and conflicting edits are caught with a version check."

### Scene 8: Insight and final decision · 4:15–4:35 · BD Manager

**Show:**
1. Switch to **Priya → Studies → CS-0001 → Catchment insight**. Point out:
   - about **10,600 households**, compared with the Census model;
   - **grocery shops counted on the ground vs just 1 in OpenStreetMap**;
   - the affluence index and housing mix;
   - the caveat **"Includes synthetic demo survey data"**.
2. **Sri Venkateswara Complex (SS-CHN-0001):** **Evaluation v2 (catchment)**, with the score change → **Approve site**.

**Say:**
> "The survey results feed back into the property as a new evaluation version with the change shown, and the manager approves. That's the full loop from area to approved site."

### Scene 9: Architecture and decisions · 4:35–5:00

**Show:** the container diagram in [ARCHITECTURE.md](ARCHITECTURE.md), and optionally http://localhost:8000/docs.

**Say:**
> "FastAPI and PostGIS in Docker, with a Postgres-backed job queue that has checkpointed steps and retry. React and TypeScript with MapLibre, and an H3 hexagon grid precomputed for the whole city. Key decisions: rules score and the AI only explains, with every number verified; honest data, where OSM gaps lower the confidence rating and mock rents are labelled; lane-level survey reuse; and offline-first field capture. Thanks!"

---

## 3. Recording tips

- **If an AI summary comes out rule-based during the take,** say *"and if the AI is unavailable or fails the grounding check, we fall back to a rule-based summary. The report never fails."* That's a feature too.
- **Use the seeded properties** in the manager scenes. They're set up to show proceed, review, reject, a duplicate and reuse.
- **Keep your cursor still** while talking over a screen, and move it deliberately to what you're describing.
- **Trim loading and typing** in editing. Clipchamp's split/delete is enough.
- **Record scenes separately** if that's easier, then join them. Resetting between scenes isn't needed, except before Scene 7 on a retake.

### Upload

1. Upload the video to **Google Drive**.
2. **Share → General access → "Anyone with the link" → Viewer.**
3. Open the link in a private window to confirm it plays without signing in.
4. Paste the link into the **[Demo](../README.md#demo)** section of the README, then commit and push.

---

## 4. Extended cut (optional extra features)

Only for a longer version. Keep the submitted video under 5 minutes.

| Feature | Where | What to show |
| --- | --- | --- |
| Locality search | Explore → Locality | Type *velachery* and select the real OSM boundary |
| Grid-cell selection | Explore → Grid cells | Click hexes to build a custom area |
| Report retry | A failed or partial report | **Retry** resumes from the failed step, not from scratch |
| Compare | Reports → tick 2–3 → Compare | Sub-scores side by side |
| Edit details | BD Executive → My properties → a property → Edit | Saving creates **evaluation v2**, with the change shown |
| Resume a draft | BD Executive → My properties | The **Unsent draft** card after leaving the wizard mid-way |
| Put on hold → Resume | BD Manager → property → Put on hold | Resume returns it to its previous stage |
| Re-split | Survey Manager → study → Re-split | Chunks of ~2/4/5 km of walking |
| Complete early | Survey Manager → study → Complete | Needs a reason; the roll-up uses what was surveyed |
| Resurvey anyway | Study with reuse | Overrides reuse, with a reason |
| Role guards | As a Survey Executive, open `/pipeline` | Redirected; the API also returns 403 |
| API docs | http://localhost:8000/docs | Every endpoint, typed |
| Data-quality report | `python -m ingest.verify` | Coverage, population totals and sanity checks |
| Tests | `python -m pytest -q` | 80 tests covering scoring, grounding, pipeline, evaluation, splitter and roll-up |
