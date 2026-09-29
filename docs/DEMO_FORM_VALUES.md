# Demo Form Values

What to type into every form during the demo recording. Forms are listed in the order you meet them in the [demo script](DEMO_SCRIPT.md).

- Option names match the app exactly.
- The "What it shows" notes come from the evaluation rules in [`backend/app/services/evaluation.py`](../backend/app/services/evaluation.py).

> **Before the real take:** do one dry run with these values, then run `demo_seed --reset`. That removes your test property and makes the Lakshmi Towers reuse scene work again.

---

## 1. Explore: choose an area · BD Manager (Priya)

| Tab | Field | Enter |
| --- | --- | --- |
| **Pincode** | Search box | `600020` or `Adyar`, then pick it from the list |
| Locality | Search box | `Velachery` (extended cut only) |
| Grid cells | Click hexagons on the map | 5–10 neighbouring hexes (60 at most) |

Then click **Run Area Fitness Report**.

---

## 2. Assign a scouting task · BD Manager

Open the **Velachery (600042)** report and click **Assign** on hotspot #3.

| Field | Enter |
| --- | --- |
| **BD Executive** | ◉ **Arjun Kumar** |
| Note | `Ground-floor shops on the main road, 1,500+ sq ft, truck access preferred` |
| Due | 2–3 days from today |

Then click **Assign**.

---

## 3. Add a property · BD Executive (Arjun), phone view

**My tasks → Add property here**

### Step 1 · Pin

- Tap the map **inside the hotspot circle, away from the seeded pins**.
  - If **"Is this the same place?"** appears, move the pin further away, or tick the confirmation that it's a different property.
- **Note the MOCK rent band** shown on the check card (e.g. ₹70–110/sq ft). You need it for the rent in Step 2.

### Step 2 · Details: a good property that should get **Proceed**

| Field | Enter | What it shows |
| --- | --- | --- |
| **Name** \* | `Demo Shop, ground floor` | |
| Landmark | `Opp. bus stand` | |
| Type | **Shop** | |
| **Floor** \* | **Ground** | Floor: *good* |
| **Carpet area** \* | `2000` | Inside the 1,500–4,000 target: *good* |
| Frontage | `30` | 25 ft or more: *good* |
| Rent per month | Carpet × the **middle of the band**, e.g. `180000` for a ₹70–110 band | Hint shows **"≈ ₹90/sq ft"**. Within the band: *good* |
| Deposit | `1800000` | |
| Delivery access | **Truck** | *good* |
| Visibility | **Main road** | *good* |
| 2W parking | `12` | 10 or more: *good* |
| Car parking | `2` | |
| Power | `25` kW | |
| Lease | `9` yrs | |
| Landlord | `Mr. Raghavan (demo)` | |
| Landlord phone | `90000 12345` | Clearly fake, so no real number appears on video |
| Notes | `Owner open to 9-year lease, side lane for unloading` | |

### Step 3 · Photos (optional)

- Slots: **Shop front / Inside / Street view**, plus **Add another photo**.
- Use 1–3 images from your PC, or skip the step.

Then click **Submit for evaluation**.

### Optional: properties that get **Review** or **Reject**

| Field | **Review** (good area, poor unit) | **Reject** (blocker) |
| --- | --- | --- |
| Floor | **First** | Ground |
| Carpet area | `1000` | `700` (under 800 is a blocker) |
| Frontage | `10` | `15` |
| Rent | Well above the band, e.g. `200000` | any |
| Delivery access | **2-wheeler only** | **None** (also a blocker) |
| Visibility | **Inside lane** | Side street |
| 2W / Car parking | `0` / `0` | `2` / `0` |

Leaving **Rent** empty adds a *Rent missing* flag.

---

## 4. Pipeline actions · BD Manager (buttons on the property page)

Every button opens the same modal with one text box. Rows marked **(required)** can't be confirmed without a reason.

| Button | Reason / note to type |
| --- | --- |
| Shortlist | `Strong score, truck access` |
| Ask executive to visit | `Confirm frontage and loading access` |
| Visit done, start negotiation **(required)** | `Visited: 30 ft frontage, trucks can unload; owner open to 9 years` |
| Request catchment study | `Terms viable; confirm the catchment first` |
| Skip study (existing data suffices) **(required)** | `Recent survey data already covers this area` |
| **Reject** **(required)**, e.g. Kamaraj Salai shop | `Too close to Savomart Thiruvanmiyur (~0.4 km); would cannibalise` |
| Put on hold **(required)** | `Landlord travelling; resume next week` |
| Resume | `Landlord back, continuing` |
| Reopen **(required)** | `Landlord reduced rent; re-evaluating` |
| **Approve site**, e.g. Sri Venkateswara Complex | `Catchment confirmed; proceed to agreement` |
| Add a note | `Landlord will reply by Friday` |

---

## 5. Request an area catchment study · BD Manager

- **Where:** the **Ground-truth this area** card on a report page, then **Request catchment study**.
- **What to fill in:** nothing. The button opens the new study directly.

---

## 6. Plan and run a study · Survey Manager (Karthik)

| Control | Choose / enter |
| --- | --- |
| Chunk size chips | **~3 km each** (default), then **Split** (**Re-split** if chunks already exist) |
| Assignee dropdown per chunk | A → **Meena Lakshmi**, B → **Rahul Nair**, C → **Farhan Ali** |
| **Complete study** → *Close and roll up* **(required)** | `Enough lanes covered for a decision; remaining lanes are commercial` |
| **Resurvey anyway** (on a reused study, min 3 chars) | `Major new apartment blocks since the last survey` |

---

## 7. Lane survey · Survey Executive (Meena), phone view

**My assignments → Chunk A → tap a grey (to-do) lane**

**Mostly**, **Homes on this lane** and **Kiranas** are required to finish a lane.

| Question | Lane 1 (dense residential) | Lane 2 (quieter) |
| --- | --- | --- |
| **Mostly** \* | **Apartments** | **Houses** |
| **Homes on this lane** \* | **51–100** | **11–25** |
| **Kiranas / grocery shops** \* | Tap **+** twice → `1`, or three times → `2` | Tap **+** once → `0` (the first tap sets 0) |
| Chain store here | ☐ | ☐ |
| Buildings look | **Kept up** | **Old** |
| Parked vehicles | **Mixed** | **Mostly 2-wheelers** |
| People around now | **Busy** | **Quiet** |
| Delivery vehicle can enter | **Van** | **2-wheeler only** |
| Notes | `Sri Murugan Stores, Anand Provisions` | *(empty)* |

Then tap **Done · next lane**.

- **Offline moment (lane 2):** before tapping Done, turn on **DevTools → Network → Offline**.
  - The badge shows **"Offline · 1 to sync"**.
  - Switch back to **No throttling** and the badge changes to **"Synced"**.
- **Skip a lane (lane 3):** tap **Skip lane**, then **Gated / no entry**.
  - Other skip reasons: *Not residential*, *Under construction*, *Can't reach*, *Other*.

---

## 8. No input needed

- **Login / Switch persona:** one click on the persona.
- **Compare:** on **Reports**, tick 2–3 reports, then click **Compare**.
- **Colour by chunk / status:** toggle on the study map.
- **Retry:** on a failed or partial report.

---

## Seeded personas (for switching)

| Persona | Name | Username |
| --- | --- | --- |
| BD Manager | Priya Raman | `bdm.priya` |
| BD Executive | Arjun Kumar, Divya Shankar | `bde.arjun`, `bde.divya` |
| Survey Manager | Karthik Subramanian | `sm.karthik` |
| Survey Executive | Meena Lakshmi, Rahul Nair, Farhan Ali | `se.meena`, `se.rahul`, `se.farhan` |
