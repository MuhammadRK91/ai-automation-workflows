#!/usr/bin/env python3
"""Strip credentials and environment-specific identifiers from n8n / Make exports.

    python scripts/sanitise.py raw/audiobook.json -o 01-audiobook-generation/workflow.json
    python scripts/sanitise.py --check 01-audiobook-generation/workflow.json

Two passes run over every file:

  1. A structural walk. Values under keys whose name looks secret-bearing
     (token, apiKey, password, ...) are replaced wholesale, and n8n credential
     blocks keep their display name while losing the instance id.

  2. A regex pass over the serialised text, for secrets that live inside
     free-form strings — URLs, JWTs, provider keys — where the key name gives
     nothing away.

Afterwards a residual scan looks for anything that still has the shape of a
secret and reports it. Automated redaction is a first pass, not a substitute
for reading the diff.

Exit status is 1 if the residual scan finds something, so this can gate CI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# --- pass 1: keys whose value is replaced regardless of content -------------

SECRET_KEY = re.compile(
    r"(?:^|_|\b)(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|token|secret|"
    r"password|passwd|authorization|auth[_-]?header|client[_-]?secret|private[_-]?key|"
    r"session[_-]?key|signing[_-]?key)(?:$|_|\b)",
    re.IGNORECASE,
)

# Identifiers that point at one specific account's resources. Not secret, but
# meaningless to anyone else and a small privacy leak.
RESOURCE_ID_KEY = re.compile(
    r"^(?:document|sheet|spreadsheet|folder|drive|file|calendar|database|table|base|"
    r"project|team|channel|chat)[_-]?id$",
    re.IGNORECASE,
)

# A webhook path is half of a live, usually unauthenticated endpoint. The host is
# redacted separately, but leaving the path published means anyone who guesses or
# learns the host has a working URL. `path` is only redacted when it is UUID-shaped,
# so ordinary file paths in other node types are left alone.
WEBHOOK_ID_KEY = re.compile(r"^(?:webhook[_-]?id|path)$", re.IGNORECASE)

UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# --- pass 2: value shapes, wherever they appear -----------------------------

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("JWT / Supabase key", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "YOUR_JWT"),
    ("OpenAI key",         re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "YOUR_OPENAI_API_KEY"),
    ("Anthropic key",      re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "YOUR_ANTHROPIC_API_KEY"),
    ("GitHub token",       re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "YOUR_GITHUB_TOKEN"),
    ("Google API key",     re.compile(r"AIza[0-9A-Za-z_-]{30,}"), "YOUR_GOOGLE_API_KEY"),
    ("Slack token",        re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "YOUR_SLACK_TOKEN"),
    ("Bearer header",      re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}"), "Bearer YOUR_TOKEN"),
    ("Supabase project",   re.compile(r"https://[a-z]{15,30}\.supabase\.co"), "https://YOUR_PROJECT.supabase.co"),
    ("Make webhook",       re.compile(r"https://hook\.[a-z0-9]+\.make\.com/[A-Za-z0-9]+"), "https://hook.make.com/YOUR_WEBHOOK_ID"),
    ("n8n webhook",        re.compile(r"https?://[A-Za-z0-9.-]+/webhook(?:-test)?/[0-9a-fA-F-]{16,}"), "https://YOUR_N8N_HOST/webhook/YOUR_WEBHOOK_ID"),
    ("hex secret",         re.compile(r"\b[0-9a-f]{32,}\b"), "YOUR_SECRET"),
    ("email address",      re.compile(r"\b[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "you@example.com"),
]

# Shapes that survive redaction and are worth a second look by a human.
RESIDUAL = [
    ("long opaque string", re.compile(r"\b[A-Za-z0-9_-]{32,}\b")),
    ("uuid",               re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    ("http(s) host",       re.compile(r"https?://(?!YOUR_|hook\.make\.com)[A-Za-z0-9.-]+")),
]

PLACEHOLDER = "YOUR_VALUE"


def walk(node, counts: Counter):
    """Pass 1 — replace values by key name, in place."""
    if isinstance(node, dict):
        for key, value in list(node.items()):
            # n8n credential block: {"openAiApi": {"id": "...", "name": "OpenAi account"}}
            if key == "credentials" and isinstance(value, dict):
                for cred in value.values():
                    if isinstance(cred, dict) and "id" in cred:
                        cred["id"] = "YOUR_CREDENTIAL_ID"
                        counts["credential id"] += 1
                walk(value, counts)
            elif isinstance(value, (dict, list)):
                walk(value, counts)
            elif isinstance(value, str) and value:
                if SECRET_KEY.search(key):
                    node[key] = PLACEHOLDER
                    counts[f"key '{key}'"] += 1
                elif WEBHOOK_ID_KEY.match(key) and UUID.match(value):
                    node[key] = "YOUR_WEBHOOK_ID"
                    counts[f"key '{key}' (webhook path)"] += 1
                elif RESOURCE_ID_KEY.match(key) and len(value) >= 6:
                    node[key] = f"YOUR_{key.upper()}"
                    counts[f"key '{key}'"] += 1
    elif isinstance(node, list):
        for item in node:
            walk(item, counts)


def scrub_text(text: str, counts: Counter) -> str:
    """Pass 2 — replace values by shape, across the whole document."""
    for label, pattern, replacement in PATTERNS:
        text, n = pattern.subn(replacement, text)
        if n:
            counts[label] += n
    return text


def residual_report(text: str) -> list[str]:
    findings = []
    for label, pattern in RESIDUAL:
        hits = {m.group(0) for m in pattern.finditer(text)}
        hits = {h for h in hits if not h.startswith("YOUR_")}
        for hit in sorted(hits)[:15]:
            findings.append(f"{label}: {hit[:90]}")
    return findings


def process(path: Path, out: Path | None, check_only: bool) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"! {path}: {exc}", file=sys.stderr)
        return 1

    counts: Counter = Counter()
    if not check_only:
        walk(data, counts)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if not check_only:
        text = scrub_text(text, counts)

    print(f"\n=== {path} ===")
    if check_only:
        print("check only — nothing written")
    elif counts:
        for label, n in counts.most_common():
            print(f"  redacted {n:>3}  {label}")
    else:
        print("  nothing matched")

    findings = residual_report(text)
    if findings:
        print(f"  -- {len(findings)} thing(s) to eyeball before committing --")
        for f in findings:
            print(f"     {f}")

    if not check_only and out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"  wrote {out}")

    return 1 if findings else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, help="output path (single input only)")
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    if args.out and len(args.files) > 1:
        ap.error("-o takes a single input file")

    status = 0
    for path in args.files:
        out = args.out if args.out else (None if args.check else path)
        status |= process(path, out, args.check)

    if status:
        print("\nResidual findings above. Read them, fix what matters, re-run.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
