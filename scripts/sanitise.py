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
    # Anchored, so compound names need spelling out: dataTableId does not match
    # "table[_-]?id" because it begins with "data".
    r"^(?:(?:document|sheet|spreadsheet|folder|drive|file|calendar|database|table|base|"
    r"data[_-]?table|project|team|channel|chat|assistant|vector[_-]?store|"
    # Voice-provider resources. A VAPI scenario names the assistant AND the phone
    # number it dials from; redacting only the assistant leaves half the pair.
    r"phone[_-]?number|voice|actor)[_-]?id"
    r"|(?:campaign|workspace|audience|segment|mailbox)(?:[_-]?id)?)$",
    re.IGNORECASE,
)

# A webhook path is half of a live, usually unauthenticated endpoint. The host is
# redacted separately, but leaving the path published means anyone who guesses or
# learns the host has a working URL. `path` is only redacted when it is UUID-shaped,
# so ordinary file paths in other node types are left alone.
WEBHOOK_ID_KEY = re.compile(r"^(?:webhook[_-]?id|path)$", re.IGNORECASE)

# Account numbers and personal contact details. Not credentials, but they identify
# a real person or a real billing account and do not belong in a public repo.
# Values that are template references ({{3.record.phone}}) are left alone — those
# are wiring, not data.
ACCOUNT_KEY = re.compile(
    r"^(?:tcsaccount|account_?(?:no|number)|customer_?(?:no|id)|mobile|phone|msisdn|contact_?no)$",
    re.IGNORECASE,
)
TEMPLATE = re.compile(r"\{\{|^\s*$")

UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# --- pass 2: value shapes, wherever they appear -----------------------------

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Secrets passed as URL query parameters. A token in a query string is still a
    # token, and this is the shape that most often survives a key-name-based pass.
    ("query-string secret",
     re.compile(r"([?&](?:access_?token|api_?key|auth|key|token|secret|password|signature)=)(?!YOUR_)[^&\"'\s}]+", re.IGNORECASE),
     r"\1YOUR_TOKEN"),
    # Credentials inside a JSON blob that is itself stored as a string, which is how
    # Make stores request bodies. Templates ({{...}}) are left alone — they are
    # references to earlier modules, not data.
    ("embedded JSON secret",
     re.compile(r"(\"(?:access_?token|api_?key|token|secret|password|client_?secret|tcsaccount|account_?no|mobile|phone)\"\s*:\s*\")(?!\{\{|YOUR_)[^\"]+(\")", re.IGNORECASE),
     r"\1YOUR_VALUE\2"),
    # Same idea as the structural pass, but for request bodies that are NOT valid
    # JSON — Make templates like {{5.total}} appear unquoted, so json.loads refuses
    # them and the only way in is the escaped text.
    ("escaped JSON secret",
     re.compile(r"(\\\"(?:access_?token|api_?key|token|secret|password|client_?secret|tcsaccount|account_?no|mobile|phone)\\\"\s*:\s*\\\")(?!\{\{|YOUR_)([^\\\"]+)(\\\")", re.IGNORECASE),
     r"\1YOUR_VALUE\3"),
    ("Cal.com key",       re.compile(r"cal_(?:live|test)_[A-Za-z0-9]{16,}"), "YOUR_CALCOM_API_KEY"),
    # ElevenLabs uses sk_ with an underscore, unlike OpenAI's sk- with a hyphen.
    ("ElevenLabs key",    re.compile(r"\bsk_[A-Za-z0-9]{32,}"), "YOUR_ELEVENLABS_API_KEY"),
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
    # A test call target left in a flow is a real phone number in a public repo.
    # Matched on shape, not on key name: the outbound-caller export carried it as a
    # bare "number" value inside an embedded JSON body, where no key name gave it away.
    ("E.164 phone number", re.compile(r"(?<![\d+])\+\d{9,15}\b"), "+10000000000"),
    # Airtable base/table/record ids identify a live workspace. Not credentials, but
    # they name someone's data, and they survive every key-name-based rule.
    # The digit is required: without it "appendAttribution" (an n8n Gmail option key)
    # matches as app + 14 chars, and a sanitiser that corrupts config is worse than one
    # that misses. Real Airtable ids are always mixed alphanumeric.
    ("Airtable id",        re.compile(r"\b(?:app|tbl|rec|viw|fld)(?=[A-Za-z0-9]{14}\b)[A-Za-z]*[0-9][A-Za-z0-9]*\b"), "YOUR_AIRTABLE_ID"),
]

# Public vendor API endpoints. Keeping them is the point — they document the stack —
# so they are excluded from the residual report to keep it worth reading.
VENDOR_HOSTS = re.compile(
    # Any subdomain: maps.googleapis.com and queue.fal.run are as public as api.openai.com,
    # and an allowlist that only understood "api." was reporting them as findings.
    r"^https?://(?:[a-z0-9-]+\.)*(?:elevenlabs\.io|transloadit\.com|anymailfinder\.com|"
    r"instantly\.ai|cal\.com|openai\.com|anthropic\.com|tcscourier\.com|googleapis\.com|"
    r"google\.com|runwayml\.com|fal\.run|fal\.ai|leonardo\.ai|telegram\.org|pdf\.co|"
    r"supabase\.com|make\.com)",
    re.IGNORECASE,
)

# Long snake_case or plain-word strings are identifiers, not secrets. A schema field
# called reveal_answer_after_wrong_attempts is 34 characters of pure signal-free noise
# in a report, and noise is what teaches people to stop reading the report.
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+$|^[A-Za-z]+$")

# Shapes that survive redaction and are worth a second look by a human.
RESIDUAL = [
    ("long opaque string", re.compile(r"\b[A-Za-z0-9_-]{32,}\b")),
    ("uuid",               re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    ("http(s) host",       re.compile(r"https?://(?!YOUR_|hook\.make\.com)[A-Za-z0-9.-]+")),
]

PLACEHOLDER = "YOUR_VALUE"


def embedded_json(value: str):
    """Return the parsed object if this string is itself a JSON document."""
    s = value.lstrip()
    if not s.startswith(("{", "[")):
        return None
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def walk(node, counts: Counter, parent_key: str = ""):
    """Pass 1 — replace values by key name, in place."""
    if isinstance(node, dict):
        # n8n resource locator: {"__rl": true, "value": "<real id>", "mode": "list",
        # "cachedResultName": "My Sheet", "cachedResultUrl": "https://..."}. The leaf
        # key is "value", so a key-name match on the parent is the only way to catch it.
        if node.get("__rl"):
            if RESOURCE_ID_KEY.match(parent_key or "") and isinstance(node.get("value"), str) and node["value"]:
                node["value"] = f"YOUR_{parent_key.upper()}"
                counts[f"resource locator '{parent_key}'"] += 1
            # A cached URL always embeds the real resource id, whatever the parent
            # key is called — sheetName.cachedResultUrl leaks the spreadsheet id
            # just as documentId.cachedResultUrl does.
            if node.get("cachedResultUrl"):
                node["cachedResultUrl"] = "YOUR_RESOURCE_URL"
                counts["cachedResultUrl"] += 1

        # n8n HTTP nodes carry headers and body fields as {"name": ..., "value": ...}
        # pairs, so the meaningful key sits in a sibling rather than above the value.
        # Expressions (leading "=") and templates are wiring, not data.
        pname = node.get("name")
        pval = node.get("value")
        if isinstance(pname, str) and isinstance(pval, str) and pval and not pval.startswith(("=", "YOUR_")) \
                and not TEMPLATE.search(pval):
            label = pname.strip()
            if SECRET_KEY.search(label) or RESOURCE_ID_KEY.match(label) or ACCOUNT_KEY.match(label):
                node["value"] = PLACEHOLDER
                counts[f"parameter '{label}'"] += 1

        for key, value in list(node.items()):
            # n8n credential block: {"openAiApi": {"id": "...", "name": "OpenAi account"}}
            if key == "credentials" and isinstance(value, dict):
                # The credential *type* (openAiApi, supabaseApi) is what tells an
                # importer which credential to configure, and it is the dict key —
                # so both the id and the user-chosen display name can go. Names are
                # not secret but they leak unrelated project names.
                for ctype, cred in value.items():
                    if isinstance(cred, dict):
                        if "id" in cred:
                            cred["id"] = "YOUR_CREDENTIAL_ID"
                            counts["credential id"] += 1
                        if cred.get("name"):
                            cred["name"] = f"YOUR_{ctype}_CREDENTIAL"
                            counts["credential name"] += 1
                walk(value, counts, key)
            elif isinstance(value, (dict, list)):
                walk(value, counts, key)
            elif isinstance(value, str) and embedded_json(value) is not None:
                # Make stores request bodies as a JSON document inside a string.
                # Walking the parsed form is far more reliable than pattern-matching
                # the escaped text, where every quote arrives as \" instead of ".
                inner = embedded_json(value)
                before = json.dumps(inner, sort_keys=True)
                walk(inner, counts, key)
                if json.dumps(inner, sort_keys=True) != before:
                    node[key] = json.dumps(inner, indent=2, ensure_ascii=False)
                    counts["embedded JSON body"] += 1
            elif isinstance(value, str) and value:
                if SECRET_KEY.search(key) and not value.startswith("=") and not TEMPLATE.search(value):
                    # An n8n expression ("={{ ... }}") or a Make template is wiring,
                    # not data. Redacting it silently breaks the imported workflow,
                    # which is worse than leaving a reference in place: the reader
                    # cannot tell the logic was removed rather than never written.
                    node[key] = PLACEHOLDER
                    counts[f"key '{key}'"] += 1
                elif ACCOUNT_KEY.match(key) and not TEMPLATE.search(value):
                    node[key] = PLACEHOLDER
                    counts[f"key '{key}' (account / contact)"] += 1
                elif WEBHOOK_ID_KEY.match(key) and UUID.match(value):
                    node[key] = "YOUR_WEBHOOK_ID"
                    counts[f"key '{key}' (webhook path)"] += 1
                elif RESOURCE_ID_KEY.match(key) and len(value) >= 6:
                    node[key] = f"YOUR_{key.upper()}"
                    counts[f"key '{key}'"] += 1
    elif isinstance(node, list):
        for item in node:
            walk(item, counts, parent_key)


def scrub_text(text: str, counts: Counter) -> str:
    """Pass 2 — replace values by shape, across the whole document."""
    for label, pattern, replacement in PATTERNS:
        text, n = pattern.subn(replacement, text)
        if n:
            counts[label] += n
    return text


def node_ids(data) -> set[str]:
    """Internal identifiers: nodes, filter conditions, Set assignments, versionId.

    These are structural — n8n generates them and they unlock nothing. Reporting
    them buries the findings that matter under dozens of lines of noise, which is
    how a security report gets ignored. Only UUID-shaped values are collected, so
    a credential stored under a key called `id` is still reported.
    """
    ids: set[str] = set()

    def collect(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("id", "versionId", "instanceId") and isinstance(value, str) and UUID.match(value):
                    ids.add(value)
                else:
                    collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(data)
    return ids


def residual_report(text: str, benign: set[str]) -> list[str]:
    findings = []
    for label, pattern in RESIDUAL:
        hits = {m.group(0) for m in pattern.finditer(text)}
        hits = {h for h in hits if not h.startswith("YOUR_") and h not in benign
                and not VENDOR_HOSTS.match(h) and not IDENTIFIER.match(h)}
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
    benign = node_ids(data)
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

    findings = residual_report(text, benign)
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
