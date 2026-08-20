"""Quick-check runner for the Mesa ForeverTree references (single timestep).

Used by CI smoke tests only. This imports the real reference modules unchanged
and overrides their module-level step count to L{STEPS} before delegating to
their C{main} functions, so a config can be exercised end-to-end in a fraction
of a second without touching the benchmark models or their step count.

Run as C{python ci/quick_mesa.py <variant> [replicates] [threads]} where
C{variant} is one of:

  - C{ai-serial}      -> forevertree.py (serial)
  - C{ai-threaded}    -> forevertree_threaded.py (free-threaded)
  - C{manual-serial}  -> forevertree_manual.py (serial)
  - C{manual-threaded}-> forevertree_manual.py (pathos ProcessPool)

@var STEPS: The reduced timestep count used for the smoke test.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference-mesa")
)

import forevertree

STEPS = 1


def main():
  """Run the requested Mesa config for a single timestep.

  Reads the variant (C{ai-serial}, C{ai-threaded}, C{manual-serial}, or
  C{manual-threaded}) and replicate count from C{argv}, forces the relevant
  step-count global down to L{STEPS}, and delegates to the matching reference
  C{main}.
  """
  variant = sys.argv[1] if len(sys.argv) > 1 else "ai-serial"
  replicates = sys.argv[2] if len(sys.argv) > 2 else "2"

  if variant in ("manual-serial", "manual-threaded"):
    import forevertree_manual
    threaded = "true" if variant == "manual-threaded" else "false"
    out_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "reference-mesa", "output"
    )
    template = os.path.join(
        out_dir, "results_manual_%d_parallel.csv" if threaded == "true"
        else "results_manual_%d.csv"
    )
    os.makedirs(out_dir, exist_ok=True)
    forevertree_manual.NUM_TIMESTEPS = STEPS
    sys.argv = [sys.argv[0], replicates, threaded, template]
    forevertree_manual.main()
    return

  forevertree.NUM_STEPS = STEPS

  if variant == "ai-threaded":
    import forevertree_threaded
    threads = sys.argv[3] if len(sys.argv) > 3 else "2"
    sys.argv = [sys.argv[0], replicates, threads]
    forevertree_threaded.main()
  else:
    sys.argv = [sys.argv[0], replicates]
    forevertree.main()


if __name__ == "__main__":
  main()
