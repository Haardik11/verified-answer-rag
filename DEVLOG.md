# VerifiedRAG — Development Log

A plain-English record of each build step: what was built, why, and how it
was verified. Written to be read back once the project is done, as a
refresher for explaining the project (e.g. in an interview).

## 1. Project scaffolding
`.gitignore`, `README.md`, `requirements.txt`, `.env.example`. No code yet
— just the basic setup every repo needs.

## 2. Model abstraction layer
`app/config.py` + `app/models/llm_router.py`. Every agent calls one
function, `call_llm(role, messages)`, and a config dict decides which
actual provider (Ollama locally, or OpenAI/Anthropic) handles that role.
Swapping a model later is a one-line config change, not a code change.

## 3. Document ingestion
`app/ingestion/loaders.py` (PDF/text → plain string) and `chunker.py`
(splits text into overlapping word-window chunks, so an answer that
straddles a chunk boundary doesn't get cut in half). Tested via
`scripts/test_ingestion.py` against `data/sample.txt` and `data/sample.pdf`
(two short Q3 financial documents used as sample data throughout).

## 4. Dense embeddings
`app/retrieval/embeddings.py` wraps `fastembed` (ONNX-based, not torch —
smaller footprint for eventual Docker deployment) using the
`BAAI/bge-small-en-v1.5` model. Converts text into 384-number vectors that
represent meaning, so semantically similar text ends up numerically close.
Smoke-tested by embedding sample strings and checking the output shape.

## 5. Vector store (dense/semantic search)
`app/retrieval/vector_store.py` wraps **Qdrant** running in local embedded
mode (`QdrantClient(path=...)` — no separate server process). `add_chunks()`
embeds and stores chunks; `dense_search()` embeds a query and returns the
closest matches by cosine similarity. Originally planned as ChromaDB, swapped
to Qdrant mid-build for its embedded mode and native fastembed pairing.
Verified with a 3-sentence test set: a query about the Eiffel Tower
correctly ranked the Eiffel Tower sentence highest.

## 6. Sparse search (BM25 keyword search)
`app/retrieval/sparse.py` implements classic keyword-based ranking (no AI
involved), rebuilding its index in memory from whatever's in Qdrant rather
than keeping a second copy of the documents. Verified: a "Python
programming language" query correctly ranked the Python sentence highest
by literal word overlap.

## 7. Hybrid search (RRF fusion)
`app/retrieval/hybrid.py` combines dense and BM25 rankings using
Reciprocal Rank Fusion (merges by rank position, since cosine similarity
and BM25 scores aren't on comparable scales). `hybrid_search()` is the one
function the rest of the project calls for retrieval.

## 8. Real end-to-end retrieval test
`scripts/build_index.py` (loads + chunks + embeds + stores the real sample
docs) and `scripts/test_hybrid.py` (runs real questions through
`hybrid_search`). Confirmed retrieval correctly discriminates between
sources: "risk factors" and "operating expenses" questions correctly
ranked the PDF higher (that content only exists there); "SMB segment"
correctly ranked the `.txt` file higher; "What was Q3 revenue?" came back
a near-tie, correctly, since both documents state that fact.

## 9. LangGraph retrieve → synthesize agent (baseline RAG loop)
`app/agent/graph.py` wires `hybrid_search()` and
`call_llm(role="synthesizer", ...)` into a two-node LangGraph:
`retrieve → synthesize`. This is deliberately the simplest working
version — no verification yet. Required installing `langgraph` (pulls in
`langchain-core` as a small dependency, but not the broader LangChain
framework) and getting Ollama running locally with the `llama3.2` model
pulled (a mismatch with an older `llama3` pull had to be fixed first).

Verified twice with real questions against the real index:
- "What was Q3 revenue...?" → correct, grounded answer.
- "What is driving operating expenses...?" → facts were correct, but the
  answer **mislabeled which source the claim came from** (said "the text
  file" when the sentence was actually from the PDF). This wasn't a bug in
  the code — retrieval pulled the right chunks — it was the LLM being
  loosely accurate rather than strictly grounded. This is a live example
  of exactly the failure mode the next step is meant to catch.

## 10. (In progress) Verifier / self-correction loop
The actual differentiator. Adding a `verify` node that checks whether the
synthesized answer is genuinely supported by the retrieved context, and a
conditional branch that re-retrieves and retries when confidence is low,
instead of just returning an unsupported answer.
