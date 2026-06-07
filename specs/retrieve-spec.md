# Spec: `retrieve()`

**File:** `retriever.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Given a user's natural language query, find the most relevant chunks from the vector store using semantic similarity search. Return them ranked by relevance so that `generate_response()` can use them as context.

---

## Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | `str` | The user's natural language question |
| `n_results` | `int` | Maximum number of chunks to return (default: `N_RESULTS` from `config.py`) |

**Output:** `list[dict]`

Each dict in the returned list must contain exactly these keys:

| Key | Type | Description |
|-----|------|-------------|
| `"text"` | `str` | The chunk text |
| `"game"` | `str` | The game name this chunk came from |
| `"distance"` | `float` | Cosine distance score — lower means more similar to the query |

Results should be ordered from most to least relevant (lowest to highest distance). Returns an empty list `[]` if the collection contains no documents.

---

## Design Decisions

*Complete the fields below before writing any code. Use your AI tool in Plan or Ask mode to help you reason through what belongs here — but the decisions are yours.*

---

### Query approach

*Describe how you will use `_collection.query()` to find relevant chunks. What arguments will you pass, and why?*

```
Call _collection.query() with three arguments:

  - query_texts=[query]
        A list containing the single user question. ChromaDB embeds each
        string here using the SAME embedding function (all-MiniLM-L6-v2)
        that embed_and_store() used on the chunks. That shared model is
        what makes the comparison meaningful — query and chunks land in
        the same 384-dim vector space, so cosine distance is comparable.

  - n_results=n_results
        Caps how many chunks come back (default 3 from config.N_RESULTS).
        Chroma does the nearest-neighbor search and returns the closest
        n_results, already sorted ascending by distance.

  - include=["documents", "metadatas", "distances"]
        Controls what payload comes back. We need:
          documents  -> the chunk text, to hand to the LLM as context
          metadatas  -> the game name, so the answer can be attributed
          distances  -> the cosine score, for ranking + downstream gating
        We deliberately omit "embeddings" — we don't need 384 floats per
        result, that's just wasted payload. (ids come back by default.)
```

---

### Return structure

*Sketch out what one item in your return list looks like as a concrete example. Where does each field come from in the query results?*

```
One returned item (real output, query "How do you get out of Jail in Monopoly?"):

  {
      "text":     "a row. When sent to Jail, move directly to Jail — do not
                   pass Go, do not collect $200. ...",
      "game":     "Monopoly",
      "distance": 0.3665616512298584,
  }

(Note: "text" can start mid-sentence — the character splitter is boundary-
indifferent. And "distance" is a raw float, ~0.37 even for a clearly
correct hit with this embedding model; it does NOT bottom out near 0.)

Where each field comes from (results = _collection.query(...)):

  "text"     <- results["documents"][0][i]
  "game"     <- results["metadatas"][0][i]["game"]   (the dict we stored
                in embed_and_store; pull the "game" key out of it)
  "distance" <- results["distances"][0][i]

The [0] is the single-query index (see next section); i walks the
results in returned order, which is already lowest-to-highest distance.
So building the list in order preserves the most-to-least-relevant
ordering the contract requires — no manual re-sort needed.
```

---

### Handling the nested result structure

*`_collection.query()` returns nested lists. Describe what index you need to access to get the actual list of results for a single query, and why the nesting exists.*

```
query() returns a dict whose values are lists-of-lists, with the OUTER
list indexed by query:

  {
      "documents": [ [doc, doc, doc] ],   # one inner list per query_text
      "metadatas": [ [md,  md,  md ] ],
      "distances": [ [d,   d,   d  ] ],
      "ids":       [ [id,  id,  id ] ],
  }

GOTCHA (confirmed against real output): the dict ALWAYS contains every
key — the real top-level keys are:
  ['ids', 'embeddings', 'documents', 'uris', 'included', 'data',
   'metadatas', 'distances']
Keys you did NOT request in `include` (e.g. 'embeddings', 'uris', 'data')
are present but set to None, not absent. So `"embeddings" in results` is
True even though we never asked for them — never test presence by key, just
index the lists you requested. 'ids' always comes back regardless.

The nesting exists because query_texts can be a BATCH of many queries —
results["documents"][q] is the result list for query q. We pass exactly
one query, so everything we want lives at index [0]:

      docs  = results["documents"][0]
      metas = results["metadatas"][0]
      dists = results["distances"][0]

Then zip/iterate those three parallel inner lists together. Forgetting
the [0] is the classic bug here: you'd be iterating the outer list (length
1) and treating an entire inner list as if it were a single result.
```

---

### Relevance threshold

*Will you filter out results above a certain distance score, or return all `n_results` regardless of how relevant they are? What are the tradeoffs of each approach?*

```
Decision: retrieve() does NOT threshold. It returns up to n_results
chunks, sorted by distance, with the raw distance attached to each. Any
relevance gating happens downstream in generate_response().

Why this split (separation of concerns):
  - retrieve()'s job is "rank what's in the store by similarity." It is
    a pure search primitive — it shouldn't decide what's "good enough."
  - The system design explicitly says the distance threshold "matters for
    generate_response()" and that distances above ~0.5 signal weak
    relevance. So the threshold is a GROUNDING decision, and grounding
    lives in generation, not retrieval.
  - We attach "distance" to every result precisely so the generator (or a
    UI debug view) can apply that judgment with full information.

Tradeoffs:
  - Filtering inside retrieve(): can return fewer than n_results, or even
    []. Cleaner output, but it hides borderline chunks from the generator
    and bakes a magic-number threshold into the search layer, where it's
    hard to tune per-query. Worse, an empty return is indistinguishable
    from an empty collection.
  - Returning all n_results (chosen): the generator always has material to
    reason over and can refuse based on distance + content together. Cost
    is that weak/irrelevant chunks can appear, so generate_response() MUST
    be written to ignore them rather than dutifully summarizing junk.
```

---

### Edge cases

*How does your implementation behave when: (a) the collection is empty, (b) the query matches no chunks well, (c) the query matches chunks from multiple games?*

```
(a) Empty collection:
    Guarded by the existing `if _collection.count() == 0: return []` at
    the top. We return [] WITHOUT calling query(), so the caller never
    sees a crash or a malformed empty-nested-list result. generate_response()
    then has nothing to ground on and should say it can't answer.

(b) Query matches nothing well:
    Because we don't threshold, query() still returns n_results — but with
    high distances (e.g. > 0.5). The list is non-empty yet weakly relevant.
    This is intentional: retrieve() reports "here's the closest I found,
    and here's how far it is." generate_response() is responsible for
    noticing the high distances / thin content and refusing rather than
    hallucinating. (A confident wrong answer is the failure mode we most
    want to avoid.)

(c) Matches span multiple games:
    Results are ranked purely by cosine distance, so a single response can
    interleave chunks from different rulebooks (e.g. a "how do you win?"
    query is similar to victory-condition text in many games). We do NOT
    filter by game. The "game" field on each result is what lets the
    generator attribute/caveat the answer ("In Catan, ... ; in Ticket to
    Ride, ..."). Known risk: cross-game contamination — a rule from the
    wrong game ranking above the right one. A future improvement would be
    an optional game filter via query(where={"game": ...}), but the lab
    keeps retrieval game-agnostic.
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 3.*

**Test query and top result returned:**

```
Query: "What happens when you roll a 7?"
Top result game: Catan
Distance score: 0.466
Does it make sense? Yes. The top chunk is the complete "ROLLING A 7"
rule — no resources produced, players with >7 cards discard half, the
roller moves the robber and steals a card. Exactly the right rule from
the right game.

(Second test) Query: "How do you win?"
Top result game: Monopoly (0.507), then Risk (0.509), Ticket to Ride (0.522)
Does it make sense? Yes — this question names no game, so winning-condition
chunks from multiple rulebooks legitimately tie. Correct multi-game behavior,
not a failure.
```

**One thing about the query results that surprised you:**

```
Two things:

1. Distances are much HIGHER than the lab's example numbers (~0.14 vs our
   ~0.47 for a perfect hit). At first this looked like a problem. It isn't:
   all-MiniLM-L6-v2 + cosine just doesn't push distances toward 0, even for
   exact matches. The right anchor for "relevant vs weak" with THIS model is
   ~0.5 (per the system design), not the textbook 0.1-0.2. We must remember
   this when setting the threshold in generate_response() — a 0.2 cutoff
   would reject every correct answer.

2. The BARE query "What happens when you roll a 7?" pulled Risk's dice-rolling
   rules into slots 2 and 3 (~0.60), because "roll"/"dice" is semantically
   close to Risk combat. Adding "...in Catan" to the query made all three
   results Catan. So wrong-game results here came from an UNDER-SPECIFIED
   QUERY, not from a chunking or retrieval bug — verified by re-checking that
   the chunks themselves are full, meaningful passages. The Risk hits sitting
   at ~0.6 (our weak zone) is retrieval being honest about marginal matches,
   which is exactly the signal generate_response() will gate on.
```
