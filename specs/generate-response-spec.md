# Spec: `generate_response()`

**File:** `generator.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Given a user query and a list of retrieved rule chunks, generate a response that directly answers the question using only the retrieved text as context. The response must be grounded — it should not draw on the model's general knowledge of board games, only on what was retrieved.

---

## Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | `str` | The user's original question |
| `retrieved_chunks` | `list[dict]` | Ranked list of chunks from `retrieve()`, each with `"text"`, `"game"`, and `"distance"` |

**Output:** `str`

A plain string containing the response to show the user. The response should:
- Answer the question using only the retrieved rule text
- Identify which game the answer comes from
- Acknowledge clearly when the answer is not found in the loaded rules

Returns a fallback string (not an error) when `retrieved_chunks` is empty.

---

## Design Decisions

*Complete the fields below before writing any code. Use your AI tool in Plan or Ask mode to help you reason through what belongs here — but the decisions are yours.*

---

### Context formatting

*How will you format the retrieved chunks before passing them to the LLM? Describe the structure — not the code. Consider: will you label chunks by game? Include distance scores? Separate chunks with delimiters?*

```
Each chunk becomes a numbered, game-labeled "source" block, separated by a
blank line, e.g.:

  [Source 1 — Pandemic]
  <chunk text>

  [Source 2 — Pandemic]
  <chunk text>

Decisions and why:
  - LABEL BY GAME: yes. The game name is what the model must cite, so it has
    to be visible in the context. Putting it in the block header (not buried
    in prose) makes it unambiguous which game each source belongs to —
    important when sources span multiple games.
  - NUMBER THE SOURCES: yes. Gives the model a stable handle and makes the
    context readable; cheap insurance.
  - DISTANCE SCORES: NO — do not put raw distances in the prompt. The number
    is meaningless to the model and could invite it to editorialize about
    confidence. Distance is used by OUR code to filter (see "Handling
    low-relevance chunks"), not shown to the LLM.
  - DELIMITERS: blank line + bracketed header per source. Clear visual
    separation so the model treats them as distinct excerpts, not one blob.

Research-aligned rationale (general findings, not a specific citation):
  - Explicit, consistent delimiters around each source reduce cross-source
    "blending" — the model is less likely to merge two excerpts into one
    false claim when each is clearly fenced and labeled. Bracketed/tagged
    headers (or XML-style tags) are a common, well-supported way to do this.
  - Models attend unevenly to position in long context ("lost in the middle"
    effect): content at the start and end is weighted more than the middle.
    Here it's mild — we feed only the few chunks that pass the distance
    filter, and retrieve() already returns them best-first, so the strongest
    evidence sits at the top where attention is highest.
  - Labeling the SOURCE (game) next to the text is what makes faithful
    citation possible — the model cites the label it can see, not a guess.
```

---

### System prompt — grounding instruction

*Write the exact system prompt instruction you will use to prevent the model from answering beyond the retrieved text. This is the most important design decision in this function.*

```
EXACT system prompt text (pressure-tested, v2):

  You are RulesBot, a board-game rules assistant. Answer the user's question
  using ONLY the rule excerpts provided in the context below.

  Strict rules:
  - The excerpts are the single source of truth. Do NOT use any prior
    knowledge you have about these games, even if you are confident — and
    even if an excerpt seems wrong or incomplete. If your own knowledge
    conflicts with an excerpt, follow the excerpt.
  - Every statement in your answer must be supported by the excerpts. Do not
    add clarifications, examples, edge cases, strategy, or "in most editions"
    caveats from memory.
  - If the excerpts answer only PART of the question, answer that part and
    state plainly which part the provided rules do not cover. Do not fill the
    gap from memory.
  - If the excerpts do not answer the question at all — or only concern a game
    the question is not about — say so plainly. Do not guess or infer rules
    that are not explicitly stated.
  - Only discuss games that actually appear in the excerpts. If the question
    is about a game not present in the excerpts, say its rules aren't loaded.
  - A short, honest "the provided rules don't cover that" is a correct and
    preferred answer — better than a confident answer not supported by text.
  - Keep answers concise; quote or closely paraphrase the relevant excerpt.

Why this wording: Llama 3.3 70B knows these games from pretraining and will
answer from memory unless explicitly forbidden. The instruction (a) names the
excerpts as the ONLY allowed source, (b) pre-authorizes "I don't know," and
(c) states the failure preference (honest gap > confident hallucination) so
refusing reads as success, not failure, to the model.

PRESSURE-TEST — holes found in the v1 draft and how v2 closes each:
  (L1) PARTIAL BLENDING — the worst case (the "you can't tell which parts"
       failure): excerpt covers half the rule, model completes the rest from
       memory silently. v1 said "don't fill gaps" but never forced the model
       to ISOLATE supported from unsupported. v2: answer the supported part,
       explicitly name the part the rules don't cover.
  (L2) WRONG-GAME / OUT-OF-SCOPE: question is about a game not in the
       excerpts; model answers from memory. v2: only discuss games present in
       the excerpts; otherwise say not loaded.
  (L3) MEMORY-vs-EXCERPT CONFLICT: model "corrects" the excerpt with training
       data (editions differ). v2: the excerpt wins, always.
  (L4) HELPFUL ELABORATION: model appends examples/strategy/"usually..." from
       memory beside a grounded core. v2: every statement must be excerpt-
       supported; no memory-sourced clarifications or caveats.
  (Residual, accepted) DEFINITIONAL leakage — what "doubles" or "a turn"
       means — is hard to forbid without hurting readability and is low-risk.
       The distance filter + "quote/paraphrase, be concise" keep it minimal.
```

---

### System prompt — citation instruction

*Write the exact instruction you will use to tell the model to identify which game its answer comes from.*

```
Begin your answer by naming the game it comes from, taken from the [Source N
— GAME] label on the excerpt(s) you used (e.g., "In Pandemic, ..."). If the
relevant excerpts come from more than one game, make the game clear for each
part of your answer rather than blending them together. Never attribute a
rule to a game whose excerpt you did not actually use.

Why: the citation is what lets the user trust and verify the answer ("which
rulebook did this come from?"). Anchoring it to the source LABEL (not the
model's own guess about the game) keeps the citation grounded in the same
evidence as the answer, and the multi-game clause prevents the model from
silently merging, say, a Risk rule and a Catan rule into one false claim.
```

---

### Fallback behavior

*What should the response say when the answer isn't found in the loaded rule books? Write the exact fallback message.*

```
Exact message:

  "I couldn't find an answer to that in the loaded rule books (Catan, Clue,
  Codenames, Monopoly, Pandemic, Risk, Ticket to Ride, and Uno). The rules I
  have don't appear to cover it. Try rephrasing your question, or name the
  specific game you're asking about."

When it fires — TWO cases, same message:
  1. retrieved_chunks is empty (collection empty / retrieve() returned []).
     (A fallback already exists for this in generator.py, but its current
     wording mentions "check your ingestion pipeline," which is developer-
     facing. Replace it with the user-facing message above.)
  2. All chunks were filtered out as low-relevance (see next field) — i.e.
     nothing cleared the distance threshold. From the user's point of view
     this is the same situation: we have no trustworthy material to answer
     from, so we say so rather than feeding junk to the model.

Why list the games: it doubles as a gentle hint about scope (these 8 books)
and nudges the user to name one, which—per Milestone 2—sharpens retrieval.
This is a normal STRING return, not an error/exception.
```

---

### Handling low-relevance chunks

*`retrieved_chunks` may include chunks with high distance scores (weak relevance). Will you filter these out before building context, pass them all in, or handle them another way? What are the tradeoffs?*

```
Approach: DISTANCE FILTER + PROMPT, layered (defense in depth).

  1. Filter: keep only chunks with distance <= MAX_DISTANCE before building
     context. If nothing survives, return the fallback message (don't call
     the LLM at all).
  2. Backstop: the grounding system prompt still instructs the model to
     refuse if the surviving excerpts don't actually answer the question.

Threshold value: MAX_DISTANCE = 0.55, chosen from OUR measured distribution
for all-MiniLM-L6-v2 (NOT the textbook 0.1-0.2 bands, which don't apply to
this model):
  - correct, on-topic hits measured ~0.34-0.47  -> kept
  - legit but game-agnostic ("how do you win?")  ~0.51-0.52  -> kept
  - off-target cross-game noise (Risk dice rules
    surfacing for a bare "roll a 7")  ~0.60+      -> dropped
  0.55 sits in the gap: it keeps real answers (incl. the borderline
  multi-game ones) and trims the clearly-weak matches. Tunable constant.

Tradeoffs:
  - Filter too LOW (e.g. 0.4): drops genuine borderline hits like the
    "how do you win?" cluster -> too many false "I don't know" refusals.
  - Filter too HIGH (e.g. 0.7) or not at all: weak/off-topic chunks reach
    the model. Even with a grounding prompt, irrelevant context can pull a
    capable model off-track or tempt it to stitch an answer from a bad chunk.
  - Why BOTH filter and prompt: the filter removes obvious junk cheaply and
    deterministically; the prompt catches the subtler case where a chunk is
    close enough to pass the threshold but still doesn't answer THIS question.
    Neither alone is sufficient — distance measures topical similarity, not
    whether the text actually contains the answer.
```

---

### Message structure

*Describe how you will structure the messages list for the API call — what goes in the system message vs. the user message?*

```
Two messages:

  messages = [
    {"role": "system", "content": <persona + grounding rules + citation rule>},
    {"role": "user",   "content": "Context:\n" + <formatted source blocks> +
                                   "\n\nQuestion: " + query},
  ]

Split rationale:
  - SYSTEM = the stable BEHAVIOR: who the bot is, "use only the excerpts,"
    "say I don't know," "cite the game." These don't change per request, so
    they belong in the durable instruction channel and carry the most weight.
  - USER = the per-request DATA: the formatted context block followed by the
    actual question. Putting the retrieved excerpts here (not in system)
    keeps the system prompt fixed across queries and clearly frames the
    excerpts as material to answer FROM, with the question last so it's the
    final thing the model reads.

API params:
  - model = config.LLM_MODEL (llama-3.3-70b-versatile)
  - temperature = low (~0.1-0.2): we want faithful, repeatable grounding,
    not creative variation. Low temp reduces the odds of the model drifting
    off the provided text.
```

---

## Implementation Notes

*Fill this in after implementing and testing.*

**Test query and response:**

```
Query: "How do you get out of Jail in Monopoly?"
Response: "In Monopoly, to get out of Jail: pay a $50 fine before rolling on
          any of your next three turns, use a Get Out of Jail Free card, or
          roll doubles on any of your three turns in Jail."
Correctly grounded? YES — the answer is a near-verbatim paraphrase of the
          top retrieved chunk (Source 1, dist 0.367). Litmus test passed:
          every claim ($50, Get Out of Jail Free card, doubles, three turns)
          appears in the retrieved text; it inherited the chunk's specific
          "three turns" wording rather than generic Monopoly knowledge, so it
          could not have come from anywhere but the excerpt.
Cited the right game? YES — opened with "In Monopoly, ..." from the source label.

(Refusal test) Query: "How does castling work in chess?"
Response: the fallback message (refused).
Correctly grounded? YES — admitted it doesn't know instead of improvising
          chess rules from memory.
```

**One thing you changed from your original spec after seeing the actual output:**

```
Nothing in the prompt needed changing — but I learned the distance FILTER is
doing more of the grounding work than I'd assumed. For the out-of-corpus
chess question, the three "nearest" chunks came back at 0.695 / 0.701 / 0.705
— all above MAX_DISTANCE (0.55) — so they were ALL filtered out and the
fallback fired WITHOUT ever calling the LLM. The grounding prompt's refusal
clause never even got exercised for that case; the filter caught it first.

Takeaway: the ~0.55 threshold is well-placed for clear out-of-corpus queries
(genuinely unrelated content lands at ~0.7). The prompt's refusal instruction
is the backstop for the HARDER case — a chunk that's topically close enough to
pass 0.55 but still doesn't actually contain the answer. Both layers matter;
they just guard different failure modes, exactly as the spec intended.
```
