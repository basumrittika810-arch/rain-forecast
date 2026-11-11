# Data Inspection Report: ECMWF IFS HRES `tp`, run 2026-11-11 00 UTC

- **Inspected:** 2026-11-11, 16:21–16:24 UTC (21:51–21:54 IST)
- **File:** `data/raw/20261111T00Z/tp_steps_0-3-6-144-150-240.grib2` (sample: 6 of the run's steps)
- **Tools:** ecCodes 2.50.0 (reference decoder), cfgrib 0.9.15.1 / xarray 2026.9.0
- **Scripts:** `scripts/inspect_eccodes.py`, `scripts/inspect_cfgrib.py`
- **Full verbatim output:** `docs/inspection/eccodes_output_20261111T00Z.txt`, `docs/inspection/cfgrib_output_20261111T00Z.txt`

Scope: **findings only.** No design decisions (daily aggregation, tolerances, region) are made here.

**Evidence labels:** **[V]** verified by direct observation in this inspection · **[D]** documented in
GRIB metadata or code tables, not yet checked against ECMWF prose documentation · **[H]** hypothesis ·
**[O]** open, needs verification

---

## 0. Integrity of the raw file

SHA-256 is a 64-hex-character fingerprint computed from every byte of the file. Changing a single
byte gives a completely different fingerprint, so equal fingerprints mean the file is byte-for-byte identical.

| When | SHA-256 | Matches manifest |
|---|---|---|
| Manifest (at download, Python `hashlib`) | `42570d62…a35308` | — |
| Before inspection, 16:21 UTC (PowerShell `Get-FileHash`) | `42570d62…a35308` | **yes** |
| After inspection, 16:24 UTC | `42570d62…a35308` | **yes** |

[V] The file was not modified. It stays read-only, its last-write time is still the download time
(16:10:38 UTC), and cfgrib wrote no `.idx` cache into the raw folder (index writing was disabled).
A mismatch would mean the bytes changed (corruption, an accidental write, or a different file).
All results derived from it would then be untrustworthy until the file is re-downloaded and re-verified.

## 1. Metadata (identical across all 6 messages unless noted) [V]

| Key | Value | Plain meaning |
|---|---|---|
| shortName / name / paramId | `tp` / Total precipitation / 228 | Rain + snow (as water) reaching the ground |
| units | **`m`** | Depth of water in **metres** (1 m = 1000 mm) |
| typeOfLevel / level | surface / 0 | At ground level |
| edition / centre | GRIB2 / ecmf | |
| stepType | **`accum`** | An accumulated (summed-over-time) quantity |
| productDefinitionTemplateNumber | **8** | "Statistically processed over a time interval" |
| typeOfStatisticalProcessing | **1** | Code 1 = **accumulation** [D: WMO GRIB2 Code Table 4.10] |
| startStep | **0** in every message | Accumulation window starts at initialisation |
| endStep / stepRange / lengthOfTimeRange | 0/`0`/0 · 3/`0-3`/3 · 6/`0-6`/6 · 144/`0-144`/144 · 150/`0-150`/150 · 240/`0-240`/240 | Window length = end step |
| stepUnits / indicatorOfUnitForTimeRange | 1 / 1 | Hours |
| dataDate / dataTime | 20261111 / 0000 | Initialisation 2026-11-11 00:00 UTC |
| validityDate / validityTime | 11-11 00:00, 11-11 03:00, 11-11 06:00, 11-17 00:00, 11-17 06:00, 11-21 00:00 | = init + endStep, all on whole UTC hours |
| gridType | regular_ll | Regular latitude/longitude grid |
| Ni × Nj | 1440 × 721 = 1,038,240 points | Global grid |
| Latitudes | 90.0 → −90.0, **descending** (north→south), spacing 0.25° | `jScansPositively = 0` |
| Longitudes | −180.0 → 179.75, ascending, spacing 0.25° | **−180..180 convention** |
| bitmapPresent / numberOfMissing | 0 / 0 | **No missing values** |
| packingType / bitsPerValue | grid_ccsds / 12 (0 at step 0) | Compressed; 4096 possible levels per field |
| referenceValue / decimalScaleFactor | 0.0 / 0 | |
| binaryScaleFactor (E) | −14 at steps 3, 6; −12 at 144, 150, 240 | Sets precision (see §4) |

Note: the key `longitudeOfFirstGridPointInDegrees` reads `180.0`, while the decoded first longitude is
`−180.0`. These are the same meridian written two ways; both libraries report it identically.

## 2. Accumulated from initialisation, or per interval?

**Conclusion [V]:** each value is the **total precipitation from initialisation (step 0) up to the
message's end step**, like a car's odometer, not the rain within the latest 3 h or 6 h interval.

The conclusion rests on four independent lines of evidence:

1. **Metadata [V/D]:** `stepType=accum`, template 8 with `typeOfStatisticalProcessing=1` (accumulation),
   `startStep=0` and `lengthOfTimeRange = endStep` in every message.
2. **Step 0 is all zeros [V]:** all 1,038,240 values are exactly 0 (`bitsPerValue=0`, a constant
   field, which is why it was only 224 bytes). Nothing has accumulated at time zero.
3. **Values grow with lead time [V]:** the area-weighted global mean (display ×1000, assuming `m` → mm):

   | Window | 0–3 h | 0–6 h | 0–144 h | 0–150 h | 0–240 h |
   |---|---|---|---|---|---|
   | Global mean (mm) | 0.364 | 0.736 | 18.65 | 19.39 | 31.48 |
   | Implied mm/day | 2.91 | 2.95 | 3.11 | 3.10 | 3.15 |

   The implied daily rate stays roughly constant at ~3 mm/day, which matches an accumulating total.
   Had the 240 h field been a single 6 h interval, its mean would be ~0.7 mm, not 31 mm.
   [H/O] ~3 mm/day is close to the commonly cited global-mean precipitation (~2.7–3 mm/day). That
   figure comes from my background knowledge and has not been checked against a cited source here.
4. **Point-by-point non-decrease [V]:** 144→150 h and 150→240 h show **0 decreases** out of 1,038,240 points.
   0→3 h also shows 0. The rare decreases elsewhere are tiny (§4).

**[O]** Only 6 of the run's steps were inspected. That the same holds for every intermediate step
(e.g. 9, 12, … 138, 156, …) is expected, but not yet observed.

## 3. India-wide inspection box (6–38°N, 68–98°E): not the pilot region

[V] Coverage: 129 latitudes (38.0→6.0) × 121 longitudes (68.0→98.0) = **15,609 grid points**. This matches
the independently computed (38−6)/0.25+1 = 129 and (98−68)/0.25+1 = 121. The box also contains sea
(Arabian Sea, Bay of Bengal) and parts of neighbouring countries. **The `tp` file has no land/sea or
country information**, so the statistics below mix land and sea.

Accumulated totals in the box, in mm (display ×1000):

| Window | min | mean | p50 | p90 | p95 | p99 | max | exactly 0 | NaN |
|---|---|---|---|---|---|---|---|---|---|
| 0–3 h | 0 | 0.49 | 0 | 1.16 | 2.75 | 8.48 | 49.6 | 65.0 % | 0 |
| 0–6 h | 0 | 0.96 | 0 | 2.38 | 5.07 | 14.9 | 56.4 | 52.3 % | 0 |
| 0–144 h | 0 | 22.0 | 1.95 | 82.8 | 105.0 | 179.9 | 605.0 | 27.9 % | 0 |
| 0–150 h | 0 | 22.8 | 1.95 | 84.7 | 107.7 | 185.0 | 644.0 | 27.7 % | 0 |
| 0–240 h | 0 | 32.9 | 3.42 | 118.7 | 148.4 | 265.6 | 700.0 | 20.2 % | 0 |

What it means:
- **Rain is very unevenly spread.** Half the box gets ≤ 3.4 mm over 10 days (median), while the wettest
  points get hundreds of mm. That fits the post-monsoon season, with dry interiors and wet patches.
- **The heaviest rain is over the sea [V].** The 0–240 h maximum (700 mm) is at 12.5°N 83.25°E, in the
  Bay of Bengal roughly 300 km east of the Tamil Nadu/Andhra coast. Early steps peak near 19°N 94°E,
  close to the Myanmar coast. [H] A concentrated multi-day maximum of this size over the Bay of Bengal
  in November could indicate an organised weather system (e.g. a depression). Not verified, and not
  something we should claim.
- [V] Points in the box with ≥ 10 mm accumulated: 92 (0–3 h), 5,066 (0–144 h), 5,966 (0–240 h).

## 4. Negative values and step-to-step decreases

**Stored fields [V]:** **zero negative values** in every message, globally and in the box. Minimum is
exactly 0 everywhere, and `referenceValue = 0.0`.

**Decreases between steps** (later value smaller than earlier). These are the values that would turn
negative if we later subtracted one step from another:

| Pair | Global decreases | India box | Magnitudes (m) | Packing increment of each field (m) |
|---|---|---|---|---|
| 0→3 | 0 | 0 | — | 1 (const) → 6.1e-5 |
| 3→6 | 278 (0.027 %) | 3 | all exactly −6.10e-5 (−0.061 mm) | 6.1e-5 → 6.1e-5 |
| 6→144 | 978 (0.094 %) | 58 | −6.10e-5 (×868), −1.22e-4 (×110) | 6.1e-5 → 2.44e-4 |
| 144→150 | 0 | 0 | — | 2.44e-4 → 2.44e-4 |
| 150→240 | 0 | 0 | — | 2.44e-4 → 2.44e-4 |

- Spatial spread: global decreases occur at all latitudes. In the India box they are mostly in dry,
  trace-rain areas (Tibet/Himalaya 28–33°N, eastern Uttar Pradesh/Bihar ~25°N, Lakshadweep sea ~11°N), where
  values go from 0.061 mm to 0. The full list is in the ecCodes output file, §5.
- **Packing precision [V]:** every decoded value is *exactly* an integer multiple of 2^E
  (checked on all 1,038,240 points × 6 messages). So values are quantised in steps of
  **0.061 mm** (E = −14, early steps) or **0.244 mm** (E = −12, later steps). E is chosen per field,
  so precision can differ between two messages being compared.
- **Explaining the decreases.** I am deliberately keeping this unresolved:
  - [H] **6→144:** the 144 h field is stored with coarser steps (0.244 mm). Rounding a true value of
    0.061–0.122 mm to the nearest 0.244 mm gives 0, so decreases up to 0.122 mm are *consistent with*
    rounding alone. Consistent, not proven.
  - [O] **3→6:** both fields use the *same* increment. Rounding to a common grid preserves order, so if the
    underlying values had not decreased, the rounded ones couldn't either. These 278 decreases therefore
    **cannot be explained by the final packing step alone**. Possible causes (all unverified): interpolation
    from the model's native grid to 0.25°, or tiny numerical artefacts in the model's accumulation.
    *(This corrects my earlier expectation in P1 that any negatives would come purely from packing.)*
  - Magnitudes are tiny (≤ 0.122 mm), but they are real and will appear in any interval calculation.

## 5. cfgrib vs ecCodes

| Aspect | ecCodes | cfgrib/xarray | Same? |
|---|---|---|---|
| Values (all 6 steps) | float64 | **float32** | **Identical: max difference 0** |
| Missing values | none | 0 NaN | yes |
| Latitude / longitude coordinates | distinctLatitudes / distinctLongitudes | `latitude`, `longitude` | identical arrays |
| Initialisation time | dataDate/dataTime | `time` = 2026-11-11T00:00 | yes |
| Valid time | validityDate/validityTime | `valid_time` | yes, all 6 |
| units, shortName, name, paramId, stepType | m, tp, Total precipitation, 228, accum | same, as `GRIB_*` attributes plus `units=m` | yes |
| missingValue key | 9999 | 3.4028e+38 | **differs** |
| stepRange, startStep, lengthOfTimeRange, statistical processing, packing keys | available | **not exposed** | **cfgrib drops them** |
| Step representation | stepRange `0-144` | `step = 6 days` (a single timedelta) | **different view** |
| Time zone | none (GRIB times are UTC by definition [D]) | naive datetime64, no tz label | consistent, but implicit |

Why the differences exist, and why they matter:
- **float32 vs float64 but identical values:** every value is an integer (≤ 4095) times a power of two, and float32
  stores such numbers exactly. No precision was lost in this file. [O] That would not hold automatically if a future
  file used decimal scaling (D ≠ 0).
- **missingValue:** cfgrib uses its own placeholder (the largest float32) and converts real missing
  points to NaN. Irrelevant here (no bitmap, no missing points), but it means missing data appears as NaN in xarray.
- **Step representation (important):** cfgrib shows `step = 144 h` and keeps `stepType=accum`, but drops
  `stepRange=0-144`. Reading only the xarray view, it is easy to mistake the value for the rain *at* hour
  144 rather than the total *from 0 to* 144. ecCodes makes the window explicit.
- **Time zone:** both give UTC times without labelling them as UTC. Any IST conversion must be added by us.

## 6. Summary: facts vs open questions

**Verified in this file [V]:** units are metres · accumulation from initialisation up to each step ·
step 0 is all zeros · init 2026-11-11 00 UTC; valid times = init + step, on whole UTC hours · global
0.25° regular grid, 1440×721, latitudes north→south, longitudes −180..179.75 · no missing values ·
no negative stored values · rare step-to-step decreases of ≤ 0.122 mm · quantisation of 0.061/0.244 mm ·
cfgrib values and coordinates identical to ecCodes.

**Still to verify independently [O]:**
1. ECMWF's own documentation for `tp` (paramId 228) and the open-data step list (3-hourly to 144 h,
   6-hourly to 240 h). Only steps 0, 3, 6, 144, 150, 240 have been observed.
2. Accumulation-from-zero for **all** intermediate steps, and for the 12 UTC run.
3. The cause of same-precision decreases (3→6 h).
4. Whether the packing precision (E) differs between runs and steps beyond those seen.
5. A cited source for the global-mean precipitation comparison.
6. Land/sea separation for the India box (the heaviest values here are over the sea).

*Process note:* the first cfgrib script run failed on a display bug in my own script (printing a
0-dimensional time coordinate). It was fixed and re-run; the data was not involved.
