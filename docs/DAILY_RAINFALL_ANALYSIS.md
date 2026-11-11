# Daily Rainfall Calculation: Analysis and Recommendation

- **Date:** 2026-11-11 (~17:00 UTC / 22:30 IST)
- **Status:** analysis and recommendation for owner review. **Nothing here is implemented, and no decisions are final.**
- **Data used:** run 2026-11-11 00 UTC. Sample GRIB `data/raw/20261111T00Z/…` (unchanged, SHA-256 identical
  before and after); server metadata only (directory listing, `.index` files, HTTP headers); no new GRIB data downloaded.
- **Evidence files:** `docs/inspection/run_steps_20261111T00Z.txt`,
  `docs/inspection/demo_interval_subtraction_20261111T00Z.txt`, `docs/INSPECTION_20261111T00Z.md`
- **Scripts:** `scripts/list_run_steps.py`, `scripts/demo_interval_subtraction.py`

**Evidence labels:** **[V]** verified by us on real data or server responses · **[D]** stated in official
documentation (quoted) · **[H]** hypothesis · **[O]** open

---

## 1. What a running accumulation is, in plain language

Think of a **rain gauge that is never emptied**. A forecaster puts an empty gauge at a location when the
forecast starts (here 11 Nov, 00:00 UTC = 05:30 IST) and reads it every few hours without emptying it.
Each reading is *all the rain since the start*. ECMWF's `tp` values are exactly these gauge readings,
except they come from a computer model.

To know how much rain fell **between two readings**, subtract the earlier reading from the later one.
Real numbers from our file, at the heaviest-rain grid point in the Bay of Bengal (12.5°N 83.25°E):

| Reading (hours after start) | Gauge reading (total since start) |
|---|---|
| 144 h (17 Nov 05:30 IST) | 604.980 mm |
| 150 h (17 Nov 11:30 IST) | 644.043 mm |

Rain between 144 h and 150 h = 644.043 − 604.980 = **39.063 mm in 6 hours** (≈ 6.5 mm/h on average).
Exact check in the file's own units: 0.64404296875 m − 0.60498046875 m = 0.0390625 m. [V]

**A daily total works the same way:** reading at the end of the day minus reading at the start of the day.
Readings in between are not needed. Subtracting consecutive readings and adding up the pieces gives exactly
the same answer, because all the in-between readings cancel out (*telescoping*):
(R₂−R₁)+(R₃−R₂)+(R₄−R₃) = R₄−R₁.

### Limitations

1. **Readings exist only at fixed times (steps).** We can compute rain between two steps, never
   between arbitrary times. Where a day starts and ends is therefore constrained by the step schedule (§3).
2. **Readings are rounded.** Values are stored as whole multiples of a small increment that is chosen per field:
   **0.061 mm** in our early steps, **0.244 mm** in later steps [V]. So a computed interval is only accurate to
   roughly ±1 increment. Example: Assam (26.25°N 91.25°E), 144→150 h gives exactly **0.244 mm**, i.e. "one
   rounding unit". We cannot tell whether the true rain was 0.1 mm or 0.35 mm. [V/H]
3. **Readings occasionally go down slightly.** A real gauge can't lose water, but here ~0.03–0.1 % of points
   show a later total smaller than an earlier one, by ≤ 0.122 mm [V]. Subtracting then gives a small
   **negative** rainfall (§4).
4. **It is a grid-box average.** Per ECMWF: "It is the depth the water would have if it were spread evenly over
   the grid box." [D: param-db 228] A 0.25° box is ~28 km wide. A downpour on one village is spread over the
   whole box.
5. **It is a forecast**, and becomes less reliable at longer lead times. That is outside this analysis.

## 2. Forecast steps: what exists, and what we can rely on

### 2.1 Which steps a complete 00 UTC run contains

| Source | Statement | Label |
|---|---|---|
| Server directory listing for 2026-11-11 00z (`scripts/list_run_steps.py`) | **85 steps: 0–144 every 3 h (49 steps), 150–360 every 6 h (36 steps).** Every step has both `.grib2` and `.index`. | [V] |
| Same run, probe for step 147 h | HTTP 404, so 3-hourly steps stop at 144 h | [V] |
| ecmwf.int open-data page | "For times 00z &12z: 0 to 144 by 3, 150 to 360 by 6." | [D] |
| ECMWF Confluence open-data page | "00/12: 0–144h by 3h, 150–360h by 6h" | [D] |
| Installed `ecmwf-opendata` 0.3.35 README (line 416) | "0 to 144 by 3, 144 to 240 by 6" | **outdated**; contradicted by the server |

- The run now extends to **360 h (15 days)**, beyond our agreed 10-day (240 h) scope. Within 240 h there are
  **65 steps**; their `tp` messages total **33.3 MB** (from `.index` lengths) [V]. For comparison, a full step file with all
  variables is ~95–104 MB (HTTP `Content-Length`) [V].
- [V] Today's 00z files all show `Last-Modified: Wed, 11 Nov 2026 07:34:00 GMT` (= 13:04 IST). That matches
  the end of ECMWF's dissemination window for 00z steps 150–360 ("06:29 -> 07:34") [D: Confluence
  "Dissemination schedule"]. ECMWF says the 0.25° open data are "released at the end of the real-time dissemination
  schedule" [D: ecmwf.int open-data page]. **This is one observation of one run.**
- Retention: the official pages disagree. ecmwf.int says "the most recent 12 forecast runs … approximately 2–3
  days"; Confluence says "approximately 4 days". [D, conflicting] We should assume ~2 days at most.

### 2.2 Is accumulation always measured from initialisation?

| Evidence | What it shows | Label |
|---|---|---|
| GRIB headers of steps 0, 3, 6, 144, 150, 240 | `startStep=0`, `stepRange=0-N`, `typeOfStatisticalProcessing=1` (accumulation) | [V] for those 6 |
| ECMWF parameter database (tp, 228) | "the total amount of water accumulated over a particular time period which depends on the data extracted. The units … are depth in metres of water equivalent." | [D]; does **not** itself say "from the start" |
| `.index` files for all 85 steps | `step` field shows only the end step (e.g. `"144"`), **not** the window start | cannot verify the start this way |
| `tp` message sizes rise with step (248,839 B at 3 h → 655,360 B at 360 h) | Consistent with fields filling up with non-zero accumulated values | [H] weak hint only, not proof |

**Conclusion:** documented by ECMWF in general terms, and verified by us for 6 of 65 relevant steps.
**[O] Verifying it for every step needed would require downloading those steps' `tp` messages** (your call,
§5). Also [O]: the dip in message size at step 132 (629,119 → 524,466 bytes) is consistent with the
rounding increment becoming coarser there, but that is unverified.

### 2.3 Can we get values for consecutive 24-hour periods?

Yes, if the day boundaries fall on existing steps. Checked against the server's actual list [V]:

| Boundary time (UTC) | Steps needed (00z run, within 240 h + 1 day) | All present? |
|---|---|---|
| 00 UTC (= 05:30 IST) | 0, 24, 48, …, 240 | **yes** |
| 18 UTC (= 23:30 IST) | 18, 42, 66, …, 234 (and 258 for a full 10th day) | **yes** |
| 03 UTC (= 08:30 IST) | 3, 27, …, 123, **147, 171, 195, 219** | **no**: 147+ are missing |
| 18:30 UTC (= 00:00 IST) | 18.5, 42.5, … | **no**: no step exists at half hours |

### 2.4 What happens when a required step is missing

- **Whole step file missing (HTTP 404):** the ECMWF client calls `r.raise_for_status()` (`client.py` line 322),
  so the request **fails loudly**. [V, from source code]
- **File present but no `tp` inside:** the client only logs "No index entries for …" (lines 346–354) and
  **continues without that message**. This is a quiet failure. Our `download_sample.py` catches it by counting
  messages afterwards. [V, from source code]
- **Effect on the rainfall calculation:** because each daily total needs only its two boundary readings,
  - a missing **intermediate** step (e.g. 21 h) does **not** affect daily totals;
  - a missing **boundary** step (e.g. 42 h) makes **two** days uncomputable (the one ending and the one
    starting at 42 h). Their combined 48-h total would still be computable.
  - Filling a missing step by interpolation would invent data. Not recommended.

## 3. The daily time window

India Standard Time is **UTC + 5 h 30 min**. All GRIB times are UTC. Today's run: start = step 0 =
11 Nov 00:00 UTC = **11 Nov 05:30 IST**; published 07:34 UTC = **13:04 IST** (observed).

### Option A: calendar day, 00:00 → 00:00 IST
- In UTC: 18:30 → 18:30 the previous day. **No forecast step exists at 18:30 UTC.** Midnight IST always falls
  inside an interval: 18→21 UTC for the first 6 days, 18→24 UTC afterwards.
- Computing it exactly requires guessing how the rain in that interval is spread over time (e.g. "assume it rains
  evenly, so 30 of 180 minutes = 1/6 of the 18→21 h rain belongs to the previous day"). That assumption
  **cannot be verified** from our data, and it requires two extra steps per boundary.
- **A′ (practical variant): 23:30 → 23:30 IST = 18 UTC → 18 UTC.** All boundaries exist exactly (steps 18, 42, …,
  234) for both the 3-hourly and 6-hourly parts of the run. The only "error" is that rain falling between
  23:30 and midnight is counted under the next date. That is a fixed, honestly statable 30-minute offset,
  with no invented numbers.

### Option B: 05:30 → 05:30 IST = 00 UTC → 00 UTC
- All boundaries are exact steps (0, 24, …, 240), and the run start itself is a boundary.
- Exactly **10 complete days within 240 h**.
- But each "day" includes the first 5½ hours of the **next calendar date**. Example: rain at 03:00 IST on
  14 Nov is reported under "13 Nov".

### Side note: India Meteorological Department convention (08:30 → 08:30 IST = 03 UTC)
- [H, from my background knowledge, **not yet verified against an IMD source**] IMD's observed "rainfall day"
  runs 08:30 → 08:30 IST. Boundaries exist only up to step 123. Steps 147, 171, … do not exist, so only **5**
  complete days are possible [V]. Not viable for a 10-day product. Mentioned only for context.

### Side-by-side for today's run (00z, 11 Nov)

| | A (exact 00:00 IST) | **A′ (23:30 IST)** | B (05:30 IST) |
|---|---|---|---|
| UTC boundaries | 18:30 | 18:00 | 00:00 |
| Exact from data? | no, needs a timing assumption | **yes** | **yes** |
| Matches the calendar date farmers use | exactly | within 30 min | off by 5½ h |
| Days within 240 h | — | today (05:30–23:30, partial) + **9 full** (12–20 Nov) + 6 h stub | **10 full** (11–20 Nov) |
| Full 10th day | — | needs step 258 (exists; run goes to 360 h) | within 240 h |
| "Today" left when data appears (13:04 IST) | — | ~10.5 h | ~16.5 h (runs to 05:30 tomorrow) |
| Works with 12z run | — | yes (steps 6, 30, …, 246) | yes (12, 36, …, 252) |
| Steps needed for daily totals (≤240 h) | ~20+ | 11 (0, 18, 42, …, 234, [240]) | 11 (0, 24, …, 240) |

### Recommendation (for your decision)

**A′: daily totals from 23:30 IST to 23:30 IST (18 UTC → 18 UTC), labelled with the IST calendar date and with the
exact window stated in the UI and API.** Reasoning:
1. Farmers plan by calendar date ("will it rain on Thursday?"). A′ matches the date to within 30 minutes; B
   shifts 5½ hours of every night into the previous date.
2. A′ uses only real forecast values; exact midnight (A) would need invented timing.
3. All its boundary steps exist in both the 3-hourly and 6-hourly parts of the run, and for both 00z and 12z.

The cost is that the first day is partial (05:30–23:30 IST), and the 10th full day needs step 258, just beyond
240 h. Choose **B** instead if you value "exactly 10 complete days inside 240 h" and maximum simplicity over
calendar alignment.

## 4. A worked calculation with real values, and what a negative result means

From `docs/inspection/demo_interval_subtraction_20261111T00Z.txt` (exact grid points, no nearest-point logic):

| Location (grid point) | Interval | Later − earlier | Result |
|---|---|---|---|
| Bay of Bengal 12.5°N 83.25°E | 144→150 h | 644.043 − 604.980 | **+39.063 mm** |
| Nearest Chennai 13.0°N 80.25°E | 150→240 h | 26.123 − 3.418 | **+22.705 mm** |
| Nearest Chennai | 144→150 h | 3.418 − 3.418 | **0.000 mm** |
| Assam 26.25°N 91.25°E | 3→6 h | 0.000 − 0.061 | **−0.061 mm** |
| Jharkhand 23.25°N 84.75°E | 6→144 h | 0.000 − 0.122 | **−0.122 mm** |
| Eastern UP 25.5°N 82.75°E | 6→144 h | 0.000 − 0.061 | **−0.061 mm** |

**Our sample has no pair 24 h apart** (steps 0, 3, 6, 144, 150, 240), so no actual daily total can be shown
yet. The mechanics are identical, e.g. day 12 Nov under A′ = tp(42 h) − tp(18 h).

### What a slightly negative result means
- Rain cannot be negative. **−0.061 mm is not "evaporation" or "negative rain".** It means the two stored
  readings disagree by one rounding unit, in a place where essentially nothing fell (Assam: 0.061 mm after 3 h,
  then 0 after 6 h).
- Magnitudes seen: −0.061 mm (one fine increment) and −0.122 mm (two fine increments). Both are far below
  anything a farmer would notice. [V]
- Two different mechanisms (from the inspection report):
  - 6→144 h: the later field has a coarser rounding unit (0.244 mm), so a true total of ~0.06–0.12 mm rounds to 0.
    Consistent with rounding alone. [H]
  - 3→6 h: **same** rounding unit, so rounding alone cannot produce it. Cause unknown. [O]
- **Not decided:** what the application does with such values. Options for later decision:
  1. Report the negative value as-is (honest, but confusing for users).
  2. Set it to 0 and **count and log** every occurrence (with magnitude) for each run.
  3. Set it to 0 only if it is within a limit tied to the rounding unit (e.g. ≤ 1–2 increments), and **fail
     the run loudly** if anything larger appears.
  4. Treat any value below a "no measurable rain" display threshold as zero for display only, keeping the raw
     value in the data.
  These should be chosen after seeing the actual frequency on **real day-boundary pairs** (e.g. 18→42 h), which
  we have not yet examined.

## 5. Decisions before implementing daily totals

### Can be decided now
| # | Decision | Recommendation | Why |
|---|---|---|---|
| 1 | Daily window | **A′: 23:30→23:30 IST (18→18 UTC)**, or B | §3 |
| 2 | How to compute a day | **End reading − start reading** (two boundary steps), not summing intervals | Mathematically identical; fewer operations; unaffected by missing intermediate steps |
| 3 | Missing boundary step | **Never interpolate.** If any required boundary step is missing, do not publish the new run; keep serving the last good one with its date | Matches the safe-failure goal; avoids invented values |
| 4 | Horizon wording | Decide whether "10 days" means 240 h (A′: partial today + 9 full days) or "10 full calendar days" (A′ needs step 258) | Scope clarity; using 258 h is a small extension beyond the agreed 240 h |
| 5 | Units | Convert m → mm by × 1000 for display and API; record the source unit | Verified `units=m` and documented "depth in metres" |

### Need further investigation first
| # | Question | How to settle it |
|---|---|---|
| 6 | Accumulation from 0 at **every** required step | Download `tp` for the needed steps (~11 boundary steps ≈ 6 MB, or all 65 steps ≈ 33 MB) and check each header. **Needs your approval** (full-run download was deferred) |
| 7 | Negative-difference policy (options in §4) | Measure count and magnitude on real day-boundary pairs from #6 |
| 8 | How to show the partial first day | Depends on #1; publication was ~13:04 IST for today's run. Observe a few more runs |
| 9 | Publication delay and retention | Record `Last-Modified` for the next runs; retention docs conflict (2–3 vs ~4 days) |
| 10 | Nearest-grid-point selection and land/sea | Separate task with the pilot region choice |
| 11 | IMD 08:30 convention (only if we want to cite it) | Find an IMD source |

*Process note:* one inline command failed on PowerShell quoting (no data involved) and was re-run via Bash.
