"""Run the seed with unbuffered output and a stack-dump watchdog.

If the run stalls, faulthandler prints the stack of every thread after three
minutes, which names the call that is blocked instead of leaving us guessing.
"""

import faulthandler
import sys

faulthandler.enable()
faulthandler.dump_traceback_later(180, repeat=True, file=sys.stdout)

from scripts.seed import seed  # noqa: E402

if __name__ == "__main__":
    import asyncio

    asyncio.run(seed())
