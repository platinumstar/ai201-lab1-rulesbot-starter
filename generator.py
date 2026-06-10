from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL

_client = Groq(api_key=GROQ_API_KEY)

# Chunks with a cosine distance above this are treated as too weakly related
# to answer from, and are dropped before building context. Calibrated to the
# all-MiniLM-L6-v2 distribution we measured (good hits ~0.34-0.47, off-target
# noise ~0.60+); 0.55 sits in the gap. Tunable.
MAX_DISTANCE = 0.55

# Exact grounding + citation instruction from the spec. Do NOT soften this:
# every clause prohibits a specific behavior so the model has nothing to
# sidestep. The excerpts are the only allowed source; refusing is success.
SYSTEM_PROMPT = """You are RulesBot, a board-game rules assistant. Answer the user's question using ONLY the rule excerpts provided in the context below.

Strict rules:
- The excerpts are the single source of truth. Do NOT use any prior knowledge you have about these games, even if you are confident — and even if an excerpt seems wrong or incomplete. If your own knowledge conflicts with an excerpt, follow the excerpt.
- Every statement in your answer must be supported by the excerpts. Do not add clarifications, examples, edge cases, strategy, or "in most editions" caveats from memory.
- If the excerpts answer only PART of the question, answer that part and state plainly which part the provided rules do not cover. Do not fill the gap from memory.
- If the excerpts do not answer the question at all — or only concern a game the question is not about — say so plainly. Do not guess or infer rules that are not explicitly stated.
- Only discuss games that actually appear in the excerpts. If the question is about a game not present in the excerpts, say its rules aren't loaded.
- A short, honest "the provided rules don't cover that" is a correct and preferred answer — better than a confident answer not supported by text.
- Keep answers concise; quote or closely paraphrase the relevant excerpt.

Begin your answer by naming the game it comes from, taken from the [Source N — GAME] label on the excerpt(s) you used (e.g., "In Pandemic, ..."). If the relevant excerpts come from more than one game, make the game clear for each part of your answer rather than blending them together. Never attribute a rule to a game whose excerpt you did not actually use."""

# Shown when there is nothing trustworthy to answer from — either retrieval
# returned nothing, or every chunk was filtered out as too weakly relevant.
FALLBACK_MESSAGE = (
    "I couldn't find an answer to that in the loaded rule books (Catan, Chess, Clue, "
    "Codenames, Monopoly, Pandemic, Risk, Scrabble, Ticket to Ride, and Uno). The rules I "
    "have don't appear to cover it. Try rephrasing your question, or name the "
    "specific game you're asking about."
)


def generate_response(query, retrieved_chunks):
    """
    Generate a grounded answer from retrieved rule chunks.

    `retrieved_chunks` is the list returned by retrieve(); each item is a dict
    with "text", "game", and "distance".

    Pipeline:
      1. Drop chunks weaker than MAX_DISTANCE. If none survive, return the
         fallback message without calling the LLM.
      2. Format the survivors as numbered, game-labeled source blocks.
      3. Ask the LLM (system = grounding/citation rules, user = context +
         question) for an answer drawn ONLY from those excerpts, citing the
         game and refusing when the rules don't cover the question.

    Returns the answer as a plain string (or the fallback string).
    """
    # Drop weakly-related chunks (see MAX_DISTANCE). If nothing survives —
    # whether because retrieval returned nothing or everything was too far —
    # there is no trustworthy material to ground an answer in, so we refuse
    # rather than feed junk to the model.
    relevant = [c for c in retrieved_chunks if c["distance"] <= MAX_DISTANCE]
    if not relevant:
        return FALLBACK_MESSAGE

    # Format each surviving chunk as a numbered, game-labeled source block,
    # separated by blank lines so the model treats them as distinct excerpts.
    context = "\n\n".join(
        f"[Source {i} — {c['game']}]\n{c['text']}"
        for i, c in enumerate(relevant, start=1)
    )

    # System = stable grounding/citation behavior; user = per-request data
    # (the context block followed by the question, question last).
    response = _client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content
