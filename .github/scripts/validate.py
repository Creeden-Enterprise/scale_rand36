#!/usr/bin/env python3
"""
data-validate — generic-but-real structural validator for the creeden-*-db
clinical reference databases. Workflow-migration Phase 2c (issue #1198, option
(b)+(c): generic-but-real validator + licensed-content guardrail, populate-gated).

Deployed identically to every armed creeden-*-db repo at
`.github/scripts/validate.py`, run by `.github/workflows/data-validate.yml`.
This file in the jcpd hub is the canonical audit-trail copy of what was deployed.

Checks (all real signal on every repo — never a trivially-passing no-op):
  1. No git merge-conflict markers in any tracked text file.
  2. Every *.json file is well-formed JSON (the structured clinical extraction).
  3. Every *.csv / *.tsv file is parseable (forward-compat; no CSV today).
  4. Naming convention: files under data/ are lowercase, no spaces.
  5. Licensed-content / binary guardrail: NO raw source documents
     (.pdf/.epub/.docx/...), archives, or oversized blobs committed. The
     structured JSON extraction under data/ is the product and is allowed; the
     raw licensed *source* (textbook PDF/EPUB/DOCX, etc.) must never enter git
     history. This is the Phase-2c licensed-content guardrail — real signal on
     EVERY repo (and most valuable on the licensed DBs precisely in the window
     when they first get populated).

Reports ALL failures (not first-fail). Exit 0 = green, exit 1 = failure.
stdlib only — runs on any python3, no pip install.
"""
import csv
import json
import os
import subprocess
import sys

MAX_BLOB_BYTES = 8 * 1024 * 1024  # 8 MB — guardrail against accidental large binaries

# Raw licensed-source + archive + opaque-binary formats that must never be
# committed. The structured JSON/CSV extraction is the product, NOT these.
FORBIDDEN_EXT = {
    ".pdf", ".epub", ".mobi", ".azw", ".azw3", ".kfx",
    ".doc", ".docx", ".rtf", ".odt",
    ".xls", ".xlsx", ".ods",
    ".ppt", ".pptx", ".odp",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2",
    ".db", ".sqlite", ".sqlite3",
}

CONFLICT_START = "<<<<<<<"
CONFLICT_MID = "======="
CONFLICT_END = ">>>>>>>"


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    )
    return [p for p in out.stdout.splitlines() if p]


def is_probably_text(path):
    try:
        with open(path, "rb") as f:
            return b"\x00" not in f.read(8192)
    except OSError:
        return False


def main():
    failures = []
    files = tracked_files()

    for path in files:
        ext = os.path.splitext(path)[1].lower()

        # (5) guardrail — forbidden raw-source / binary extensions
        if ext in FORBIDDEN_EXT:
            failures.append(
                f"[guardrail] forbidden licensed-source/binary file committed: {path}"
            )
            continue

        # (5) guardrail — oversized blob
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if size > MAX_BLOB_BYTES:
            failures.append(
                f"[guardrail] file exceeds {MAX_BLOB_BYTES} bytes ({size}): {path}"
            )

        # (4) naming convention under data/
        if path.startswith("data/"):
            base = os.path.basename(path)
            if base != base.lower() or " " in path:
                failures.append(
                    f"[naming] data file must be lowercase, no spaces: {path}"
                )

        # (1) merge-conflict markers — text files only
        if is_probably_text(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError as e:
                failures.append(f"[read] could not read {path}: {e}")
                lines = []
            has_start = any(ln.startswith(CONFLICT_START) for ln in lines)
            for i, ln in enumerate(lines, 1):
                if ln.startswith(CONFLICT_START) or ln.startswith(CONFLICT_END):
                    failures.append(f"[conflict] merge-conflict marker at {path}:{i}")
                elif ln.rstrip() == CONFLICT_MID and has_start:
                    failures.append(f"[conflict] merge-conflict marker at {path}:{i}")

        # (2) JSON well-formedness
        if ext == ".json":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    json.load(f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
                failures.append(f"[json] invalid JSON in {path}: {e}")

        # (3) CSV / TSV parseability
        if ext in (".csv", ".tsv"):
            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    delim = "\t" if ext == ".tsv" else ","
                    for _ in csv.reader(f, delimiter=delim):
                        pass
            except (csv.Error, OSError, UnicodeDecodeError) as e:
                failures.append(f"[csv] invalid CSV in {path}: {e}")

    json_count = sum(1 for p in files if p.lower().endswith(".json"))
    print(
        f"data-validate: scanned {len(files)} tracked files ({json_count} JSON)."
    )
    if failures:
        print(f"\nFAIL - {len(failures)} issue(s):")
        for msg in failures:
            print(f"  - {msg}")
        sys.exit(1)
    print("OK - all structural checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
