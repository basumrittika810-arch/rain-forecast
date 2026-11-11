# Daily Rainfall Calculation: Analysis and Recommendation

- **Date:** 2026-11-11 (~17:00 UTC / 22:30 IST)
- **Status:** analysis complete; **owner decisions taken 2026-11-11 18:13 UTC (see §6)**. Nothing is implemented yet.
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

**Correction to §5 #6:** "~11 boundary steps ≈ 6 MB" covered only one day-window option. Both options
together needed 22 steps ≈ 11.4 MB (computed from `.index` lengths). This is superseded by decision 6.3 below.

## 6. Owner decisions (Mrittika Basu, 2026-11-11 18:13 UTC / 23:43 IST)

| # | Decision | Owner's reasoning | Differs from assistant recommendation? |
|---|---|---|---|
| 6.1 | **Daily window 23:30 → 23:30 IST (18 → 18 UTC)**, labelled with the IST calendar date | Keeps rainfall on the correct calendar date as closely as the data allows. 05:30 would move early-morning rain to the previous date, which could mislead a farmer. 23:30 limits the mismatch to 30 min. | No |
| 6.2 | **Horizon extended to 258 h**: one initial partial period (00→18 UTC on the run date, i.e. 05:30→23:30 IST) **plus 10 complete 24-h periods** (18→42, …, 234→258). The partial period must be shown transparently as partial, not as a full day. | More useful daily forecast; worth the small extension beyond 240 h | Yes: assistant had suggested staying within 240 h. Owner chose the extension. |
| 6.3 | **Download all available steps through 258 h** (verify the actual list; include 246, 252, 258) | Verify the complete dataset now rather than discover gaps later; enables checks on both daily totals and 3-/6-h amounts | No |
| 6.4 | **Missing boundary → publish valid periods; mark the affected periods unavailable.** A missing boundary affects both adjacent periods, which must be identified. **Never fill with zero or estimates.** If the update itself fails, keep the previous validated forecast. | One or two missing days shouldn't discard an otherwise usable forecast | Yes: assistant had suggested rejecting the whole run. Owner chose partial publication. |
| 6.5 | **Output both daily totals and interval-level (3-h/6-h) rainfall**; average rates may be computed using the **actual** interval duration, without implying when within an interval the rain fell | Daily overview plus timing information gives a better user experience | Yes: assistant had suggested daily totals only for the MVP. Owner chose both. |
| 6.6 | **Negative-value handling: left open** until the full-run evidence is reviewed | — | — |

Consequences recorded for implementation (not yet implemented):
- Required steps: 0–144 every 3 h and 150–258 every 6 h, **68 steps expected** (to be verified against the server, §7).
- Daily boundaries: steps 0 (start of partial period), 18, 42, 66, 90, 114, 138, 162, 186, 210, 234, 258.
- Interval durations change from 3 h to 6 h at step 144, so rates must use each interval's own duration.
- Negative values will appear more often at interval level than in daily totals (3→6 h example in §4).
  That makes decision 6.6 more important now that 6.5 includes interval output.

## 7. Full-run verification (run 2026-11-11 00 UTC, steps 0–258)

- **Run:** 2026-11-11 ~18:15–18:25 UTC
- **Download:** `scripts/download_run.py 20261111 00 258` → `data/raw/20261111T00Z/tp_steps_0-258.grib2`,
  35,139,859 bytes, SHA-256 `6de90b3f…cbc6f3132`, 55 s, read-only
- **Verification:** `scripts/verify_run.py`. Full output in `docs/inspection/verify_run_20261111T00Z_0-258.txt`.
  Nothing was clamped or altered.

### 7.1 Step list [V]
- Server listing re-checked at 18:15 UTC: still 85 steps (0–360). **68 steps ≤ 258 h, identical to the
  expected cadence** 0–144 by 3 (49) + 150–258 by 6 (19). The script would have stopped before downloading on any mismatch.
- Intervals: **48 × 3 h** (0→3 … 141→144), **19 × 6 h** (144→150 … 252→258). All 12 daily boundaries are present.

### 7.2 Metadata, every one of the 68 messages [V]: all PASS
`shortName=tp`, `units=m`, `stepType=accum`, **`startStep=0`**, `stepRange=0-N`, `lengthOfTimeRange=N`,
template 8 / statistical processing 1, same initialisation (2026-11-11 00:00 UTC = 05:30 IST),
validity = init + step, identical grid, no bitmap or missing values, D=0, R=0.
**This closes open item §5 #6: accumulation from initialisation is verified for every step used.**

### 7.3 Independent consistency [V]
- Steps 0, 3, 6, 144, 150, 240 are **bit-identical** to the separately downloaded sample.
- **Telescoping:** for all 11 daily periods, (end − start) equals the sum of the consecutive interval
  differences **exactly** (max difference 0) on all 1,038,240 grid points.
- Original sample file SHA-256 unchanged (`42570d62…a35308`).

### 7.4 Packing increment by step [V]
| From step | E | Increment |
|---|---|---|
| 0 | 0 (constant field) | — |
| 3 | −14 | 0.061 mm |
| 9 | −13 | 0.122 mm |
| 132 | −12 | 0.244 mm |

### 7.5 Negative differences: evidence only, nothing altered [V]
- **Intervals:** 168,793 negative values out of 67 × 1,038,240 (0.24 %); India box 2,528. They occur in only
  **5 of 67 intervals**:

  | Interval | Increments (earlier → later) | Global | India box | Most negative | Largest earlier total at a negative point |
  |---|---|---|---|---|---|
  | 3→6 | 0.061 → 0.061 (same) | 278 | 3 | −0.061 mm | 4.3 mm |
  | 6→9 | 0.061 → 0.122 (**change**) | 43,439 | 321 | −0.061 mm | 45.6 mm |
  | 9→12 | 0.122 → 0.122 (same) | 684 | 12 | −0.122 mm | 19.9 mm |
  | 129→132 | 0.122 → 0.244 (**change**) | 120,914 | 2,087 | −0.122 mm | 394.4 mm |
  | 246→252 | 0.244 → 0.244 (same) | 3,478 | 105 | −0.244 mm | 341.1 mm |

- **Every negative is exactly one increment of the finer field of the pair.** None exceeds one increment of
  either field.
- **96 % of negatives sit at the two increment changes** (6→9, 129→132). [H] Independent rounding of two
  readings to different increment sizes can produce an apparent decrease of up to one fine increment even
  when the true total rose. The observed magnitudes fit that bound.
- **Same-increment negatives** (3→6, 9→12, 246→252) cannot come from the final rounding alone [O]; cause
  unresolved (possibly an earlier processing or quantisation stage). They are also exactly one increment.
- **Negatives also occur where totals are large** (e.g. 394 mm → one increment lower), not only in near-dry
  areas. This corrects the earlier impression from the 6-step sample.
- **Daily periods:** negatives in **2 of 11** periods: 114→138 (contains the 129→132 change): 41,847 global /
  1,332 box, min −0.122 mm; and 234→258 (contains 246→252): 1,676 / 90, min −0.244 mm. **Daily aggregation
  does not remove negatives.**

### 7.6 India box daily totals (mm), for scale [V]
Partial 11 Nov: mean 2.96, max 88.5 · full days 12–21 Nov: means 2.0–4.6, maxima 60.6–483.3
(max 483.3 mm on 16 Nov; earlier inspection placed the heaviest rain over the Bay of Bengal).

### 7.7 Worked example: grid point 13.0°N 80.25°E (nearest Chennai), real values
| Date (window 23:30→23:30 IST) | Daily total |
|---|---|
| 11 Nov (**partial**, 05:30→23:30) | 0.000 mm |
| 12 Nov | 0.366 |
| 13 Nov | 2.808 |
| 14 Nov | 0.122 |
| 15 Nov | 0.000 |
| 16 Nov | 0.122 |
| 17 Nov | 0.000 |
| 18 Nov | 7.568 |
| 19 Nov | 2.930 |
| 20 Nov | 11.963 |
| 21 Nov | 1.465 |
Interval detail example (20 Nov): 10.986 mm fell in the 6-h interval 19 Nov 23:30 → 20 Nov 05:30 IST
(average 1.83 mm/h). The data cannot say *when* within those 6 h it fell.

### 7.8 Still open after verification
1. **Negative-value policy (6.6):** evidence now available (above). To decide: whether "exactly ≤ 1 increment
   of the finer field" counts as an acceptable rounding artefact, what is done with it (as-is / set to 0 and
   logged / display-only), and whether anything larger fails the run.
2. **Run-to-run variation:** the steps where the increment changes depend on each run's field maxima, so
   negatives will fall at different steps in other runs. Checks must run on every run, not be hardcoded.
   Verify on at least one more run.
3. **Cause of same-increment decreases:** unresolved. ECMWF guidance on negative precipitation not yet found.
4. **Partial first period display:** the run appeared at 13:04 IST, when 7.5 h of the 18-h partial period
   had already passed. Interval data makes it possible to show only the remaining intervals; to decide.
5. **Rate presentation:** mm/h averages over 3 h vs 6 h intervals; UI wording so a 6-h average is not
   read as a constant rate.
6. **Publication timing / retention** for other runs (one observation so far: 07:34 UTC).
7. **Pilot region, nearest-grid-point rule, land/sea.**
8. **00z only vs 00z and 12z:** a 12z run would use boundary steps 6, 30, …, 246, 270 (all exist up to 360 h).
   Not yet decided.
