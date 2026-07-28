# Multi-channel social publishing

*Make · OpenAI (text + image) · Supabase Storage · Instagram, Facebook, LinkedIn, X*

Takes a content backlog from a spreadsheet, generates copy and imagery, and publishes across four platforms on a schedule with a per-destination router.

![Workflow canvas](canvas.png)

| File | What it is |
|---|---|
| `workflow.json` | Sanitised export — import into Make |
| `canvas.png` | The graph as built |

Every host, credential, id and webhook URL in the export is a placeholder. See
[SANITISING.md](../SANITISING.md) for what was replaced and why.

The full write-up, including the design rationale, is in the
[root README](../README.md#multi-channel-social-publishing).
