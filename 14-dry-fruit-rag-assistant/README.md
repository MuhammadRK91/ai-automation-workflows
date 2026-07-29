# Multilingual RAG assistant for a dry fruit retailer

*Voiceflow · gpt-4o · Airtable · Zendesk · Google Maps*

A customer-facing assistant for a dry fruit retail business. It answers product questions from the shop's own catalogue, searches the live product table, raises support tickets, and shows the shop on a map. Multilingual, with voice input and output enabled alongside text.

Built for a client. Demo video is on [LinkedIn](https://www.linkedin.com/feed/update/urn:li:activity:7369704798637555713).

## Retrieval is a pipeline, not a lookup

The part worth reading. A question does not go straight at the knowledge base.

```
user question
  → Ask Clarifying Question   rewrite the query for retrieval, ask the user
                              only when the ambiguity actually blocks an answer
  → kb-search                 retrieve the top 2 chunks from the catalogue
  → Reduce Hallucinations     answer strictly from retrieved context,
                              fall through when the context does not support one
  → answer
```

**Why the rewrite step exists.** People ask "is the small one cheaper", which retrieves nothing useful on its own. Rewriting it against conversation state into something self-contained is what makes retrieval land. The rewrite runs before every search, and the clarifying question is only put to the user when the rewrite cannot resolve the ambiguity alone. Asking on every turn destroys the conversation.

**`maxChunks` is 2, deliberately.** A product catalogue is dense and repetitive. Widening the window pulls in near-identical entries for other products and the model starts blending them, quoting the weight of one item with the price of another. Two chunks keeps the answer traceable to a single product.

**The grounding step has a real exit.** When retrieved context does not support an answer, the flow falls through to an explicit path rather than letting the model improvise. For a shop, an invented price or origin claim is a customer complaint, not a bad demo.

## The rest of it

| Flow | What it does |
|---|---|
| Knowledge Base | The retrieval pipeline above, over the shop's catalogue |
| Shop Products | Product browse and search, 257 nodes, carousels and product cards, backed by an Airtable search function |
| Submit Ticket | Creates a Zendesk ticket from the conversation, with the details captured in-flow |
| Contact us | Captures and validates contact details |
| Google_maps | Returns the shop location |

**Intent classification runs on gpt-4o at temperature 0.1**, over 9 intents and 121 training utterances, rather than on keyword matching. Customers do not use the shop's vocabulary, and they do not all ask in English. 106 variables carry conversation state across the flows.

**Product facts come from Airtable, not from the model.** The search function queries a named column and returns matching rows, so price and stock are read from the table at answer time. The knowledge base handles descriptive questions; the table handles anything a customer could hold you to.

## Why Voiceflow, and why no export here

Voiceflow was the right tool for the client: they needed to see and adjust conversation copy themselves without a deploy, and the widget, voice input and multilingual handling came for free. The engineering that mattered went into the retrieval design, the Airtable and Zendesk integrations, and the intent model.

The `.vf` export is not published in this repo. It is a 1.15 MB machine-generated blob with no readable diff, it carries workspace identifiers, and it still contains unused agents from the platform's starter templates. None of that tells a reader anything the description above does not. The design is the part worth publishing.

No credentials appear in this folder because no export appears in it.
