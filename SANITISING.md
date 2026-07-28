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

**By key name** — anything under `apiKey`, `token`, `secret`, `password`, `authorization`,
`clientSecret`, `privateKey` and similar. n8n credential blocks keep their display name (`OpenAi
account`) and lose the instance id, because the name documents which credential type to configure and
the id is meaningless outside one instance.

Resource pointers — `documentId`, `sheetId`, `folderId`, `driveId`, `calendarId` — are also replaced.
Not secret, but they identify one person's Drive and are useless to anyone importing the workflow.

**By shape, anywhere in the file** — JWTs and Supabase anon keys, `sk-` OpenAI keys, `sk-ant-`
Anthropic keys, `gh*_` GitHub tokens, `AIza…` Google keys, `xox*-` Slack tokens, `Bearer …` headers,
Supabase project URLs, Make webhook URLs, n8n webhook URLs, bare 32+ character hex strings, and email
addresses.

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
