import chromadb
from chromadb.utils import embedding_functions
from config import CHROMA_COLLECTION, CHROMA_PATH, EMBEDDING_MODEL, N_RESULTS

# Embedding function and ChromaDB client are initialized once at module load.
# sentence-transformers downloads the model on first use — this may take
# 30–60 seconds the very first time. Subsequent runs use a local cache.
_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=EMBEDDING_MODEL
)
_client = chromadb.PersistentClient(path=CHROMA_PATH)
_collection = _client.get_or_create_collection(
    name=CHROMA_COLLECTION,
    embedding_function=_ef,
    metadata={"hnsw:space": "cosine"},
)


def get_collection():
    """Return the ChromaDB collection. Used by app.py during ingestion."""
    return _collection


def embed_and_store(chunks):
    """
    Embed a list of chunks and store them in the vector database.

    This function is already implemented — read through it before moving on.

    _collection.add() takes three parallel lists built from the chunks
    returned by chunk_document():
      - documents : raw text strings — ChromaDB's embedding function converts
                    these to vectors automatically using sentence-transformers
      - metadatas : one dict per chunk, stored alongside the vector so that
                    retrieve() can surface which game a result came from
      - ids       : the unique chunk_id strings used to identify each entry

    You don't generate embeddings manually here — you hand over the text
    and ChromaDB handles the vector math.
    """
    _collection.add(
        documents=[c["text"] for c in chunks],
        metadatas=[{"game": c["game"]} for c in chunks],
        ids=[c["chunk_id"] for c in chunks],
    )
    print(f"Stored {_collection.count()} total chunks in the vector database.")


def retrieve(query, n_results=N_RESULTS):
    """
    Find the most relevant rule chunks for a user's question via semantic search.

    Embeds `query` (using the same all-MiniLM-L6-v2 model the chunks were
    stored with) and returns the `n_results` closest chunks by cosine distance.

    Returns a list of dicts, ordered most- to least-relevant (ascending
    distance), each with:
      - "text"     : the chunk text
      - "game"     : the game name (pulled from the chunk's metadata)
      - "distance" : cosine distance, lower = more similar

    Returns [] if the collection is empty. No relevance threshold is applied
    here — that grounding decision is deferred to generate_response().

    Note: _collection.query() returns nested lists (one inner list per query).
    We pass a single query, so the results live at index [0] of each list.
    """
    if _collection.count() == 0:
        return []

    # Semantic search: ChromaDB embeds `query` with the same model used at
    # ingestion (all-MiniLM-L6-v2), so query and chunks live in the same
    # vector space and cosine distance is comparable. This is meaning-based
    # matching, not keyword matching.
    results = _collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    # query() returns lists-of-lists indexed by query. We passed one query,
    # so the actual results live at index [0] of each parallel list.
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    # Already sorted lowest-to-highest distance (most to least relevant), so
    # zipping in order preserves the ranking the contract requires.
    return [
        {"text": doc, "game": meta["game"], "distance": dist}
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]
