# Sanitising an export before it is committed

n8n and Make exports carry more than the graph. Before anything lands in this repo it goes through
[`scripts/sanitise.py`](scripts/sanitise.py) and then a human read.

## Workflow

Drop the raw export in `raw/` — that directory is gitignored, so an unsanitised file cannot be
committed by accident.

```bash
python scripts/sanitise.py raw/audiobook.json -o 01-audiobook-generation/workflow.json
```

The script prints what it redacted and then lists anything left that still *looks* like a secret.
Read that list. It is deliberately noisy — it would rather flag a harmless CDN URL than stay quiet
about a live endpoint.

Verify before committing:

```bash
python scripts/sanitise.py --check 01-audiobook-generation/workflow.json
git diff --cached
```

`--check` exits non-zero when the residual scan finds something, so it works as a pre-commit gate.

## What gets replaced

Across the seven exports in this repo, 104 values.

**By key name** — anything under `apiKey`, `token`, `secret`, `password`, `authorization`,
`clientSecret`, `privateKey` and similar. n8n credential blocks keep their display name (`OpenAi
account`) and lose the instance id: the name documents which credential type to configure, the id is
meaningless outside one instance.

Resource pointers (`documentId`, `sheetId`, `folderId`, `calendarId`, `campaign`) and account or
contact fields (`tcsaccount`, `mobile`, `phone`) are replaced too. Not credentials, but they identify
a real billing account or a real person.

**By shape, anywhere in the file** — JWTs and Supabase anon keys, `sk-` OpenAI keys, `sk_` ElevenLabs
keys, `sk-ant-` Anthropic keys, `cal_live_` Cal.com keys, `gh*_` GitHub tokens, `AIza…` Google keys,
`xox*-` Slack tokens, `Bearer …` headers, Supabase project URLs, Make and n8n webhook URLs, bare 32+
character hex strings, and email addresses.

**In the four places a key name alone doesn't reach.** Each of these leaked a real credential on a
first pass and is the reason the residual scan exists:

- *Query strings.* `?accesstoken=…` is still a token. The key name lives in the URL, not in the JSON.
- *Resource locators.* n8n stores `{"__rl": true, "value": "<real id>", "cachedResultUrl": "https://…"}`,
  so the leaf key is `value` and the cached URL embeds the id a second time, under a different parent.
- *Embedded request bodies.* Make stores a whole JSON document inside a string. Its quotes arrive
  escaped (`\"accesstoken\"`), so text patterns miss it. The parsed form is walked instead — and when
  the body contains unquoted templates (`{{5.total}}`) and won't parse at all, an escaped-text pass
  catches it.
- *Name/value parameter pairs.* n8n HTTP headers and body fields are `{"name": "campaign", "value": "…"}`,
  so the meaningful key is a sibling of the value rather than its parent.

**Left alone deliberately** — public vendor hosts (`api.elevenlabs.io`, `api.cal.com`,
`ociconnect.tcscourier.com` …), because they document the stack and that is the point. Template
references (`{{3.record.shipping_phone}}`) are wiring, not data. n8n's internal UUIDs — node ids,
condition ids, `versionId` — are structural and unlock nothing.

## What the script cannot do

**Prompt text.** Prompts are the most likely place for something that shouldn't be public — a client
name, a pricing rule, an internal policy, a real customer example used as a few-shot. No regex finds
those. Read every prompt in the export.

**Business logic in comments and node names.** A node called `Book TCS for Karachi orders over 5000`
tells a reader about the business. Usually fine — this is a portfolio, the detail is the point — but
it is a decision, so make it deliberately.

**NDA'd client work.** If a workflow was built for a client under NDA, genericise the client name or
leave the workflow out. The shipping automation is the author's own business, so it is named.

## Why credential *ids* are safe

An n8n credential id is a pointer into one instance's credential store. Without access to that
instance it unlocks nothing. They are replaced here anyway — they add no value to a reader and cost
nothing to remove.
