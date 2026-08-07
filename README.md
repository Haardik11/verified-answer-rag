# VerifiedRAG (working title)

Self-correcting multimodal document agent. Built incrementally - this is
step 1-2 of the full build.

## What's here so far
- `app/config.py` + `app/models/llm_router.py` - model abstraction layer.
  Every agent calls one function; swap Ollama/OpenAI/Anthropic per role by
  editing `ROLE_MODELS` in `config.py`, no other code changes needed.
- `app/ingestion/loaders.py` - loads PDF and plain text into raw text.
- `app/ingestion/chunker.py` - splits text into overlapping chunks.

## Try it
```bash
pip install -r requirements.txt
PYTHONPATH=. python3 scripts/test_ingestion.py
```

## Coming next
- Embeddings + ChromaDB (dense retrieval)
- BM25 + hybrid fusion
- The actual retrieve -> synthesize agent loop
- FastAPI backend
- React frontend
- Verifier / self-correction loop
- Evaluation harness
