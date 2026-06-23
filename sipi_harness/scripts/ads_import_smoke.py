from __future__ import annotations

import os
import sys

print("python:", sys.executable, flush=True)
print("HPEESOF_DIR:", os.environ.get("HPEESOF_DIR"), flush=True)
print("before import keysight.ads.de", flush=True)
import keysight.ads.de as de

print("after import keysight.ads.de", flush=True)
print("workspace_is_open:", de.workspace_is_open(), flush=True)
