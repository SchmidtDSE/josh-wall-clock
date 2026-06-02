import math
import numpy as np
import xarray as xr
import pandas as pd
from mesa import Agent, Model
from mesa.space import MultiGrid


def D(value):
    """Coerce a scalar (numpy/Python float or int) into a Python float.

    Both implementations are compared at matched native precision: this
    reference carries every model quantity as an IEEE 754 64-bit float, and
    Josh is run with --use-float-64 so it likewise backs values with Java
    doubles rather than BigDecimal. Using the same native floating-point type
    on both sides avoids the behavioral differences between Python's Decimal
    and Java's BigDecimal and keeps the wall-clock comparison clean.
    """
    return float(value)


# Simulation constants, carried as floats so all per-tree growth math stays in
# IEEE 754 64-bit floating point (the Java-double analogue under --use-float-64).
T_MIN = 270.0
T_MAX = 330.0
P_LOW = 300.0
P_HIGH = 500.0
SIGMOID_K = 12.0
DELTA_H_MAX = 1.0
STOCHASTIC_STD = 0.05  # passed to numpy's float64 RNG; already a float
TREES_PER_PATCH = 10

# Float literals reused in the hot path.
_ZERO = 0.0
_ONE = 1.0
_FOUR = 4.0
_HALF = 0.5

LAT_LOW = 35.80
LAT_HIGH = 36.73
LON_LOW = -119.52
LON_HIGH = -117.98
PATCH_SIZE_KM = 1.0
SECONDS_PER_YEAR = 31_536_000

START_YEAR = 2024
NUM_STEPS = 31

# Parsed climate arrays, cached per (temp_path, precip_path) so the NetCDF is
# read and unit-converted once per process and then shared (read-only) across
# every replicate's model, instead of being re-opened on each model __init__.
# This mirrors Josh, which parses the climate once into .jshd and reuses it.
_CLIMATE_CACHE = {}


def _temperature_impact(temp_k):
    t = min(max(temp_k, T_MIN), T_MAX)
    x = (t - T_MIN) / (T_MAX - T_MIN)
    return _FOUR * x * (_ONE - x)


def _precipitation_impact(precip_mm):
    x = (precip_mm - P_LOW) / (P_HIGH - P_LOW)
    return _ONE / (_ONE + math.exp(-SIGMOID_K * (x - _HALF)))


class ForeverTree(Agent):
    def __init__(self, model):
        super().__init__(model)
        self.age = _ZERO
        self.height = _ZERO

    def step(self):
        cell = self.pos
        temp_k = D(self.model.get_temperature(cell, self.model.current_step))
        precip_mm = D(self.model.get_precipitation(cell, self.model.current_step))

        temp_pct = _temperature_impact(temp_k)
        precip_pct = _precipitation_impact(precip_mm)
        stochastic = D(self.model.rng.normal(1.0, STOCHASTIC_STD))

        self.height += DELTA_H_MAX * temp_pct * precip_pct * stochastic
        self.age += _ONE


class ForeverTreeModel(Model):
    def __init__(self, temp_path, precip_path, seed=None):
        super().__init__(seed=seed)

        self._load_climate(temp_path, precip_path)

        # Build grid from bounding box using Haversine-approximate km → degrees
        lat_range = LAT_HIGH - LAT_LOW
        lon_range = LON_HIGH - LON_LOW
        lat_mid = (LAT_LOW + LAT_HIGH) / 2.0
        km_per_deg_lat = 111.32
        km_per_deg_lon = 111.32 * math.cos(math.radians(lat_mid))

        self.n_rows = max(1, round(lat_range * km_per_deg_lat / PATCH_SIZE_KM))
        self.n_cols = max(1, round(lon_range * km_per_deg_lon / PATCH_SIZE_KM))

        self.grid = MultiGrid(self.n_cols, self.n_rows, torus=False)
        self.current_step = 0
        self.records = []

        for row in range(self.n_rows):
            for col in range(self.n_cols):
                for _ in range(TREES_PER_PATCH):
                    tree = ForeverTree(self)
                    self.grid.place_agent(tree, (col, row))

    def _load_climate(self, temp_path, precip_path):
        key = (temp_path, precip_path)
        cached = _CLIMATE_CACHE.get(key)
        if cached is None:
            ds_t = xr.open_dataset(temp_path)
            ds_p = xr.open_dataset(precip_path)
            # Detect coordinate names
            lat_name = next(v for v in ds_t.coords if "lat" in v.lower())
            lon_name = next(v for v in ds_t.coords if "lon" in v.lower())
            time_name = next(v for v in ds_t.coords if "year" in v.lower() or "time" in v.lower())
            cached = (
                ds_t[lat_name].values,
                ds_t[lon_name].values,
                ds_t["tasmax"].values,                    # (time, lat, lon)
                ds_p["pr"].values * SECONDS_PER_YEAR,     # kgm2s → mm/yr
                int(ds_t[time_name].values[0]) - START_YEAR,
            )
            ds_t.close()
            ds_p.close()
            _CLIMATE_CACHE[key] = cached
        (self._lats, self._lons, self._temp_data,
         self._precip_data, self._start_year_idx) = cached

    def _nearest_climate(self, col, row, step):
        lat = LAT_HIGH - (row + 0.5) * (LAT_HIGH - LAT_LOW) / self.n_rows
        lon = LON_LOW + (col + 0.5) * (LON_HIGH - LON_LOW) / self.n_cols
        lat_idx = int(np.argmin(np.abs(self._lats - lat)))
        lon_idx = int(np.argmin(np.abs(self._lons - lon)))
        t_idx = step - self._start_year_idx
        return lat, lon, lat_idx, lon_idx, t_idx

    def get_temperature(self, cell, step):
        col, row = cell
        _, _, li, oi, ti = self._nearest_climate(col, row, step)
        return float(self._temp_data[ti, li, oi])

    def get_precipitation(self, cell, step):
        col, row = cell
        _, _, li, oi, ti = self._nearest_climate(col, row, step)
        return float(self._precip_data[ti, li, oi])

    def step(self):
        for row in range(self.n_rows):
            for col in range(self.n_cols):
                trees = self.grid.get_cell_list_contents([(col, row)])
                for tree in trees:
                    tree.step()

        self._record_step()
        self.current_step += 1

    def _record_step(self):
        year = START_YEAR + self.current_step
        for row in range(self.n_rows):
            for col in range(self.n_cols):
                trees = self.grid.get_cell_list_contents([(col, row)])
                if not trees:
                    continue
                lat, lon, li, oi, ti = self._nearest_climate(col, row, self.current_step)
                temp = float(self._temp_data[ti, li, oi])
                precip = float(self._precip_data[ti, li, oi])
                n = len(trees)
                mean_age = sum((t.age for t in trees), _ZERO) / n
                mean_height = sum((t.height for t in trees), _ZERO) / n
                self.records.append({
                    "cell_id": f"{col}_{row}",
                    "year": year,
                    "nTrees": len(trees),
                    "meanAge": float(mean_age),
                    "meanHeight": float(mean_height),
                    "temperature": temp,
                    "precipitation": precip,
                })

    def run(self):
        for _ in range(NUM_STEPS):
            self.step()
        return pd.DataFrame(self.records)


if __name__ == "__main__":
    import sys, os

    here = os.path.dirname(__file__)
    temp_path = os.path.join(here, "../data/maxtemp_synthetic.nc")
    precip_path = os.path.join(here, "../data/precip_synthetic.nc")
    out_dir = os.path.join(here, "output")

    replicates = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    os.makedirs(out_dir, exist_ok=True)

    # Produce every replicate inside this one long-lived process: the Python
    # interpreter + imports are paid for exactly once, not per replicate. This
    # parallels how the Josh runtime emits all replicates from a single JVM
    # invocation, making the wall-clock comparison cleaner. Note Python's float
    # arithmetic runs at constant native speed across replicates, so unlike the
    # JVM's JIT-compiled paths it won't speed up as the run warms.
    total_rows = 0
    for seed in range(replicates):
        model = ForeverTreeModel(temp_path, precip_path, seed=seed)
        df = model.run()
        out_path = os.path.join(out_dir, f"results_{seed}.csv")
        df.to_csv(out_path, index=False)
        total_rows += len(df)

    print(f"Wrote {replicates} replicate(s), {total_rows} rows total to {out_dir}")
