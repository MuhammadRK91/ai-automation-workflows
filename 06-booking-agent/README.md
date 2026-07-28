# Conversational booking agent

*Make · OpenAI · Google Calendar*

Handles scheduling, rescheduling and cancellation from natural language. The calendar stays the source of truth for availability; the model only handles language.

![Workflow canvas](canvas.png)

| File | What it is |
|---|---|
| `workflow.json` | Sanitised export — import into Make |
| `canvas.png` | The graph as built |

Every host, credential, id and webhook URL in the export is a placeholder. See
[SANITISING.md](../SANITISING.md) for what was replaced and why.

The full write-up, including the design rationale, is in the
[root README](../README.md#conversational-booking-agent).
