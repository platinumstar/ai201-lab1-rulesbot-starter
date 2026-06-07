# Spec: `chunk_document()`

**File:** `ingest.py`
**Status:** Pre-implemented — read through this spec and the code in `ingest.py` before moving to Milestone 2.

---

## Purpose

Split a single rule book document into smaller chunks suitable for embedding and semantic retrieval. Each chunk should carry enough context to be meaningful on its own when retrieved in response to a user query.

---

## Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | The full text of a rule book document |
| `game_name` | `str` | The name of the game this document belongs to (e.g., `"Catan"`) |

**Output:** `list[dict]`

Each dict in the returned list contains exactly these keys:

| Key | Type | Description |
|-----|------|-------------|
| `"text"` | `str` | The chunk text |
| `"game"` | `str` | The game name (passed through from `game_name`) |
| `"chunk_id"` | `str` | A unique identifier for this chunk (e.g., `"catan_0"`, `"catan_1"`) |

Returns an empty list `[]` if the input text is empty or produces no valid chunks.

---

## Design Decisions

---

### Splitting approach

```
Character-based sliding window. The document text is stepped through in
fixed-size windows of `chunk_size` characters, advancing by
(chunk_size - overlap) on each step so adjacent chunks share a small
region of text at their boundary.
```

---

### Chunk size

```
300 characters. Rule book text is semantically dense — a single rule is
often 1–3 sentences, which fits comfortably in this range. Going smaller
would fragment individual rules; going larger would merge unrelated rules
into one chunk, making retrieval less precise.
```

---

### Overlap

```
50 characters of overlap between adjacent chunks. If a rule falls exactly
on a chunk boundary, neither chunk alone contains the full rule. Overlap
duplicates the tail of each chunk at the start of the next, so boundary-
spanning content can still be retrieved intact. 50 characters is roughly
one short sentence — enough to preserve context without significantly
bloating the database.
```

---

### Minimum chunk length

```
50 characters. Chunks shorter than this are discarded. Very short segments
typically contain only whitespace, section headers, or punctuation — content
that has no semantic signal and would just add noise to the vector database.
```

---

### Rationale

```
Rule books pack a lot of meaning into short passages, so smaller chunks
tend to outperform paragraph-level splitting for targeted Q&A. A 300-
character window is typically one complete rule — the right unit of
retrieval for questions like "What happens when you roll a 7?" Paragraph
splitting would work but produces uneven chunk sizes, since rule book
paragraphs vary from one sentence to ten.
```

---

### Known limitations

```
Character-based splitting is indifferent to sentence and paragraph
boundaries. A chunk can begin mid-sentence or split a rule across two
chunks even with overlap, if the rule is longer than `chunk_size`.
Numbered lists (e.g., "1. ... 2. ... 3. ...") may get split in the
middle of an item. A paragraph-aware or sentence-aware splitter would
handle these cases better, at the cost of more implementation complexity.
```

---

## Implementation Notes

*Fill this in after running the app and confirming ingestion worked.*

**Actual chunk count produced across all 8 rule books:**

```
149 chunks total. Per rulebook:
  Catan          18      Pandemic         18
  Clue           21      Risk             20
  Codenames      16      Ticket to Ride   16
  Monopoly       23      Uno              17

That averages ~18.6 chunks/book, with a tight spread (16-23). The count is
deterministic — re-ingesting the same docs produces exactly 149 every time,
as expected from a fixed-size character window. A scan confirmed 0 chunks
contain HTML/markup, so the source .txt files are clean plain text.
```

**One thing that surprised you or didn't match your expectations:**

```
How indifferent the splitter is to word and sentence boundaries — and how
little that hurt retrieval. Printed chunks frequently start mid-sentence, and
some start mid-WORD (e.g. one Catan chunk begins "ding cost cards, 2 special
cards..." — the front of "building" got cut off on the previous boundary).
I expected those ragged edges to noticeably degrade search quality. They
didn't: the embedding model still matched these chunks correctly to relevant
queries, because semantic meaning survives a clipped first/last word.

A second, subtler surprise: dropping short tail chunks (< min_length) loses
NO information. Because min_length (50) equals the overlap (50), any tail too
short to keep is already fully contained in the previous chunk's overlap
region. So the min-length filter only ever discards text that's already
duplicated elsewhere — a clean property I didn't anticipate when reading the
spec, only noticed when tracing the window arithmetic.
```
