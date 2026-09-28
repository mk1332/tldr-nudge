#!/usr/bin/env python3
"""Run every tldr-nudge test file and report a single total."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["test_hook.py", "test_mute.py"]
TALLY = re.compile(r"^(\d+)/(\d+) passed", re.M)

passed = total = 0
for name in FILES:
    print(f"===== {name} =====")
    p = subprocess.run([sys.executable, os.path.join(HERE, name)],
                       capture_output=True, text=True)
    sys.stdout.write(p.stdout)
    if p.stderr.strip():
        sys.stderr.write(p.stderr)
    m = TALLY.search(p.stdout)
    if not m or p.returncode != 0:
        print(f"{name}: could not read a tally, treating as failure")
        total += 1
        continue
    passed += int(m.group(1))
    total += int(m.group(2))
    print()

print(f"===== {passed}/{total} passed =====")
sys.exit(0 if passed == total else 1)
