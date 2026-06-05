"""Mesa reference implementation of the ForeverTree growth model.

This module is the serial Python/Mesa baseline that the Josh runtime is
benchmarked against in the wall-clock comparison. It grows a grid of trees over
a sequence of yearly timesteps, where each tree's annual height increment is
driven by gridded temperature and precipitation read from synthetic NetCDF
climate files.

Every model quantity is carried as an IEEE 754 64-bit float (see L{D}). Josh is
run with C{--use-float-64} so it likewise backs values with Java doubles rather
than BigDecimal; matching the native floating-point type on both sides avoids
the behavioral differences between Python's C{Decimal} and Java's C{BigDecimal}
and keeps the wall-clock comparison clean.

Run directly to produce one CSV per replicate::

    python forevertree.py [replicates]

@var T_MIN: Lower bound (K) of the temperature growth window.
@var T_MAX: Upper bound (K) of the temperature growth window.
@var P_LOW: Precipitation (mm/yr) mapped to the low end of the sigmoid.
@var P_HIGH: Precipitation (mm/yr) mapped to the high end of the sigmoid.
@var SIGMOID_K: Steepness of the precipitation-impact sigmoid.
@var DELTA_H_MAX: Maximum annual height increment under ideal conditions.
@var STOCHASTIC_STD: Std dev of the per-step multiplicative growth noise.
@var TREES_PER_PATCH: Number of trees placed in each grid cell.
@var START_YEAR: Calendar year of the first timestep.
@var NUM_STEPS: Number of yearly timesteps each replicate runs.
"""

import math
import os
import sys

import numpy as np
import xarray as xr
import pandas as pd
import mesa
import mesa.space


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
NUM_STEPS = 101

# Parsed climate arrays, cached per (temp_path, precip_path) so the NetCDF is
# read and unit-converted once per process and then shared (read-only) across
# every replicate's model, instead of being re-opened on each model __init__.
# This mirrors Josh, which parses the climate once into .jshd and reuses it.
_CLIMATE_CACHE = {}


def D(value):
  """Coerce a scalar (numpy/Python float or int) into a Python float.

  Both implementations are compared at matched native precision: this
  reference carries every model quantity as an IEEE 754 64-bit float, and Josh
  is run with C{--use-float-64} so it likewise backs values with Java doubles.

  @param value: The scalar to coerce.
  @type value: float or int or numpy.number
  @return: The value as a native Python float.
  @rtype: float
  """
  return float(value)


def _temperature_impact(temp_k):
  """Map a temperature to a growth multiplier via an inverted parabola.

  The temperature is clamped to [L{T_MIN}, L{T_MAX}], normalized to [0, 1],
  and passed through C{4x(1 - x)} so the multiplier peaks at 1.0 mid-range and
  falls to 0.0 at either bound.

  @param temp_k: Temperature in Kelvin.
  @type temp_k: float
  @return: Growth multiplier in [0, 1].
  @rtype: float
  """
  t = min(max(temp_k, T_MIN), T_MAX)
  x = (t - T_MIN) / (T_MAX - T_MIN)
  return _FOUR * x * (_ONE - x)


def _precipitation_impact(precip_mm):
  """Map an annual precipitation to a growth multiplier via a logistic curve.

  Precipitation is normalized between L{P_LOW} and L{P_HIGH} and passed
  through a sigmoid of steepness L{SIGMOID_K} centered at the midpoint.

  @param precip_mm: Annual precipitation in mm.
  @type precip_mm: float
  @return: Growth multiplier in (0, 1).
  @rtype: float
  """
  x = (precip_mm - P_LOW) / (P_HIGH - P_LOW)
  return _ONE / (_ONE + math.exp(-SIGMOID_K * (x - _HALF)))


class ForeverTree(mesa.Agent):
  """A single tree agent that accumulates height once per yearly step.

  @ivar age: Number of steps the tree has been advanced.
  @type age: float
  @ivar height: Accumulated height in model units.
  @type height: float
  """

  def __init__(self, model):
    """Initialize a tree at zero age and zero height.

    @param model: The model the tree belongs to.
    @type model: L{ForeverTreeModel}
    """
    super().__init__(model)
    self.age = _ZERO
    self.height = _ZERO

  def step(self):
    """Advance the tree by one year.

    Reads the temperature and precipitation for the tree's cell at the
    model's current step, converts each to a growth multiplier, applies a
    per-tree multiplicative stochastic term, and adds the resulting
    increment to L{height} while incrementing L{age}.
    """
    cell = self.pos
    temp_k = D(self.model.get_temperature(cell, self.model.current_step))
    precip_mm = D(self.model.get_precipitation(cell, self.model.current_step))

    temp_pct = _temperature_impact(temp_k)
    precip_pct = _precipitation_impact(precip_mm)
    stochastic = D(self.model.rng.normal(1.0, STOCHASTIC_STD))

    self.height += DELTA_H_MAX * temp_pct * precip_pct * stochastic
    self.age += _ONE


class ForeverTreeModel(mesa.Model):
  """Grid of tree agents advanced over yearly climate-driven steps.

  The grid is sized from a fixed latitude/longitude bounding box, and each
  cell is seeded with L{TREES_PER_PATCH} trees. Per-step summaries are
  accumulated in L{records} and returned as a DataFrame by L{run}.

  @ivar n_rows: Number of grid rows derived from the latitude span.
  @type n_rows: int
  @ivar n_cols: Number of grid columns derived from the longitude span.
  @type n_cols: int
  @ivar grid: The Mesa grid holding the tree agents.
  @type grid: mesa.space.MultiGrid
  @ivar current_step: Index of the next step to run (0-based).
  @type current_step: int
  @ivar records: Per-cell, per-year summary rows accumulated during the run.
  @type records: list of dict
  """

  def __init__(self, temp_path, precip_path, seed=None):
    """Build the grid from the bounding box and populate it with trees.

    The grid shape is derived from the bounding box using a
    Haversine-approximate km-to-degrees conversion (longitude degrees are
    scaled by the cosine of the mid-latitude).

    @param temp_path: Path to the maximum-temperature NetCDF file.
    @type temp_path: str
    @param precip_path: Path to the precipitation NetCDF file.
    @type precip_path: str
    @param seed: Seed for the model RNG; C{None} for nondeterministic.
    @type seed: int or None
    """
    super().__init__(seed=seed)

    self._load_climate(temp_path, precip_path)

    lat_range = LAT_HIGH - LAT_LOW
    lon_range = LON_HIGH - LON_LOW
    lat_mid = (LAT_LOW + LAT_HIGH) / 2.0
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * math.cos(math.radians(lat_mid))

    self.n_rows = max(1, round(lat_range * km_per_deg_lat / PATCH_SIZE_KM))
    self.n_cols = max(1, round(lon_range * km_per_deg_lon / PATCH_SIZE_KM))

    self.grid = mesa.space.MultiGrid(self.n_cols, self.n_rows, torus=False)
    self.current_step = 0
    self.records = []

    for row in range(self.n_rows):
      for col in range(self.n_cols):
        for _ in range(TREES_PER_PATCH):
          tree = ForeverTree(self)
          self.grid.place_agent(tree, (col, row))

  def _load_climate(self, temp_path, precip_path):
    """Load and cache the gridded climate arrays for this process.

    On a cache miss the two NetCDF datasets are opened, their coordinate
    names are detected heuristically (the first coord containing "lat",
    "lon", and "year"/"time" respectively), the precipitation is converted
    from kg/m^2/s to mm/yr by multiplying by L{SECONDS_PER_YEAR}, and the
    resulting arrays are stored in L{_CLIMATE_CACHE} keyed by the path pair.
    Subsequent models for the same paths reuse the cached (read-only)
    arrays.

    @param temp_path: Path to the maximum-temperature NetCDF file.
    @type temp_path: str
    @param precip_path: Path to the precipitation NetCDF file.
    @type precip_path: str
    """
    key = (temp_path, precip_path)
    cached = _CLIMATE_CACHE.get(key)
    if cached is None:
      ds_t = xr.open_dataset(temp_path)
      ds_p = xr.open_dataset(precip_path)
      lat_name = next(v for v in ds_t.coords if "lat" in v.lower())
      lon_name = next(v for v in ds_t.coords if "lon" in v.lower())
      time_name = next(v for v in ds_t.coords if "year" in v.lower() or "time" in v.lower())
      cached = (
          ds_t[lat_name].values,
          ds_t[lon_name].values,
          ds_t["tasmax"].values,
          ds_p["pr"].values * SECONDS_PER_YEAR,
          int(ds_t[time_name].values[0]) - START_YEAR,
      )
      ds_t.close()
      ds_p.close()
      _CLIMATE_CACHE[key] = cached
    (self._lats, self._lons, self._temp_data,
     self._precip_data, self._start_year_idx) = cached

  def _nearest_climate(self, col, row, step):
    """Resolve a grid cell and step to the nearest climate sample indices.

    The cell center is converted back to a latitude/longitude and matched
    to the nearest entry in the cached coordinate arrays.

    @param col: Grid column index.
    @type col: int
    @param row: Grid row index.
    @type row: int
    @param step: Timestep index.
    @type step: int
    @return: Tuple of C{(lat, lon, lat_idx, lon_idx, time_idx)}.
    @rtype: tuple
    """
    lat = LAT_HIGH - (row + 0.5) * (LAT_HIGH - LAT_LOW) / self.n_rows
    lon = LON_LOW + (col + 0.5) * (LON_HIGH - LON_LOW) / self.n_cols
    lat_idx = int(np.argmin(np.abs(self._lats - lat)))
    lon_idx = int(np.argmin(np.abs(self._lons - lon)))
    t_idx = step - self._start_year_idx
    return lat, lon, lat_idx, lon_idx, t_idx

  def get_temperature(self, cell, step):
    """Return the temperature for a cell at a given step.

    @param cell: The C{(col, row)} grid cell.
    @type cell: tuple of int
    @param step: Timestep index.
    @type step: int
    @return: Temperature in Kelvin.
    @rtype: float
    """
    col, row = cell
    _, _, li, oi, ti = self._nearest_climate(col, row, step)
    return float(self._temp_data[ti, li, oi])

  def get_precipitation(self, cell, step):
    """Return the annual precipitation for a cell at a given step.

    @param cell: The C{(col, row)} grid cell.
    @type cell: tuple of int
    @param step: Timestep index.
    @type step: int
    @return: Annual precipitation in mm.
    @rtype: float
    """
    col, row = cell
    _, _, li, oi, ti = self._nearest_climate(col, row, step)
    return float(self._precip_data[ti, li, oi])

  def step(self):
    """Advance every tree by one step, record summaries, and tick forward.

    Iterates over all cells in row-major order, steps each tree, appends the
    per-cell summary rows for the step via L{_record_step}, and increments
    L{current_step}.
    """
    for row in range(self.n_rows):
      for col in range(self.n_cols):
        trees = self.grid.get_cell_list_contents([(col, row)])
        for tree in trees:
          tree.step()

    self._record_step()
    self.current_step += 1

  def _record_step(self):
    """Append one summary row per populated cell for the current step.

    Each row carries the cell id, calendar year, tree count, mean age and
    height, and the temperature and precipitation that drove the cell.
    """
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
    """Run the model for L{NUM_STEPS} steps and return the results.

    @return: One row per populated cell per step.
    @rtype: pandas.DataFrame
    """
    for _ in range(NUM_STEPS):
      self.step()
    return pd.DataFrame(self.records)


def main():
  """Run every replicate in one process and write a CSV per replicate.

  The replicate count is taken from C{argv[1]} (default 1). Producing every
  replicate inside this one long-lived process means the Python interpreter
  and imports are paid for exactly once, not per replicate. This parallels how
  the Josh runtime emits all replicates from a single JVM invocation, making
  the wall-clock comparison cleaner. Note Python's float arithmetic runs at
  constant native speed across replicates, so unlike the JVM's JIT-compiled
  paths it won't speed up as the run warms.
  """
  here = os.path.dirname(__file__)
  temp_path = os.path.join(here, "../data/maxtemp_synthetic.nc")
  precip_path = os.path.join(here, "../data/precip_synthetic.nc")
  out_dir = os.path.join(here, "output")

  replicates = int(sys.argv[1]) if len(sys.argv) > 1 else 1
  os.makedirs(out_dir, exist_ok=True)

  total_rows = 0
  for seed in range(replicates):
    model = ForeverTreeModel(temp_path, precip_path, seed=seed)
    df = model.run()
    out_path = os.path.join(out_dir, f"results_{seed}.csv")
    df.to_csv(out_path, index=False)
    total_rows += len(df)

  print(f"Wrote {replicates} replicate(s), {total_rows} rows total to {out_dir}")


if __name__ == "__main__":
  main()
