# RulesBot — Planning Doc

Use this file to record your design decisions as you work through the lab.
There are no wrong answers — write enough that you could explain your reasoning to another group.

---

## Domain

Board game rule books are a domain where the knowledge exists but is hard to query. Rule books are written as sequential reference documents, not searchable Q&A databases. A player at game night who wants to know whether they can build a settlement adjacent to a city has to skim several pages — or argue about what "adjacent" means — without a way to ask the question directly. The same problem applies for Chess castling conditions, Scrabble scoring rules, or Pandemic win conditions.

RulesBot makes 10 loaded rule books queryable with plain-language questions: "What happens when you roll a 7?" "How does castling work?" "Can a player challenge a word in Scrabble?" This knowledge is publicly available but practically inaccessible mid-game in its original form.

---

## Documents

All documents are plain-text rule summaries stored in the `docs/` directory. Each covers components, setup, turn structure, special rules, and winning conditions. No HTML, no navigation text — clean plain text only.

| File | Game |
|------|------|
| `docs/catan.txt` | Catan |
| `docs/chess.txt` | Chess |
| `docs/clue.txt` | Clue (Cluedo) |
| `docs/codenames.txt` | Codenames |
| `docs/monopoly.txt` | Monopoly |
| `docs/pandemic.txt` | Pandemic |
| `docs/risk.txt` | Risk |
| `docs/scrabble.txt` | Scrabble |
| `docs/ticket_to_ride.txt` | Ticket to Ride |
| `docs/uno.txt` | Uno |

Total: 10 documents, 189 chunks after ingestion.

---

## Chunking Strategy

**Splitting approach:** Character-based sliding window. The document text is stepped through in fixed-size windows of `chunk_size` characters, advancing by `(chunk_size - overlap)` on each step so adjacent chunks share a small region of text at their boundary.

**Chunk size:** 300 characters. Rule book text is semantically dense — a single rule is typically 1–3 sentences, which fits comfortably in this range. Going smaller would fragment individual rules; going larger would merge unrelated rules into one chunk, making retrieval less precise.

**Overlap:** 50 characters between adjacent chunks. If a rule falls exactly on a chunk boundary, neither chunk alone contains the full rule. Overlap duplicates the tail of each chunk at the start of the next, so boundary-spanning content can still be retrieved intact. 50 characters is roughly one short sentence — enough to preserve context without significantly bloating the database.

**Minimum chunk length:** 50 characters. Chunks shorter than this are discarded. Very short segments typically contain only whitespace, section headers, or punctuation — content with no semantic signal that would add noise to the vector database. Because min_length equals overlap, any tail chunk too short to keep is already fully contained in the previous chunk's overlap region — so nothing is lost.

**Why this fits rule book text:** Rule books pack a lot of meaning into short passages, so smaller chunks outperform paragraph-level splitting for targeted Q&A. A 300-character window is typically one complete rule — the right retrieval unit for questions like "What happens when you roll a 7?" Paragraph splitting would work but produces uneven chunk sizes, since rule book paragraphs vary from one sentence to ten.

**Known limitation:** Character-based splitting is indifferent to sentence and paragraph boundaries. A chunk can begin mid-sentence. Numbered lists may get split in the middle of an item. A sentence-aware splitter would handle these edge cases better at the cost of implementation complexity.

---

## Retrieval Approach

**Embedding model:** `all-MiniLM-L6-v2` via sentence-transformers. Runs locally with no API key or rate limits. Maps text to 384-dimensional vectors with good performance on short to medium passages.

**Vector store:** ChromaDB (persistent, local). Cosine distance metric configured via `metadata={"hnsw:space": "cosine"}`. Ingestion runs once at startup; subsequent runs skip it if the collection is already populated (`./chroma_db` persists to disk).

**Top-k:** 3 results per query (default `N_RESULTS` in `config.py`). 3 is enough for well-specified questions that map to a single chunk. It is a known limitation for questions whose answer spans multiple chunks or whose relevant chunk ranks outside the top 3 — see Anticipated Challenges.

**Production tradeoffs:** If deploying this for real users with no cost constraint, the key considerations would be:

- *Accuracy vs. cost*: `text-embedding-3-large` (OpenAI) produces higher-quality embeddings but costs per token and requires a network call. `all-MiniLM-L6-v2` is free and local but weaker on domain-specific text.
- *Context length*: Larger embedding models support longer inputs, useful if chunks need to be wider.
- *Multilingual*: For documents in multiple languages, a multilingual model like `paraphrase-multilingual-MiniLM-L12-v2` would be needed.
- *Latency*: Local embedding (no network round-trip) is fast for a single-instance app; API embedding scales better under concurrent load.

---

## Evaluation Plan

Five test questions with specific, verifiable expected answers:

| # | Question | Expected Answer |
|---|----------|----------------|
| 1 | What happens when you roll a 7 in Catan? | No resources produced; players with >7 cards discard half (rounded down); the roller moves the robber and steals one card from an adjacent player. |
| 2 | How do you castle in Chess, and when is it not allowed? | King moves two squares toward the rook; rook moves to the square the king crossed. Not allowed if: either piece has moved before, pieces stand between them, the king is in check, or the king passes through or lands on an attacked square. |
| 3 | How does a Suggestion work in Clue? | Name a suspect, weapon, and the room you are currently in; move those pieces there; starting left, each player privately shows one matching card; the first player to show a card ends the process. |
| 4 | What is a bingo in Scrabble and how many bonus points does it give? | Using all 7 tiles from your rack in a single turn earns a 50-point bonus on top of the word score. |
| 5 | How do you win Pandemic? | Players win by discovering cures for all four diseases. Players lose if the player deck runs out, the 8th outbreak marker is placed, or any disease cube cannot be placed. |

---

## Anticipated Challenges

**1. Top-k too small to surface the right chunk.** With `n_results=3`, if the relevant chunk ranks 4th or 5th (because several topically related but non-specific chunks outrank it), the system fails silently. The LLM receives no usable context and refuses. The castling query turned out to be exactly this case: overview/movement chunks ranked 1st–3rd at distances 0.422–0.453, while the actual castling rule chunk ranked 4th at distance 0.512. Increasing `N_RESULTS` to 5 or 6 would fix most such cases, at the cost of a slightly larger context window.

**2. Chunk boundary splits cutting a rule in half.** A 300-character window can end mid-sentence, leaving a rule split across two chunks. With 50-character overlap, a rule longer than ~300 characters may not fit in a single retrievable unit. This could cause the LLM to receive incomplete context. The Pandemic win-condition query showed this: only the chunk containing "Either all players win" passed the distance filter; the chunk with the full loss-condition detail ranked outside top-3.

---

## AI Tool Plan

| Pipeline component | Input given to AI | What AI produced | What I changed |
|-------------------|------------------|-----------------|---------------|
| `chunk_document()` in `ingest.py` | Chunking Strategy section above + input/output contract from `chunk-document-spec.md` | Character-based sliding window with configurable `chunk_size`, `overlap`, and `min_length` | None — implementation matched spec exactly |
| `retrieve()` in `retriever.py` | `retrieve-spec.md` with query approach, return structure, nested-result handling, and edge cases filled in | ChromaDB `.query()` call with `[0]` index unpacking and `zip` over parallel lists | Added inline comment explaining the `[0]` index gotcha |
| `generate_response()` in `generator.py` | `generate-response-spec.md` with system prompt, fallback message, and distance filter sections filled in | Full implementation: `MAX_DISTANCE` filter, numbered source blocks, Groq API call with two-message structure | Lowered temperature from 0.2 to 0.1 for more deterministic grounding |

---

## Architecture

```
User Query
    │
    ▼
┌───────────────────────────────────────────┐
│  INGEST (startup only)                    │
│  ingest.py                                │
│  load_documents() — 10 plain .txt files   │
│  chunk_document() — 300-char sliding win  │
│  189 chunks total across 10 games         │
└──────────────────┬────────────────────────┘
                   │ list of chunk dicts
                   ▼
┌───────────────────────────────────────────┐
│  EMBED + STORE (startup only)             │
│  retriever.py: embed_and_store()          │
│  Embedding model: all-MiniLM-L6-v2        │
│  (sentence-transformers, runs locally)    │
│  Vector store: ChromaDB (persistent disk) │
│  Distance metric: cosine                  │
└───────────────────────────────────────────┘
                   │
          (per-query path below)
                   │
    User Query ───►│
                   ▼
┌───────────────────────────────────────────┐
│  RETRIEVE                                 │
│  retriever.py: retrieve()                 │
│  Embeds query with all-MiniLM-L6-v2       │
│  Returns top-3 chunks, ranked by dist     │
└──────────────────┬────────────────────────┘
                   │ ranked chunks + distance scores
                   ▼
┌───────────────────────────────────────────┐
│  GENERATE                                 │
│  generator.py: generate_response()        │
│  Filter: drop chunks with dist > 0.55     │
│  LLM: Groq llama-3.3-70b-versatile        │
│  Grounding: strict system prompt          │
│  Citation: game name in every response    │
└──────────────────┬────────────────────────┘
                   │ grounded answer string
                   ▼
┌───────────────────────────────────────────┐
│  UI                                       │
│  app.py: Gradio ChatInterface             │
│  http://localhost:7860                    │
└───────────────────────────────────────────┘
```

---

## Retrieval Observations

After implementing retrieval, test queries and results:

| Query | Top result game | Does it make sense? |
|-------|----------------|---------------------|
| "How do you win?" | Monopoly (0.507), Risk (0.509), Ticket to Ride (0.522) | Yes — game-agnostic query legitimately returns winning conditions from multiple games |
| "What happens when you roll a 7?" | Catan (0.461) | Yes — top chunk contains the complete ROLLING A 7 rule |
| "Can two players share a route?" | Ticket To Ride (0.390) | Yes — route-claiming rule retrieved correctly |

**Anything surprising?**

Two things. First, distances are much higher than textbook examples — a perfect hit scores ~0.46, not ~0.14. The threshold for "relevant" with this model is ~0.55, not ~0.2. Second, the bare query "What happens when you roll a 7?" pulled Risk dice-rolling rules into slots 2 and 3 (~0.60), because "roll" and "dice" overlap semantically with Risk combat. Adding "in Catan" to the query made all three results Catan. The lesson: under-specified queries produce cross-game contamination; that's a query formulation issue, not a retrieval bug.

---

## Response Quality

After implementing generation, test questions and assessments:

| Query | Answer accurate? | Properly grounded? | Cited the right game? |
|-------|-----------------|-------------------|----------------------|
| "What happens when you roll a 7 in Catan?" | Yes | Yes — every claim traceable to retrieved chunk | Yes — opened with "In Catan, ..." |
| "How do you get out of Jail in Monopoly?" | Yes | Yes — $50, doubles, Get Out of Jail Free all from chunk | Yes — "In Monopoly, ..." |
| "What is offside in soccer?" | N/A — refused | Yes — correctly declined | N/A |

**What would you change about the prompt to improve grounding?**

The v2 system prompt already handles the main failure modes (partial blending, wrong-game, memory-vs-excerpt conflict, helpful elaboration). The remaining gap is that the prompt can't compensate for retrieval returning the wrong chunks — grounding only works if the right text is in context. The higher-leverage fix for cases like the castling failure is increasing `N_RESULTS` from 3 to 5–6 so relevant chunks ranked 4th or 5th can reach the LLM.
