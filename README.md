# RulesBot

> A board game rules assistant — because "just read the rulebook" isn't always helpful at 11pm on game night.

RulesBot answers natural language questions about board game rules using a RAG (Retrieval-Augmented Generation) pipeline. Ask it anything about the loaded games: it retrieves the relevant rule passages and generates an answer grounded in the actual rulebook text, with a citation so you can verify it.

---

## Getting Started

### 1. Fork and clone

Fork this repo, then clone your fork locally.

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Mac/Linux
# or: .venv\Scripts\activate   # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `sentence-transformers` will download the embedding model (~80MB) on first run. This only happens once — it's cached locally afterward.

### 4. Add your Groq API key

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder value with your key from [console.groq.com](https://console.groq.com). No credit card required.

### 5. Run the app

```bash
python app.py
```

RulesBot will ingest the rule books, open the Gradio interface, and be ready to answer questions at `http://localhost:7860`.

---

## Domain and Document Sources

**Domain:** Board game rule books — structured reference documents that are comprehensive but hard to query mid-game. A player asking "can I build adjacent to another player's city?" has to skim several pages without a direct way to pose the question. RulesBot makes the rules conversationally searchable.

**What the system can answer:** Specific rules questions about any of the 10 loaded games — setup, turn structure, special mechanics, winning conditions, and edge cases.

**Document sources** (10 plain-text rule summaries in `docs/`):

| File | Game | Content |
|------|------|---------|
| `docs/catan.txt` | Catan | Setup, resource production, building, trading, robber, win condition |
| `docs/chess.txt` | Chess | Piece movement, special moves (castling, en passant, promotion), check/checkmate/draw |
| `docs/clue.txt` | Clue (Cluedo) | Setup, movement, suggestions, deduction, accusations, win condition |
| `docs/codenames.txt` | Codenames | Setup, spymaster clues, guessing, assassin, win condition |
| `docs/monopoly.txt` | Monopoly | Setup, buying/mortgaging, houses/hotels, jail, taxes, win condition |
| `docs/pandemic.txt` | Pandemic | Setup, player roles, actions, infection, outbreaks, win/lose conditions |
| `docs/risk.txt` | Risk | Setup, troop placement, attacking, fortifying, cards, win condition |
| `docs/scrabble.txt` | Scrabble | Setup, tile values, premium squares, scoring, bingo, challenges, end game |
| `docs/ticket_to_ride.txt` | Ticket to Ride | Setup, route claiming, destination tickets, scoring, win condition |
| `docs/uno.txt` | Uno | Setup, card types, action cards, Draw Four legality, win condition |

---

## Chunking Strategy and Reasoning

**Strategy:** Character-based sliding window with overlap.

**Parameters:**
- Chunk size: **300 characters**
- Overlap: **50 characters**
- Minimum chunk length: **50 characters** (shorter chunks discarded)

**Why these numbers fit rule book text:**

Rule book text is semantically dense — a single rule typically fits in 1–3 sentences, which maps to roughly 150–350 characters. A 300-character window captures one complete rule in most cases, which is exactly the unit of retrieval needed for targeted Q&A ("What happens when you roll a 7?" should return the rolling-a-7 rule, not a page about Catan's economy).

The 50-character overlap prevents a rule that lands on a chunk boundary from becoming unretrievable — the tail of each chunk appears at the head of the next, so a sentence split across two chunks can still be matched to a query.

The 50-character minimum discards section headers, whitespace artifacts, and very short tail segments that carry no semantic content. Because minimum length equals overlap, any discarded tail chunk is already fully contained in the previous chunk's overlap region — no information is lost.

**Result:** 189 total chunks across 10 documents, averaging 18.9 chunks per game (range: 16–23). Chunk counts are deterministic — re-ingesting the same documents produces exactly 189 every time.

**Known limitation:** Character-based splitting is indifferent to sentence boundaries. Some chunks start mid-sentence (e.g., a Catan chunk begins `"ding cost cards, 2 special cards..."`). In practice, this has little impact on retrieval quality because the embedding model captures semantic meaning even from clipped text — but a sentence-aware splitter would produce cleaner chunks.

---

## Sample Chunks

Five representative chunks from the ingested documents, illustrating the 300-character sliding window:

**Chunk 1 — Catan (`catan_6`)**
```
x, that hex produces no resources that turn, regardless of the number rolled.

ROLLING A 7
When a 7 is rolled, no resources are produced. Every player with more than 7 resource cards in hand must discard half (rounded down). The player who rolled moves the robber to any terrain hex and steals one ra
```

**Chunk 2 — Chess (`chess_11`)**
```
r previously moved. The king moves two squares toward the rook, and the rook moves to the square the king crossed. Conditions: neither the king nor the rook involved have moved previously this game; no pieces stand between them; the king is not currently in check; the king does not pass through or l
```

**Chunk 3 — Scrabble (`scrabble_16`)**
```
n a single turn, they score a 50-point bonus (called a bingo) in addition to the word score. This 50-point bonus is added after all other premium multipliers are applied.

CHALLENGING A WORD
If a player believes an opponent's word is invalid, they may challenge it before the next player takes their
```

**Chunk 4 — Clue (`clue_8`)**
```
pace. Secret passages in the corners of the board allow you to move directly to the diagonally opposite corner room without rolling.

MAKING A SUGGESTION
When you are in a room, you may make a Suggestion — a claim about the murder: one suspect, one weapon, and the room you are currently in (you cann
```

**Chunk 5 — Pandemic (`pandemic_10`)**
```
player.
Discover a Cure: At a research station, discard 5 city cards of the same color to cure that disease. Place the cure marker on the board. If all cubes of that color have already been removed, the disease is eradicated.

DRAWING PLAYER CARDS
After taking actions, draw 2 cards from the player
```

Notice the ragged starts and truncated ends — the character splitter is indifferent to sentence boundaries. Despite this, the embedding model still matches these chunks correctly to relevant queries because semantic meaning survives a clipped first or last word.

---

## Embedding Model

**Model used:** `all-MiniLM-L6-v2` (sentence-transformers)

Maps text to 384-dimensional vectors. Runs entirely locally — no API key, no rate limits, no network calls. Cached after first download (~80MB).

**Tradeoffs for a production deployment:**

| Factor | all-MiniLM-L6-v2 (this project) | OpenAI text-embedding-3-large |
|--------|----------------------------------|-------------------------------|
| Cost | Free (local) | Per-token API cost |
| Latency | Fast (no network) | Network round-trip per request |
| Accuracy | Good for general short text | Higher accuracy, larger context |
| Context length | ~256 tokens max | 8191 tokens |
| Multilingual | English-focused | Strong multilingual support |
| Offline use | Yes | No (requires API) |

For a production system serving real users, `text-embedding-3-large` would give meaningfully better retrieval accuracy — especially for longer chunks and domain-specific terminology. For a local, cost-free prototype like this, `all-MiniLM-L6-v2` is the right tradeoff. A multilingual corpus would require a different model entirely (`paraphrase-multilingual-MiniLM-L12-v2` or similar).

One critical calibration note: cosine distances for `all-MiniLM-L6-v2` do not approach 0 even for exact-match retrieval. Correct hits for this model measure ~0.34–0.47; weak matches start around 0.55+. The standard textbook "0.1–0.2 = relevant" threshold would reject every correct answer — the `MAX_DISTANCE` constant in `generator.py` is set to 0.55 based on empirical calibration against this model's actual distribution.

---

## Retrieval Test Results

Three queries tested against the vector store after ingestion (top-3 results shown):

### Query 1: "What happens when you roll a 7 in Catan?"

| Rank | Game | Distance | Chunk excerpt |
|------|------|----------|---------------|
| 1 | Catan | 0.461 | `"...ROLLING A 7\nWhen a 7 is rolled, no resources are produced. Every player with more than 7 resource cards..."` |
| 2 | Catan | 0.524 | `"CATAN — OFFICIAL RULES SUMMARY\n\nOVERVIEW\nCatan is a strategy board game for 3–4 players..."` |
| 3 | Scrabble | 0.587 | `"...draw the same number from the bag, then shuffle the returned tiles back into the bag..."` |

**Why the top result is relevant:** The #1 chunk contains the exact "ROLLING A 7" section header and the complete rule: no resources, discard half if over 7, move robber and steal. It's the right rule from the right game. The #2 chunk is the Catan title/overview — on-topic but not specific. The #3 Scrabble chunk (0.587) is noise; it passes `N_RESULTS=3` but would be filtered out by the `MAX_DISTANCE=0.55` gate in generation.

---

### Query 2: "How do you castle in Chess, and when is it not allowed?"

| Rank | Game | Distance | Chunk excerpt |
|------|------|----------|---------------|
| 1 | Chess | 0.422 | `"CHESS — OFFICIAL RULES SUMMARY\n\nOVERVIEW\nChess is a two-player strategy board game..."` |
| 2 | Chess | 0.446 | `"...nally). The king may never move to a square that is attacked by an opponent's piece..."` |
| 3 | Chess | 0.453 | `"opponent's king — to place it under attack with no legal escape. White always moves first..."` |

**Why retrieval fails here:** All three results are Chess (correct game), but all three are overview/movement chunks — none contains the castling rule. The actual castling chunk (`chess_11`) ranks 6th at distance 0.540. With `N_RESULTS=3`, the castling chunk is never retrieved. The LLM correctly refuses ("the provided rules don't cover that") because it has no castling text in context — this is a retrieval depth failure, documented as a failure case below.

---

### Query 3: "How does a Suggestion work in Clue?"

| Rank | Game | Distance | Chunk excerpt |
|------|------|----------|---------------|
| 1 | Clue | 0.439 | `"CLUE (CLUEDO) — OFFICIAL RULES SUMMARY\n\nOVERVIEW\nClue (known as Cluedo outside North America)..."` |
| 2 | Clue | 0.453 | `"one card from their hand that matches any element of your suggestion (suspect, weapon, or room)..."` |
| 3 | Codenames | 0.457 | `"...followed by a number. The word hints at the meaning of one or more codenames the Spymaster..."` |

The #2 chunk contains the disproval mechanic. The Codenames chunk at rank 3 (0.457) is cross-game noise — "suggestion/hint" language in Codenames overlaps semantically with Clue "suggestions." It passes the distance filter; the system prompt's grounding instruction prevents the LLM from folding Codenames content into its Clue answer.

---

## Grounded Generation

Grounding is enforced in two layers:

**Layer 1 — Distance filter (deterministic):** Before calling the LLM, `generate_response()` drops any chunk with `distance > MAX_DISTANCE` (0.55). If no chunks survive, the system returns a fixed fallback message without ever calling the LLM. For out-of-corpus queries like "What is offside in soccer?", all chunks scored 0.695–0.705 — all filtered, LLM never called, refusal guaranteed.

**Layer 2 — System prompt (instruction-based):** The LLM is given a strict system prompt that:
- Names the retrieved excerpts as the only allowed source of truth
- Explicitly forbids using prior knowledge about the games, even when confident
- Instructs the model to follow the excerpt if its own knowledge conflicts
- Requires every statement to be supported by the excerpts
- Pre-authorizes "I don't have enough information" as a preferred correct answer
- Mandates citing the game name (from the `[Source N — GAME]` label) in every response

The two layers guard different failure modes: the distance filter eliminates clearly off-topic chunks cheaply; the system prompt handles the harder case of a chunk that passes the distance threshold but doesn't actually contain the answer to this specific question.

The full system prompt text is in `generator.py` at the `SYSTEM_PROMPT` constant.

---

## Example Responses

### Response 1 — Grounded, source cited

**Query:** "What happens when you roll a 7 in Catan?"

**RulesBot:** "In Catan, when a 7 is rolled, no resources are produced. Every player with more than 7 resource cards in hand must discard half (rounded down). The player who rolled moves the robber to any terrain hex and steals one resource."

*Grounding check:* Every claim ($7 threshold, discard half rounded down, move robber, steal one resource) is a direct paraphrase of the retrieved chunk. The response could not have come from general knowledge — it inherits the chunk's specific "rounded down" wording.

---

### Response 2 — Grounded, source cited

**Query:** "What is a bingo in Scrabble and how many bonus points does it give?"

**RulesBot:** "In Scrabble, a bingo is when a player uses all 7 tiles from their rack in a single turn, and it gives a 50-point bonus."

*Grounding check:* The top retrieved chunk (distance 0.234 — the strongest hit in any test) contains the exact sentence "they score a 50-point bonus (called a bingo)." The response is a near-verbatim paraphrase with no additions from memory.

---

### Response 3 — Out-of-scope refusal

**Query:** "What is offside in soccer?"

**RulesBot:** "I couldn't find an answer to that in the loaded rule books (Catan, Chess, Clue, Codenames, Monopoly, Pandemic, Risk, Scrabble, Ticket to Ride, and Uno). The rules I have don't appear to cover it. Try rephrasing your question, or name the specific game you're asking about."

*Why this is correct:* All three retrieved chunks scored 0.695–0.705, well above `MAX_DISTANCE=0.55`. The filter caught them all; the LLM was never called. This is the right behavior — a confident improvised answer about soccer offside would be a grounding failure.

---

## Query Interface

**Interface type:** Gradio ChatInterface (`app.py`), accessible at `http://localhost:7860` after running `python app.py`.

**Input field:** A text box labeled with a placeholder example ("Can I build a road through someone else's settlement?"). Press Enter or click the Submit button to query.

**Output field:** A chat-style response panel. The response opens by naming the source game ("In Catan, ...") and answers using only retrieved rule text. If no relevant rules are found, a fallback message names all loaded games and suggests rephrasing.

**Sidebar:** Lists all 10 loaded rule books with game icons.

**Example queries** are pre-loaded in the UI for one-click testing.

### Sample Interaction Transcript

```
User:    How do you get out of Jail in Monopoly?

RulesBot: In Monopoly, to get out of Jail, you can:
          1. Pay a $50 fine before rolling on any of your next three turns.
          2. Use a Get Out of Jail Free card (from Chance or Community Chest, 
             or purchased from another player).
          3. Roll doubles on any of your three turns in Jail.
          If you fail to roll doubles after three turns, you must pay the $50 fine
          and move the number shown on the dice.
```

---

## Evaluation Report

System tested on all 5 planned questions. Ground-truth answers were written before running the system.

### Q1 — What happens when you roll a 7 in Catan?

**Expected:** No resources produced; players with >7 cards discard half (rounded down); roller moves the robber and steals one card from an adjacent player.

**System response:** "In Catan, when a 7 is rolled, no resources are produced. Every player with more than 7 resource cards in hand must discard half (rounded down). The player who rolled moves the robber to any terrain hex and steals one resource."

**Retrieved chunks:** Catan 0.461 (ROLLING A 7 section), Catan 0.524 (overview), Scrabble 0.587 (filtered out).

**Accuracy: Accurate.** All three elements of the expected answer are present. The "rounded down" qualifier appears in the response, confirming it came from the retrieved text rather than general knowledge.

---

### Q2 — How do you castle in Chess, and when is it not allowed?

**Expected:** King moves two squares toward the rook; rook moves to the square the king crossed. Not allowed if either piece has moved, pieces stand between them, king is in check, or king passes through/lands on an attacked square.

**System response:** "The provided rules don't cover that."

**Retrieved chunks:** Chess 0.422 (overview), Chess 0.446 (king movement), Chess 0.453 (overview) — all passed the distance filter; none contained the castling rule.

**Accuracy: Inaccurate.** See failure case below.

---

### Q3 — How does a Suggestion work in Clue?

**Expected:** Name a suspect, weapon, and the room you are currently in; move those pieces there; starting left, each player privately shows one matching card; first to show ends the process.

**System response:** "In Clue, a Suggestion works by a player making a suggestion about the crime, and then other players can show 'one card from their hand that matches any element of your suggestion (suspect, weapon, or room) — if they have one.' The suggestion process ends as soon as one player shows a matching card."

**Retrieved chunks:** Clue 0.439 (overview), Clue 0.453 (disproval mechanic), Codenames 0.457 (Codenames spymaster — grounding prompt prevented cross-contamination).

**Accuracy: Partially accurate.** The disproval mechanic (show one matching card, first to show ends the process) is correct. Missing: the constraint that the named room must be your current room, and that the named suspect/weapon tokens are physically moved into that room. Both details are in the document but split across chunks that didn't rank in the top 2.

---

### Q4 — What is a bingo in Scrabble and how many bonus points does it give?

**Expected:** Using all 7 tiles from your rack in a single turn earns a 50-point bonus on top of the word score.

**System response:** "In Scrabble, a bingo is when a player uses all 7 tiles from their rack in a single turn, and it gives a 50-point bonus."

**Retrieved chunks:** Scrabble 0.234 (bingo rule — strongest hit in all tests), Scrabble 0.411, Scrabble 0.474.

**Accuracy: Accurate.** Complete and correct. The 0.234 distance score shows this is the most precise retrieval match in the evaluation set.

---

### Q5 — How do you win Pandemic?

**Expected:** Players win by discovering cures for all four diseases. Players lose if the player deck runs out, the 8th outbreak marker is placed, or any disease cube cannot be placed.

**System response:** "In Pandemic, the rules provided do not fully cover how to win the game, only stating that 'Either all players win' without specifying the conditions for winning."

**Retrieved chunks:** Pandemic 0.292 (passed filter), Pandemic 0.571 (filtered), Pandemic 0.586 (filtered).

**Accuracy: Partially accurate.** The system correctly identified that the retrieved chunk was incomplete — the chunk containing "Either all players win" is a partial sentence from a longer passage. The full win/loss conditions are in the Pandemic document, but the relevant chunk (describing curing all four diseases) ranked outside the top 3. The system's honest admission of incompleteness is the correct behavior given what it received.

---

### Summary

| # | Question | Accuracy |
|---|----------|----------|
| 1 | Roll a 7 in Catan | Accurate ✅ |
| 2 | Castling in Chess | Inaccurate ❌ |
| 3 | Suggestion in Clue | Partially accurate ⚠️ |
| 4 | Bingo in Scrabble | Accurate ✅ |
| 5 | Win Pandemic | Partially accurate ⚠️ |

2/5 accurate, 2/5 partially accurate, 1/5 inaccurate.

---

## Failure Case

**Question:** "How do you castle in Chess, and when is it not allowed?"
**Expected behavior:** Describe the castling move and enumerate the four conditions that prevent it.
**Actual behavior:** "The provided rules don't cover that." (complete refusal)

**Why it failed — retrieval depth.**

The castling rule is in the database. Chunk `chess_11` contains the full castling description: "The king moves two squares toward the rook, and the rook moves to the square the king crossed. Conditions: neither the king nor the rook involved have moved previously..." This chunk exists and is correct. Its distance from the castling query is **0.540**.

The problem is `N_RESULTS=3`. The top-3 results are all Chess chunks (correct game), but they are the overview, king-movement, and title chunks, at distances 0.422, 0.446, and 0.453. These chunks rank higher because the query contains words like "Chess," "king," and "not allowed" that overlap semantically with the overview/movement section text. The actual castling chunk ranks **4th** at 0.512 — just outside the retrieval window.

The LLM correctly refused because it received only overview text with no castling content. The system behaved exactly as designed: refuse when the context doesn't support an answer. The failure is upstream in retrieval, not in generation.

**Fix:** Increase `N_RESULTS` in `config.py` from 3 to 5 or 6. With `n_results=6`, both castling chunks (`chess_11` at 0.540 and `chess_12` at 0.512) would be retrieved and would pass the `MAX_DISTANCE=0.55` filter, giving the LLM the text it needs. The tradeoff is a slightly larger context window per query.

---

## Spec Reflection

**One way the spec helped:** The generate-response spec's "pressure test" section — which enumerated specific failure modes (partial blending, wrong-game contamination, memory-vs-excerpt conflict, helpful elaboration) and required writing a system prompt clause to close each — directly produced the v2 system prompt in `generator.py`. Without that structured pressure-test, it would have been easy to write a soft grounding instruction ("try to use the provided context") that a capable LLM like Llama 3.3 70B would sidestep the moment it had a confident answer from training data. The spec forced specificity.

**One way implementation diverged:** The retrieve-spec documented a relevance threshold as a "generate_response() decision," with the spec's own example showing a 0.50 cutoff as a reference point. After calibrating against real retrieval output — where correct hits measured 0.34–0.47 and clear noise measured 0.60+ — the threshold was set to 0.55, not 0.50. The spec provided the right mental model; the actual number came from empirical measurement, which the spec correctly deferred to implementation time.

---

## AI Usage

**Instance 1 — Implementing `generate_response()`**

After completing `generate-response-spec.md` (system prompt, context formatting, fallback message, distance filter all written out), I gave Claude the full spec file and asked it to implement the function. The generated code matched the spec exactly on structure: `MAX_DISTANCE` filter first, then numbered `[Source N — GAME]` blocks, then the two-message API call. I changed one thing: temperature was generated as 0.2; I lowered it to 0.1 after the spec noted that the goal was "faithful, repeatable grounding, not creative variation" and 0.1 is more conservative.

**Instance 2 — Pressure-testing the system prompt**

Before finalizing the system prompt, I gave Claude a draft v1 prompt and asked it to role-play as the LLM and identify ways a capable model could sidestep the instruction while technically complying. It identified four specific gaps: (L1) partial blending without flagging the gap, (L2) answering about a game not in the excerpts from memory, (L3) silently "correcting" an excerpt with training data when editions differ, (L4) appending helpful memory-sourced elaboration alongside a grounded core. Each gap was closed with a specific clause in the v2 prompt. The final prompt in `generator.py` is the v2 version.

---

## Re-ingesting After Changes

ChromaDB persists to disk in `./chroma_db`. If you change your chunking strategy and want to re-ingest, delete that folder and restart:

```bash
rm -rf chroma_db/   # Mac/Linux
python app.py
```

---

## Rule Books Included

| Game | File |
|------|------|
| Catan | `docs/catan.txt` |
| Chess | `docs/chess.txt` |
| Clue | `docs/clue.txt` |
| Codenames | `docs/codenames.txt` |
| Monopoly | `docs/monopoly.txt` |
| Pandemic | `docs/pandemic.txt` |
| Risk | `docs/risk.txt` |
| Scrabble | `docs/scrabble.txt` |
| Ticket to Ride | `docs/ticket_to_ride.txt` |
| Uno | `docs/uno.txt` |

## Project Structure

```
ai201-lab1-rulesbot-starter/
├── app.py              # Gradio UI and startup logic
├── config.py           # Settings (models, paths, retrieval params)
├── ingest.py           # Document loading + chunking
├── retriever.py        # Vector store + semantic search
├── generator.py        # LLM response generation
├── docs/               # Board game rule documents (10 .txt files)
├── specs/              # Design documents
│   ├── system-design.md
│   ├── chunk-document-spec.md
│   ├── retrieve-spec.md
│   └── generate-response-spec.md
└── planning.md         # Design decisions and evaluation observations
```
