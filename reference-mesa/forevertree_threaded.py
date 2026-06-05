"""Free-threaded (no-GIL) variant of the Mesa ForeverTree model.

This reuses the constants, climate loading, and growth math from
L{forevertree} unchanged, and overrides only the per-step loop so that the
independent patches within a step run across a thread pool. On a standard
(GIL-enabled) CPython this would not parallelize, because the per-tree float
arithmetic holds the GIL; it is meant to be run on a free-threaded build
(C{python3.14t}) with C{PYTHON_GIL=0} so the GIL stays disabled even after
C{cftime} is imported.

Thread-safety note: C{numpy}'s C{Generator} is not safe to call from multiple
threads at once, so each worker thread draws its stochastic term from its own
C{Generator} (kept in C{threading.local}), seeded deterministically from the
replicate seed and the worker's chunk index. Results therefore differ from the
serial run draw-for-draw, but come from the same distribution -- fine for a
wall-clock benchmark of the same arithmetic workload.

Run directly to produce one CSV per replicate::

    python forevertree_threaded.py [replicates] [threads]
"""

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import forevertree as ft


def _step_patches(model, patches, rng):
  """Advance every tree in a chunk of patches by one step.

  Mirrors L{forevertree.ForeverTree.step} exactly -- the temperature and
  precipitation impact math is computed I{per tree}, not hoisted to once per
  patch, so this thread pool performs the identical per-tree workload as the
  serial model and as Josh (whose impacts are organism-level). Only C{rng} is
  worker-local so concurrent workers never touch a shared Generator. The
  threading speedup therefore reflects parallelism alone, not a reduced amount
  of work.

  @param model: The model whose grid and climate accessors are read.
  @type model: L{ThreadedForeverTreeModel}
  @param patches: The C{(col, row)} cells this worker owns.
  @type patches: list of tuple of int
  @param rng: The worker-local random generator for stochastic draws.
  @type rng: numpy.random.Generator
  """
  get_temp = model.get_temperature
  get_precip = model.get_precipitation
  contents = model.grid.get_cell_list_contents
  step = model.current_step
  for col, row in patches:
    cell = (col, row)
    for tree in contents([cell]):
      temp_k = ft.D(get_temp(cell, step))
      precip_mm = ft.D(get_precip(cell, step))
      temp_pct = ft._temperature_impact(temp_k)
      precip_pct = ft._precipitation_impact(precip_mm)
      stochastic = ft.D(rng.normal(1.0, ft.STOCHASTIC_STD))
      tree.height += ft.DELTA_H_MAX * temp_pct * precip_pct * stochastic
      tree.age += ft._ONE


class ThreadedForeverTreeModel(ft.ForeverTreeModel):
  """ForeverTree model whose per-step patch loop runs across a thread pool.

  The grid's patches are statically partitioned into one chunk per worker, and
  each worker advances its chunk with a worker-local RNG, so the only override
  relative to L{forevertree.ForeverTreeModel} is L{step}.

  @ivar n_threads: Number of worker threads (and patch chunks).
  @type n_threads: int
  """

  def __init__(self, temp_path, precip_path, seed=None, n_threads=None):
    """Partition patches into per-worker chunks and prepare the thread pool.

    Each chunk gets its own C{numpy} C{Generator}, kept in thread-local
    storage and seeded deterministically from the replicate seed plus the
    chunk index so a run is reproducible for a given seed and thread count.

    @param temp_path: Path to the maximum-temperature NetCDF file.
    @type temp_path: str
    @param precip_path: Path to the precipitation NetCDF file.
    @type precip_path: str
    @param seed: Seed for the model RNG; C{None} for nondeterministic.
    @type seed: int or None
    @param n_threads: Worker thread count; defaults to the CPU count.
    @type n_threads: int or None
    """
    super().__init__(temp_path, precip_path, seed=seed)
    self.n_threads = n_threads or (os.cpu_count() or 1)
    self._seed = 0 if seed is None else seed

    all_patches = [
        (col, row)
        for row in range(self.n_rows)
        for col in range(self.n_cols)
    ]
    self._chunks = [all_patches[i::self.n_threads] for i in range(self.n_threads)]

    self._tls = threading.local()
    self._chunk_seeds = [
        np.random.SeedSequence([self._seed, i]) for i in range(self.n_threads)
    ]
    self._executor = ThreadPoolExecutor(max_workers=self.n_threads)

  def _worker(self, chunk_idx):
    """Advance one patch chunk, lazily creating its thread-local RNG.

    On a thread's first call the chunk's C{Generator} is built from its
    seed sequence and stashed in thread-local storage; later calls reuse it.

    @param chunk_idx: Index of the patch chunk (and its seed) to advance.
    @type chunk_idx: int
    """
    rng = getattr(self._tls, "rng", None)
    if rng is None:
      rng = np.random.default_rng(self._chunk_seeds[chunk_idx])
      self._tls.rng = rng
    _step_patches(self, self._chunks[chunk_idx], rng)

  def step(self):
    """Advance all patch chunks in parallel, then record and tick forward.

    Dispatches one L{_worker} call per chunk across the thread pool, waits
    for all of them, appends the per-cell summaries for the step, and
    increments the current step.
    """
    list(self._executor.map(self._worker, range(self.n_threads)))
    self._record_step()
    self.current_step += 1

  def run(self):
    """Run the model to completion and shut down the thread pool.

    @return: One row per populated cell per step.
    @rtype: pandas.DataFrame
    """
    try:
      return super().run()
    finally:
      self._executor.shutdown(wait=True)


def main():
  """Run every replicate across a thread pool and write a CSV per replicate.

  The replicate count and thread count are taken from C{argv[1]} and
  C{argv[2]} (defaulting to 1 replicate and the CPU count, respectively). A
  warning is printed to stderr if the GIL is still enabled, since the worker
  threads will not then run in parallel.
  """
  here = os.path.dirname(__file__)
  temp_path = os.path.join(here, "../data/maxtemp_synthetic.nc")
  precip_path = os.path.join(here, "../data/precip_synthetic.nc")
  out_dir = os.path.join(here, "output")

  replicates = int(sys.argv[1]) if len(sys.argv) > 1 else 1
  n_threads = int(sys.argv[2]) if len(sys.argv) > 2 else (os.cpu_count() or 1)
  os.makedirs(out_dir, exist_ok=True)

  if sys._is_gil_enabled():
    print(
        "WARNING: the GIL is ENABLED -- threads will not run in parallel. "
        "Run on a free-threaded build with PYTHON_GIL=0.",
        file=sys.stderr,
    )

  total_rows = 0
  for seed in range(replicates):
    model = ThreadedForeverTreeModel(
        temp_path, precip_path, seed=seed, n_threads=n_threads
    )
    df = model.run()
    out_path = os.path.join(out_dir, f"results_threaded_{seed}.csv")
    df.to_csv(out_path, index=False)
    total_rows += len(df)

  print(
      f"Wrote {replicates} replicate(s) with {n_threads} threads, "
      f"{total_rows} rows total to {out_dir}"
  )


if __name__ == "__main__":
  main()
