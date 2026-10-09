"""``python -m app.workers`` - the analysis worker's entry point.

Kept to three lines on purpose: ``runner.main`` is where the process is defined, and a
second place that decides what a worker is would be a second thing to keep in step with
it.
"""

import sys

from app.workers.runner import main

if __name__ == "__main__":
    sys.exit(main())
