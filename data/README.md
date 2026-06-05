# Synthetic climate inputs

Gridded, synthetic climate driving both ForeverTree implementations. Using
synthetic (rather than observed) data keeps the repository self-contained and
the benchmark deterministic; both runtimes read the identical files so the
comparison reflects runtime and threading behavior, not differing inputs.

The grid covers a fixed bounding box (lat 35.80–36.73, lon -119.52 to -117.98,
~31 × 50 cells at 1 km) over a 101-year span (years 2024–2124), matching the
101 annual timesteps the models run.

## Files

- `maxtemp_synthetic.nc` — maximum temperature. Variable `tasmax`, in Kelvin
  (`K`).
- `precip_synthetic.nc` — precipitation. Variable `pr`, in `kg m⁻² s⁻¹`
  (`kgm2s`), converted to mm/yr on read (× 31,536,000 seconds per year).

Each file is NetCDF with latitude, longitude, and time/year coordinates (the
references detect coordinate names heuristically).

## How they are consumed

- **Mesa** ([`../reference-mesa/`](../reference-mesa)): `forevertree.py` opens
  both datasets once per process via xarray, converts precipitation to mm/yr,
  and caches the arrays across replicates.
- **Josh** ([`../reference/`](../reference)): `run.sh` preprocesses each file
  into a cached `.jshd` (`tasmax` as `K`, `pr` as `kgm2s`) before running.
