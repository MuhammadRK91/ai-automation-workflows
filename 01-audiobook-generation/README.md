# Audiobook generation

*n8n · gpt-4o · ElevenLabs · PDF.co · Transloadit · Supabase*

PDF in, narrated audio summary out. Map-reduce summarisation, per-segment speech synthesis, then async concatenation polled to completion.

![Workflow canvas](canvas.png)

| File | What it is |
|---|---|
| `workflow.json` | Sanitised export — import into n8n |
| `canvas.png` | The graph as built |

Every credential, account id, webhook path and resource id in the export is a placeholder. See
[SANITISING.md](../SANITISING.md) for what was replaced and why.

Full write-up with the design rationale is in the [root README](../README.md#01--audiobook-generation).
