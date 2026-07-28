# AI Automation Workflows

Eleven automation pipelines I've built and run — LLM orchestration, media generation, data enrichment
and multi-system integration across n8n and Make.

These aren't demos. Each one runs on a schedule or a webhook and does real work: generating the
content behind two published mobile apps, booking couriers for my own e-commerce business, running
outreach campaigns, taking appointment calls for a dental clinic.

Every export here is sanitised — see [SANITISING.md](SANITISING.md).

| # | Workflow | Platform | AI |
|---|---|---|---|
| [01](01-audiobook-generation) | Audiobook generation | n8n | gpt-4o · ElevenLabs |
| [02](02-meal-plan-onboarding) | Meal plan onboarding | n8n | gpt-5.1 agent |
| [03](03-meal-photo-analysis) | Meal photo analysis | n8n | Gemini 2.5 Pro |
| [04](04-social-publishing) | Multi-channel social publishing | Make | gpt-4o · DALL·E 3 |
| [05](05-ecommerce-shipping) | E-commerce shipping | Make | gpt-4o |
| [06](06-lead-generation) | Lead generation and outreach | n8n | LLM agents |
| [07](07-voice-appointment-agent) | Voice appointment agent | Make | gpt-4o |
| [08](08-video-generation) | Video generation | Make | fal.ai · Leonardo.AI · RunwayML |
| [09](09-video-feedback) | Video review feedback | n8n | — |
| [10](10-daily-puzzle) | Daily puzzle generation | n8n | OpenAI agent |
| [11](11-maps-lead-scraper) | Maps lead scraper | n8n | — |

## Why these eleven

There are over 150 workflows in my n8n instance, plus Make scenarios. Eleven are in this repo.

They were picked because each one solves a *different* problem, not because they were the largest:

- map-reduce summarisation past a context limit
- polling an async job instead of holding a worker open, across three vendors in one chain
- an agent constrained by numbers computed in code before it runs
- strict structured output from a vision model
- **validating model output and repairing it automatically, with a bounded retry**
- fuzzy normalisation of messy human input
- fan-out to platforms with incompatible media handling
- **cursor pagination with the cursor persisted outside the run**
- **multimodal capture — image, annotation and audio — as one payload**
- a voice interface where the model is never the source of truth

A folder of 150 near-identical CRUD flows would demonstrate less than these eleven do.

---

**Models are chosen per task, not per vendor.** Gemini 2.5 Pro does the meal-photo vision work because
it handles strict JSON-only output well under a long constraint prompt; gpt-5.1 drives the meal-plan
agent where reasoning over constraints matters; gpt-4o handles the high-volume, low-latency
classification and copy jobs. Three providers across seven workflows is a deliberate result of that.

---

## 01 · Audiobook generation
*n8n · gpt-4o · ElevenLabs · PDF.co · Transloadit · Supabase · 31 nodes*

PDF in, narrated audio summary out, triggered by webhook.

```
PDF upload → PDF.co: extract + paginate → chunk
   → map:    summarise each chunk       (gpt-4o)
   → reduce: single coherent summary    (gpt-4o)
   → clean + segment text
   → loop:   synthesise each segment    (ElevenLabs)
             upload to Supabase Storage
   → aggregate segment URLs
   → Transloadit assembly: concatenate into one track
   → GET assembly → Wait → Switch: poll until complete
   → write the public URL back to the database
   → respond to the webhook
```

*Context limits.* A book does not fit in a context window, so summarisation is map-reduce — summarise
chunks independently, then reduce those summaries into one narrative. Chunks are cut on page
structure rather than token count, so sections aren't split mid-argument.

*Speech synthesis is fragmented.* TTS runs per segment and yields many audio files that must become
one track. Transloadit does the concatenation as an async assembly, so the flow submits the job and
then polls it with an explicit `GET Assembly → Wait → Switch` loop rather than holding a worker open
for the duration. That polling loop is the part worth reading.

## 02 · Meal plan onboarding
*n8n · gpt-5.1 agent with memory and tools · Supabase · 13 nodes*

```
webhook → Mathematical Calculation (BMR / TDEE / macro split)
   → Meal Plan agent, conditioned on those targets
   → Parse Meal Plan → Get a row → Existence of User
   → Switch: create row if absent, update if present
   → respond
```

**The deterministic maths runs before the model, not inside it.** BMR, TDEE and the macro split are
computed in code, and the agent is handed those numbers as constraints to compose meals against. Ask
a language model to do arithmetic on a user's body metrics and it will occasionally be confidently
wrong, in a health context, silently. Ask it to build a menu hitting numbers you already calculated
and the failure mode is a boring meal, not a bad calorie target.

Powers **[CalTrack](https://play.google.com/store/apps/details?id=com.pet.caltrack)** on Google Play.

## 03 · Meal photo analysis
*n8n · Google Gemini 2.5 Pro · Supabase · 8 nodes*

```
webhook (image) → Supabase Storage → public URL
   → Gemini 2.5 Pro: analyse image
   → parse to required format → write row → respond to app
```

The prompt does the heavy lifting: it first decides whether the image contains edible food at all,
then itemises what it sees with per-item calories and macros, and is constrained to emit raw JSON
with no markdown, code fences or prose. A vision model that returns a chatty paragraph breaks the
client; the app is only ever handed a parsed row.

Also powers CalTrack.

## 04 · Multi-channel social publishing
*Make · gpt-4o · DALL·E 3 · Google Sheets · Supabase Storage · 12 modules*

```
scheduled sheet read → aggregate into batch → transform to JSON
   → gpt-4o: post copy
   → gpt-4o: supporting angle / benefit line
   → write back to the sheet (audit trail)
   → DALL·E 3 image → upload to Supabase Storage → public URL
   → router → Instagram · Facebook · LinkedIn · X
```

Each platform handles media differently, so the router branches per destination instead of pretending
one payload fits all. Generated copy and imagery are persisted before publishing, so a failed post is
retried from stored assets rather than regenerated — which matters when regeneration costs money and
produces something different.

## 05 · E-commerce shipping
*Make · gpt-4o · TCS courier API · Supabase · Google Drive · 34 redactions to publish*

Running in production for my own business. Watches for orders and books couriers automatically.

```
Supabase order event → set shipping city → CODE CITIES lookup
   → gpt-4o: resolve free-text city to a courier city code
   → router: COD vs EasyPaisa
       └─ router: order value band
           → TCS booking → write tracking number back
           → fetch consignment label → archive to Drive
```

**Why a model for city codes.** Customers type "Karachi", "karachi.", "KHI", "Karachi Sindh". The
courier API wants an exact code. It is fuzzy normalisation over messy human input with a long tail —
a lookup table caught the common cases and failed constantly on the rest, and every failure was a
shipment that didn't book.

Two routers nest to give four leaf paths, one per payment-method and value-band combination, each
with its own booking rules.

## 06 · Lead generation and outreach
*n8n · LLM agents · AnyMailFinder · Instantly · 10 nodes*

```
read prospect sheet → filter → loop per prospect
   → agent: normalise name into first / last
   → AnyMailFinder → success / error branch
   → Check Valid Email → discard unverifiable
   → agent: write a personalised icebreaker
   → push to Instantly campaign
```

Deliverability is the whole constraint. Every address is verified before it enters a campaign and
anything unverifiable is dropped rather than sent — one bounce costs more than a hundred skipped
leads, because it damages the sending domain for everything after it.

## 07 · Voice appointment agent
*Make · gpt-4o · Cal.com · Google Calendar*

A voice agent that takes appointment calls for a dental clinic. Speech is handled upstream by VAPI,
which posts the transcribed request to a webhook.

```
VAPI webhook → router on intent (schedule | reschedule | cancel)
   → gpt-4o: parse natural language into a date range
   → Cal.com: find available slots
   → gpt-4o: check and pick a slot
   → router: available vs conflict
       ├─ Google Calendar: create / update / delete the event
       └─ gpt-4o: compose an alternative offer
   → respond to the caller
```

**Availability is never hallucinated.** The model parses language — "next Tuesday afternoon",
"sometime after the 15th" — and composes the reply, but every claim about what is free comes from a
real Cal.com slot query, and the booking itself is a Google Calendar write. The model is the
interface, not the source of truth. That separation is the entire design.

## 08 · Video generation
*Make · fal.ai FLUX realism · Leonardo.AI · RunwayML Gen-3 Turbo*

```
prompt → fal.ai flux-realism (1280x720, 35 steps)
   → sleep → GET status_url → GET request → download the still
   → Leonardo.AI: upload as init image
   → Leonardo.AI: universal upscaler, 2x, realistic
   → RunwayML image_to_video (gen3a_turbo, 5s, 1280x768)
   → sleep → GET task
```

Three vendors, three independent job queues, one chain. Each stage submits work and comes back for it
later, because none of them return a finished asset synchronously.

**Where this one is weaker than 01, and why that matters.** The audiobook pipeline polls properly, with
a `GET → Wait → Switch` loop that keeps checking until the assembly reports complete. This scenario
uses fixed sleeps instead — 20 seconds for the image, 60 for the video — and checks once. That works
until a vendor is slow, and then it fails for no visible reason. Same problem, two solutions, and only
one of them is correct; the audiobook version is the one I'd copy forward.

## 09 · Video review feedback
*n8n · webhook · base64 media handling*

A reviewer pauses a video, draws on the frame, records a voice note, types a comment, and submits.
Instead of "something looks off around 2 minutes" in a doc, the editor receives the exact frame, the
annotated version, the audio and the note, tied to a timestamp.

```
webhook → extract fields + presence flags
   → strip base64 data-URI prefixes
   → build binary attachments for whichever media are present
   → deliver: original frame, annotated frame, voice note, summary
```

**Two details do the work here.** Browser-captured media arrives as a data URI —
`data:image/png;base64,iVBOR...` — and the prefix has to come off before the payload is a valid
buffer; miss it and you get a corrupt file rather than an error. And all three media types are
optional, so attachments are constructed conditionally from presence flags rather than assumed, which
is why a comment-only submission doesn't fail.

Delivery currently goes to a chat transport, which is honest prototype scaffolding rather than the
product — the capture and packaging is the part that took the thinking.

## 10 · Daily puzzle generation
*n8n · OpenAI agent · Supabase*

One solvable puzzle per day, generated rather than authored.

```
select puzzle type → read recent puzzles → build prompt with that history
   → agent generates → parse JSON → validate the logic
   → valid?   yes → save
              no  → repair in code → validate again
                    still no → regeneration attempt (bounded) → else alert
```

**The generation is the easy half.** What makes this worth reading is everything after it: the puzzle
is checked for logical validity, and when it fails the workflow first tries to *repair* it in code,
then re-validates, then falls back to a bounded regeneration attempt, and only alerts a human once it
has genuinely run out of options. A model that is right most of the time is not good enough when the
output ships to users unattended, and "ask it again" is not an error-handling strategy.

Recent puzzles are fed back into the prompt so the same puzzle isn't generated twice.

## 11 · Maps lead scraper
*n8n · Google Geocoding + Places · Google Sheets · n8n data table*

Finds businesses by category and area, writes name, address, phone and website to a sheet.

```
parameters (query, address, radius, max) → geocode the address
   → Places searchText, biased to a circle on those coordinates
   → split → append rows → save nextPageToken to a data table
   → cursor empty?  yes → stop
                    no  → wait → reload cursor → next page → repeat
   → also stop once the row count reaches the requested maximum
```

**The pagination is the whole exercise.** Places returns a `nextPageToken` and the obvious approach —
hold it in a variable and loop — breaks the moment an execution ends. Here the cursor is written to an
n8n data table, so it outlives the run and the next execution resumes exactly where the last one
stopped. There are also two independent stop conditions: the cursor running out, and the collected
count reaching the requested maximum. Either one alone eventually costs you money or an infinite loop.

---

## Stack

**Orchestration** n8n · Make
**AI** OpenAI gpt-5.1, gpt-4o, DALL·E 3 · Google Gemini 2.5 Pro · ElevenLabs · fal.ai FLUX ·
Leonardo.AI · RunwayML Gen-3
**Data** Supabase (Postgres, Storage, Edge Functions) · Google Sheets · n8n data tables
**Documents & media** PDF.co · Transloadit · base64 / binary handling
**Integrations** Google Geocoding + Places · Google Calendar · Google Drive · Cal.com · VAPI ·
TCS courier API · AnyMailFinder · Instantly · Instagram · Facebook · LinkedIn · X

## Repo layout

```
<workflow-folder>/
├── README.md      what it does and why it is built this way
├── workflow.json  sanitised export
└── canvas.png     screenshot of the graph
```

Imports need your own credentials and endpoints — 162 values across the eleven exports were replaced
with placeholders. [SANITISING.md](SANITISING.md) documents what, and the script that does it.
