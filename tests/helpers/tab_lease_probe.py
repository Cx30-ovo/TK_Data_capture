"""Child-process probe; never connects to a browser."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.douyin_browser_coordinator import DouyinTabLease, DouyinBrowserBusyError


async def main():
    try:
        async with DouyinTabLease(path=sys.argv[1], timeout=0.15):
            print("acquired", flush=True)
    except DouyinBrowserBusyError:
        print("busy", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
