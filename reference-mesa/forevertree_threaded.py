"""Free-threaded (no-GIL) variant of the Mesa ForeverTree model.

This reuses the constants, climate loading, and growth math from
``forevertree.py`` unchanged, and overrides only the per-step loop so that the
independent patches within a step run across a thread pool. On a standard
(GIL-enabled) CPython this would not parallelize, because the per-tree float
arithmetic holds the GIL; it is meant to be run on a free-threaded build
(``python3.14t``) with ``PYTHON_GIL=0`` so the GIL stays disabled even after
``cftime`` is imported.

Thread-safety note: ``numpy``'s ``Generator`` is not safe to call from multiple
threads at once, so each worker thread draws its stochastic term from its own
``Generator`` (kept in ``threading.local``), seeded deterministically from the
replicate seed and the worker's chunk index. Results therefore differ from the
serial run draw-for-draw, but come from the same distribution -- fine for a
wall-clock benchmark of the same arithmetic workload.
"""

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import forevertree as ft
from forevertree import (
    DELTA_H_MAX,
    STOCHASTIC_STD,
    ForeverTreeModel,
    _ONE,
    _precipitation_impact,
    _temperature_impact,
)


def _step_patches(model, patches, rng):
    """Advance every tree in a chunk of patches by one step.

    Mirrors ``ForeverTree.step`` exactly -- the temperature/precipitation impact
    math is computed *per tree*, not hoisted to once per patch, so this thread
    pool performs the identical per-tree workload as the serial model and as
    Josh (whose impacts are organism-level). Only ``rng`` is worker-local so
    concurrent workers never touch a shared Generator. The threading speedup
    therefore reflects parallelism alone, not a reduced amount of work.
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
            temp_pct = _temperature_impact(temp_k)
            precip_pct = _precipitation_impact(precip_mm)
            stochastic = ft.D(rng.normal(1.0, STOCHASTIC_STD))
            tree.height += DELTA_H_MAX * temp_pct * precip_pct * stochastic
            tree.age += _ONE


class ThreadedForeverTreeModel(ForeverTreeModel):
    def __init__(self, temp_path, precip_path, seed=None, n_threads=None):
        super().__init__(temp_path, precip_path, seed=seed)
        self.n_threads = n_threads or (os.cpu_count() or 1)
        self._seed = 0 if seed is None else seed

        # Precompute a static partition of patches into one chunk per worker.
        all_patches = [
            (col, row)
            for row in range(self.n_rows)
            for col in range(self.n_cols)
        ]
        self._chunks = [all_patches[i::self.n_threads] for i in range(self.n_threads)]

        # One Generator per worker chunk, kept in thread-local storage and
        # seeded deterministically from the replicate seed + chunk index.
        self._tls = threading.local()
        self._chunk_seeds = [
            np.random.SeedSequence([self._seed, i]) for i in range(self.n_threads)
        ]
        self._executor = ThreadPoolExecutor(max_workers=self.n_threads)

    def _worker(self, chunk_idx):
        rng = getattr(self._tls, "rng", None)
        if rng is None:
            rng = np.random.default_rng(self._chunk_seeds[chunk_idx])
            self._tls.rng = rng
        _step_patches(self, self._chunks[chunk_idx], rng)

    def step(self):
        list(self._executor.map(self._worker, range(self.n_threads)))
        self._record_step()
        self.current_step += 1

    def run(self):
        try:
            return super().run()
        finally:
            self._executor.shutdown(wait=True)


if __name__ == "__main__":
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
