"""Run the library indexer in the foreground:  python -m app.index_cli [--scan-only]"""
from __future__ import annotations

import logging
import sys
import threading
import time

from . import db, indexer


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    db.init()
    n = indexer.scan()
    print(f"scan: {n} files", flush=True)
    if "--scan-only" in sys.argv:
        return
    t = threading.Thread(target=indexer.extract_all, daemon=True)
    t.start()
    while t.is_alive():
        time.sleep(60)
        s = indexer.status()
        print(f"extract: {s['text_done']}/{s['text_total']}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
