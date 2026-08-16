# VerifiedRAG

A self-correcting, multimodal document Q&A agent — not just a "chat with
your PDF" demo. Most RAG chatbots trust their own first answer. This one
checks whether its own answer is actually supported by the retrieved
documents before showing it to you, and automatically retries with a
rewritten search query when it isn't confident, instead of silently
shipping an unsupported answer.

For the full, honest build story - every real bug found, how it was
diagnosed, and how it was fixed, with evidence - see [`DEVLOG.md`](./DEVLOG.md).

## What makes this different from a basic RAG chatbot

- **Self-correction, not just retrieval.** A `retrieve -> synthesize ->
  verify` loop: if a separate verification step decides an answer isn't
  grounded in the retrieved evidence, the query gets rewritten and
  retried (bounded, so it can't loop forever) - the Corrective RAG /
  Self-RAG pattern.
- **Hybrid retrieval.** Dense (semantic, via embeddings + Qdrant) and
  sparse (keyword, via BM25) search combined with Reciprocal Rank Fusion,
  not just one or the other.
- **Honest about its own confidence.** Every answer is labeled
  "Verified," "Unverified," or "General knowledge - not from your
  documents" - never falsely presented as grounded when it isn't. A
  message router also skips retrieval entirely for greetings/small talk
  instead of running the full pipeline pointlessly.
- **Multimodal ingestion.** PDFs, plain text, spreadsheets (CSV/Excel),
  and scanned/image-only PDF pages (via vision-model OCR) all go through
  the same pipeline.
- **Measured, not just claimed.** A real evaluation harness
  (`app/eval/`) scores the system against hand-verified ground truth and
  reports an actual hallucination rate, broken down by failure-mode
  category (simple lookups, paraphrased questions, multi-hop reasoning,
  adversarial/unanswerable questions, exact-figure lookups) - see
  `eval_results.json` for the latest run.

## Architecture

```
data/  -->  app/ingestion/  -->  app/retrieval/  -->  app/agent/  -->  app/main.py (FastAPI)  -->  frontend/ (React)
(PDF, text,     (loaders,          (embeddings,          (LangGraph:                (POST /ask)         (chat UI)
 CSV/xlsx,       chunker)           Qdrant, BM25,          route -> retrieve ->
 scanned PDF)                       RRF fusion)            synthesize -> verify)
```

- `app/config.py` + `app/models/llm_router.py` - every agent calls one
  function, `call_llm(role, messages)`; which provider/model handles
  each role is configured in one place, no other code changes needed to
  swap a model.
- `app/ingestion/` - loaders for PDF, text, spreadsheets, and scanned-PDF
  OCR, plus chunking.
- `app/retrieval/` - dense embeddings (fastembed/ONNX), Qdrant vector
  store, BM25 keyword search, RRF fusion.
- `app/agent/` - the LangGraph self-correcting loop, plus the verifier.
- `app/eval/` - the evaluation harness (test cases, scorer, runner).
- `app/main.py` - the FastAPI backend.
- `frontend/` - the React/TypeScript chat UI.

## Try it

```bash
pip install -r requirements.txt
cp .env.example .env   # add your GROQ_API_KEY (used for verifier/synthesizer/router)

# Build the searchable index from the sample documents in data/
PYTHONPATH=. python3 scripts/build_index.py

# Start the backend
PYTHONPATH=. uvicorn app.main:app --port 8000

# In another terminal, start the frontend
cd frontend
npm install
npm run dev   # opens on http://localhost:5173
```

Run the evaluation harness (reports a hallucination rate over hand-verified test cases):

```bash
PYTHONPATH=. python3 scripts/run_eval.py
```

## Status

Built and verified: ingestion (including multimodal), hybrid retrieval,
the self-correcting agent loop, the FastAPI backend, the React frontend,
and the evaluation harness (partially run - see `eval_results.json` and
`DEVLOG.md` steps 24-25 for current numbers and why it's not yet a full
run). Deliberately not built: Docker/AWS deployment - deprioritized in
favor of the parts that actually demonstrate the project's core claim.
