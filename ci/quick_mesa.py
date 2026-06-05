"""Quick-check runner for the Mesa ForeverTree references (single timestep).

Used by CI smoke tests only. This imports the real reference modules unchanged
and overrides their module-level step count to L{STEPS} before delegating to
their C{main} functions, so a config can be exercised end-to-end in a fraction
of a second without touching the benchmark models or their step count.

Run as C{python ci/quick_mesa.py <variant> [replicates] [threads]} where
C{variant} is C{serial} or C{threaded}.

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

  Reads the variant (C{serial} or C{threaded}) and replicate count from
  C{argv}, forces L{forevertree.NUM_STEPS} down to L{STEPS} (both the serial and
  threaded models loop over that module global), and delegates to the matching
  reference C{main}.
  """
  variant = sys.argv[1] if len(sys.argv) > 1 else "serial"
  replicates = sys.argv[2] if len(sys.argv) > 2 else "2"

  forevertree.NUM_STEPS = STEPS

  if variant == "threaded":
    import forevertree_threaded
    threads = sys.argv[3] if len(sys.argv) > 3 else "2"
    sys.argv = [sys.argv[0], replicates, threads]
    forevertree_threaded.main()
  else:
    sys.argv = [sys.argv[0], replicates]
    forevertree.main()


if __name__ == "__main__":
  main()
