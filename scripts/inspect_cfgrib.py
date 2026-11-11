"""Open the tp GRIB file with cfgrib/xarray and compare metadata + values against raw ecCodes.

Usage:
    python scripts/inspect_cfgrib.py <grib_file> <output_txt>

cfgrib normally writes a '<file>.<hash>.idx' cache next to the GRIB file. We disable that
(indexpath="") so nothing is written into the raw-data directory.
"""

import sys
from pathlib import Path

import cfgrib
import eccodes
import numpy as np
import pandas as pd
import xarray as xr

_out = None


def log(*args):
    text = " ".join(str(a) for a in args)
    print(text)
    _out.write(text + "\n")


def eccodes_messages(path: Path):
    out = []
    with open(path, "rb") as f:
        while True:
            gid = eccodes.codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                out.append({
                    "endStep": eccodes.codes_get(gid, "endStep"),
                    "dataDate": eccodes.codes_get(gid, "dataDate"),
                    "dataTime": eccodes.codes_get(gid, "dataTime"),
                    "validityDate": eccodes.codes_get(gid, "validityDate"),
                    "validityTime": eccodes.codes_get(gid, "validityTime"),
                    "Ni": eccodes.codes_get(gid, "Ni"),
                    "Nj": eccodes.codes_get(gid, "Nj"),
                    "values": eccodes.codes_get_values(gid),
                    "lats": eccodes.codes_get_array(gid, "distinctLatitudes"),
                    "lons": eccodes.codes_get_array(gid, "distinctLongitudes"),
                })
            finally:
                eccodes.codes_release(gid)
    return out


def main(argv):
    global _out
    if len(argv) != 3:
        print(__doc__)
        return 2
    path, out_path = Path(argv[1]), Path(argv[2])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _out = open(out_path, "w", encoding="utf-8")

    before = sorted(p.name for p in path.parent.iterdir())
    log(f"# cfgrib inspection of {path.name}")
    log(f"cfgrib {cfgrib.__version__}, xarray {xr.__version__}, ecCodes {eccodes.codes_get_api_version()}")

    ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""},
                         decode_timedelta=True)

    log("\n## 1. Dataset as cfgrib presents it")
    log(repr(ds))
    log("\n## 2. Attributes of variable 'tp' (cfgrib-derived)")
    for k, v in ds["tp"].attrs.items():
        log(f"  {k:<40} = {v}")
    log("\n## 3. Global attributes")
    for k, v in ds.attrs.items():
        log(f"  {k:<40} = {v}")

    log("\n## 4. Coordinates")
    for name, c in ds.coords.items():
        vals = np.atleast_1d(c.values)  # scalar coords (time, surface) are 0-d
        if vals.size <= 10:
            shown = list(vals)
        else:
            shown = f"[{vals[0]} ... {vals[-1]}] (n={vals.size})"
        log(f"  {name:<12} dims={c.dims} dtype={c.dtype} attrs.units={c.attrs.get('units')}  values={shown}")
    log(f"\n  tp dims={ds['tp'].dims} shape={ds['tp'].shape} dtype={ds['tp'].dtype}")

    # ---- Compare against ecCodes ----
    log("\n## 5. Comparison with raw ecCodes, message by message")
    ref = eccodes_messages(path)
    lat_eq = np.array_equal(ds["latitude"].values, ref[0]["lats"])
    lon_eq = np.array_equal(ds["longitude"].values, ref[0]["lons"])
    log(f"  latitude coordinate identical to ecCodes distinctLatitudes : {lat_eq}")
    log(f"  longitude coordinate identical to ecCodes distinctLongitudes: {lon_eq}")

    init_cf = pd.Timestamp(ds["time"].values)
    for m in ref:
        step_h = int(m["endStep"])
        init_ec = pd.Timestamp(f"{m['dataDate']}") + pd.Timedelta(hours=m["dataTime"] // 100,
                                                                   minutes=m["dataTime"] % 100)
        valid_ec = pd.Timestamp(f"{m['validityDate']}") + pd.Timedelta(
            hours=m["validityTime"] // 100, minutes=m["validityTime"] % 100)
        da = ds["tp"].sel(step=pd.Timedelta(hours=step_h))
        valid_cf = pd.Timestamp(da["valid_time"].values)
        cf_vals = da.values  # (lat, lon)
        ec_vals = m["values"].reshape(m["Nj"], m["Ni"])
        diff = np.abs(cf_vals.astype(np.float64) - ec_vals)
        exact64 = np.array_equal(cf_vals.astype(np.float64), ec_vals)
        exact32 = np.array_equal(cf_vals, ec_vals.astype(np.float32))
        log(f"\n  step {step_h} h:")
        log(f"    init  : cfgrib={init_cf}  ecCodes={init_ec}  equal={init_cf == init_ec}")
        log(f"    valid : cfgrib={valid_cf}  ecCodes={valid_ec}  equal={valid_cf == valid_ec}")
        log(f"    values: cfgrib dtype={cf_vals.dtype}, ecCodes dtype={ec_vals.dtype}")
        log(f"            NaN in cfgrib={int(np.isnan(cf_vals).sum())}")
        log(f"            identical after cfgrib->float64: {exact64};  identical after ecCodes->float32: {exact32}")
        log(f"            max |cfgrib - ecCodes| = {diff.max():.3g}")

    ds.close()
    after = sorted(p.name for p in path.parent.iterdir())
    log("\n## 6. Raw-data directory unchanged by cfgrib (no .idx written)?")
    log(f"  before: {before}")
    log(f"  after : {after}")
    log(f"  unchanged: {before == after}")
    _out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
