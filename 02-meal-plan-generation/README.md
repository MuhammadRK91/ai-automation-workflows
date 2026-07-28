# Personalised meal plan generation

*n8n · OpenAI (agent with memory + tools) · Supabase*

Generates a day's meal plan against a user's goals and constraints. Nutrition maths runs in code before the model is called, so the LLM composes to targets rather than calculating them.

![Workflow canvas](canvas.png)

| File | What it is |
|---|---|
| `workflow.json` | Sanitised export — import into n8n |
| `canvas.png` | The graph as built |

Every host, credential, id and webhook URL in the export is a placeholder. See
[SANITISING.md](../SANITISING.md) for what was replaced and why.

The full write-up, including the design rationale, is in the
[root README](../README.md#personalised-meal-plan-generation).
