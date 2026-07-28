# AI Automation Workflows

Production automation pipelines I've built and run — LLM orchestration, media generation, data
enrichment and multi-system integration across n8n and Make.

These aren't demos. Each one runs on a schedule or a webhook and does real work: generating the
content behind two published mobile apps, booking couriers for an e-commerce business, running
outreach campaigns, managing calendars.

Every export in this repo is sanitised — see [SANITISING.md](SANITISING.md).

| Workflow | Platform | Folder |
|---|---|---|
| Audiobook generation | n8n | [`01-audiobook-generation`](01-audiobook-generation) |
| Personalised meal plans | n8n | [`02-meal-plan-generation`](02-meal-plan-generation) |
| Multi-channel social publishing | Make | [`03-social-publishing`](03-social-publishing) |
| E-commerce shipping | Make | [`04-ecommerce-shipping`](04-ecommerce-shipping) |
| Lead generation and outreach | n8n | [`05-lead-generation`](05-lead-generation) |
| Conversational booking agent | Make | [`06-booking-agent`](06-booking-agent) |

---

## Audiobook generation pipeline
*n8n · OpenAI · TTS · Transloadit · Supabase*

Turns an uploaded PDF into a narrated audio summary, end to end, triggered by webhook.

```
PDF upload → extract + paginate → chunk
   → map:    summarise each chunk        (LLM, parallel)
   → reduce: single coherent summary     (LLM)
   → clean + segment text
   → loop:   synthesise audio per segment (TTS)
             upload each to object storage
   → aggregate segment URLs
   → Transloadit assembly: concatenate into one track
   → poll assembly until complete (wait + status switch)
   → write public URL back to the database
   → respond to the original webhook
```

**The interesting problems here:**

*Context limits.* A book does not fit in a context window, so summarisation is map-reduce — summarise
chunks independently, then reduce those summaries into one narrative. Chunk boundaries are chosen on
page structure rather than raw token count, so sections aren't split mid-argument.

*TTS output is fragmented.* Speech synthesis is done per segment, which yields many audio files that
have to become one track. Transloadit handles the concatenation as an async assembly job, so the
pipeline submits, then polls with a wait-and-check loop until the assembly reports complete — rather
than blocking a worker for the duration.

*The webhook has to stay responsive.* Generation takes minutes. The flow writes the finished URL back
to the database, where the mobile client picks it up.

Powers **AudioBooks** on Google Play.

---

## Personalised meal plan generation
*n8n · OpenAI (agent with memory + tools) · Supabase*

Generates a day's meal plan conditioned on a user's goals, body metrics and dietary constraints.

```
webhook from app → compute targets (BMR/TDEE, macro split)
   → LLM agent (memory + tools) generates the plan against those constraints
   → parse and validate structure
   → look up existing row for this user/date
   → switch: create if absent, update if present
   → confirm back to the app
```

Deterministic nutrition maths is done in code *before* the model is called — the LLM composes meals to
hit targets it is given, rather than being trusted to calculate them. Model output is parsed and
validated before it reaches the database.

Powers **[CalTrack](https://play.google.com/store/apps/details?id=com.pet.caltrack)** on Google Play.

---

## Multi-channel social publishing
*Make · OpenAI (text + image) · Supabase Storage · Instagram, Facebook, LinkedIn, X*

Takes a content backlog from a spreadsheet and publishes finished posts across four platforms on a
schedule.

```
scheduled read of content queue → assemble into batch → structure as JSON
   → LLM: generate post copy
   → LLM: generate supporting angle/benefit text
   → write back to sheet (audit trail)
   → image generation → upload to object storage → public URL
   → router → Instagram · Facebook · LinkedIn · X
```

Each platform has different media handling, so the router branches per destination rather than
pretending one payload fits all. Generated assets are stored and logged before publishing, so a failed
post can be retried without regenerating content.

---

## E-commerce shipping automation
*Make · Supabase · OpenAI · TCS courier API · Google Drive*

Built for my own e-commerce business and running in production. Watches for new orders and books
couriers automatically, branching on payment method and order value — removing manual courier booking
from the daily operation entirely.

```
Supabase order event → normalise shipping city
   → LLM: resolve free-text city to courier city code
   → router: cash-on-delivery vs digital wallet
       └─ router: order value band
           → book courier consignment
           → write tracking number back to database
           → fetch consignment label
           → archive label to Drive
```

**Why an LLM for city codes:** customers type "Karachi", "karachi.", "KHI", "Karachi Sindh". The courier
API needs an exact code. This is fuzzy normalisation over messy human input with a long tail — a lookup
table handled the common cases and failed constantly on the rest.

Four parallel booking branches handle the payment-method and value combinations, each with its own
rules for what gets booked and how.

---

## Lead generation and outreach
*n8n · OpenAI · email finder API · verification · Instantly*

Sources prospects, enriches them, personalises a first line, and loads them into a sending platform.

```
read prospect list → filter → loop per prospect
   → LLM: normalise name into first/last
   → email finder API → success/error branch
   → validity check → discard unverifiable
   → LLM: generate a personalised icebreaker
   → push to campaign platform
```

Deliverability is the constraint. Every address is verified before it enters a campaign, and anything
that fails is dropped rather than sent — a bounce costs far more than a skipped lead.

---

## Conversational booking agent
*Make · OpenAI · Google Calendar*

Handles appointment scheduling, rescheduling and cancellation from natural-language requests.

```
webhook → router on intent (schedule | reschedule | cancel)
   → LLM: parse natural language into a date range
   → query free/busy for available slots
   → LLM: select and confirm a slot
   → router: available vs conflict
       ├─ create / update / delete calendar event
       └─ LLM: compose alternative offer
   → respond
```

Availability is computed from the real calendar, not from the model. The LLM handles language — "next
Tuesday afternoon", "sometime after the 15th" — and the calendar API remains the source of truth for
what is actually free.

---

## Stack

**Orchestration** n8n (150+ production workflows) · Make
**AI** OpenAI (chat, agents with memory and tools, image generation, TTS)
**Data** Supabase (Postgres, Storage, Edge Functions) · Google Sheets · Airtable
**Media** Transloadit
**Integrations** Google Calendar / Drive · Instagram · Facebook · LinkedIn · X · courier APIs · email
finding and verification · Instantly

---

## Repo layout

```
<workflow-folder>/
├── README.md      what it does and why it is built this way
├── workflow.json  sanitised export, importable into n8n or Make
└── canvas.png     screenshot of the graph
```

Imports need your own credentials and endpoints — every host, ID, key and webhook URL has been
replaced with a placeholder. See [SANITISING.md](SANITISING.md) for the full list and the script that
does it.
