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

## 10. Verifier / self-correction loop
The actual differentiator. `app/agent/verify.py` adds a separate LLM call
(role=`"verifier"`) that judges whether a synthesized answer is genuinely
supported by the retrieved context - tested standalone first against the
real "correct facts, wrong source" case from step 9, and it correctly
told the two apart (`grounded: True` vs `grounded: False`).

`app/agent/graph.py` was then rewired into the full self-correcting loop:
`retrieve -> synthesize -> verify`, with a conditional branch - if not
grounded, `rewrite_query` (a new LLM call, role=`"query_rewrite"`)
rephrases the search query and the loop retries, bounded by
`max_attempts` so it can't run forever.

Verified two real behaviors:
- **Easy question** ("What was Q3 revenue?"): passed verification on the
  first attempt, 0 retries - confirms the loop doesn't retry
  unnecessarily when the answer is already well-grounded.
- **Hard question** ("What is driving the operating expenses this
  quarter?"): failed verification on all 3 attempts (hit `max_attempts`),
  and correctly returned the best-effort answer with `grounded: False`
  clearly flagged, instead of silently pretending it succeeded. Streaming
  the graph's steps showed the verifier's rejection reason was somewhat
  pedantic each time ("a factor" vs. "the main reason") rather than
  catching the actual source-mislabeling bug from step 9 - a real,
  honest finding: the retry *mechanism* is sound, but judgment quality is
  bounded by the model doing the verifying. This is exactly why
  `ROLE_MODELS` in `app/config.py` allows swapping a stronger model (e.g.
  GPT-4o) into just the `verifier` role later without touching any
  pipeline code - a natural next experiment once API keys are added.

## 11. FastAPI backend
`app/main.py` wraps the agent in a real web API - one endpoint,
`POST /ask`, that takes a question and returns the answer, its sources
(with scores), and the verification status (`grounded`, `attempts`,
`verification_reason`), so a future frontend can show the user not just
an answer but how confident the system is in it. Also exposes `/health`
and (free from FastAPI) interactive docs at `/docs`.

Verified for real: started the server with `uvicorn app.main:app`, sent an
actual HTTP POST to `/ask`, and got back the correct grounded answer with
full source chunks as JSON - the same result as calling `answer_question()`
directly in Python, now reachable over HTTP.

## 12. Manual testing via /docs, and hardening the verifier
Tried the API by hand through FastAPI's auto-generated `/docs` page and
found two real problems worth fixing:

1. **Honest refusals were wrongly punished.** Asked "What was Q2 revenue?"
   (neither document mentions Q2 at all). The synthesizer correctly said
   "I don't know" every time - no hallucination - but the verifier still
   marked it `NOT_GROUNDED`, because the original prompt only asked "is
   every claim supported," and a refusal doesn't cleanly fit that framing.
   Fixed by explicitly telling the verifier prompt that an honest "the
   context doesn't say" is always a pass. Confirmed fixed: re-ran the same
   question, got `grounded: True` on the first attempt.

2. **The verifier sometimes wrote a verdict that contradicted its own
   stated reason** (e.g. writing a reason that clearly described a pass,
   then outputting `NOT_GROUNDED` anyway). Root cause: the prompt asked
   for `VERDICT` before `REASON`, so the model committed to a conclusion
   before actually reasoning through it. Fixed by reordering the prompt to
   require reasoning first, verdict last, so the verdict is generated
   *after* (and conditioned on) the written-out reasoning. Confirmed
   fixed for the general case: ran the same good/bad test 3 times back to
   back with `temperature=0.0` and got identical, self-consistent results
   every time.

Also reconsidered what "grounded" should even mean: the original prompt
treated citing the wrong specific document (e.g. "the text file" when a
fact was actually in the PDF) as a failure, on the theory that it was
close to the source-mislabeling bug found in step 9. On reflection, that
conflates two different things - **hallucination** (stating something not
actually supported by any of the retrieved documents) versus **citation
accuracy** (correctly saying which specific document a true fact came
from). Only the first one is what the project's hallucination-rate goal
actually cares about. Reworded the prompt to explicitly stop penalizing
correct-fact/wrong-file-label answers, focusing purely on whether facts
are real and unfabricated.

**Honest remaining limitation:** even after both fixes, a follow-up test
still caught the verifier giving `NOT_GROUNDED` to a correct-fact
wrong-file-label answer, with a reason that itself described a pass. So
the verdict/reason self-contradiction problem is *reduced*, not
eliminated. Genuinely fabricated facts, however, were caught reliably and
correctly in every test run tonight (e.g. an invented "50% increase due
to a new office lease" was correctly rejected with an accurate reason).
Conclusion: this is a capability ceiling of `llama3.2` (a small, free,
local ~3B-parameter model used for cost-free development, per
`app/config.py`) doing nuanced self-consistent judgment, not something
further prompt tweaking is likely to fully solve. The documented next
step is unchanged from step 10: swap `ROLE_MODELS["verifier"]` to a
stronger model (e.g. GPT-4o) once API keys are added - no pipeline code
changes required, by design.

## 13. Swapping the verifier to a stronger model (Groq)
Followed through on the plan from step 12: added Groq as a fourth
provider in `app/models/llm_router.py`. Groq's API is OpenAI-compatible,
so this reused the existing `openai` SDK (already a dependency) pointed
at Groq's endpoint instead of writing a new integration - no new pip
package needed. Also fixed a real, separate gap found along the way:
`python-dotenv` had been listed in `requirements.txt` since the very
first commit but nothing ever actually called `load_dotenv()`, so keys
in `.env` were silently never being read. Added that call to
`llm_router.py`.

`ROLE_MODELS["verifier"]` in `app/config.py` now points at
`llama-3.3-70b-versatile` via Groq (a 70-billion-parameter model) instead
of the local 3B `llama3.2` - `synthesizer` and other roles stay on free
local Ollama, since the consistency problem was specific to the judgment
task, not generation.

Re-ran the exact same 3-case test from step 12 (good answer, correct-fact
wrong-source-label answer, genuinely fabricated fact) 3 times back to
back. Every single run, every case, came back correct **and**
self-consistent - the reasoning always matched the verdict, including
the mislabeled-source case explicitly being described as "a minor
labeling slip" rather than a failure, exactly matching the intended
definition of "grounded." Zero contradictions across 9 total
verdict/reason pairs, versus the recurring inconsistencies seen with the
3B model in step 12. Confirms the hypothesis: this was a small-model
capability ceiling, not a flaw in the verification approach itself -
solved by scaling up the model for just this one role, exactly the
tradeoff `ROLE_MODELS` was designed to make easy.

## 14. Fixing citation accuracy in the written answer
Separate from the verifier's internal judgment, the *synthesizer's own
written answer text* still had the original step-9 bug: it would say
"the text file" or "the PDF" in prose, sometimes incorrectly, even though
the underlying fact was true and the retrieval metadata itself was always
accurate (`RetrievedChunk.source` never lies - only the AI's narration
about it could be wrong).

Two changes: (1) `SYNTHESIZER_PROMPT` in `app/agent/graph.py` now
explicitly tells the model that each context chunk is labeled with an
exact bracketed source (e.g. `[data/sample.pdf#0]`), and to cite that
literal label instead of paraphrasing a source name from memory. (2)
`ROLE_MODELS["synthesizer"]` also switched from local `llama3.2` to the
same Groq 70B model now used for `verifier`.

Re-ran the exact question that originally exposed this bug ("What is
driving the operating expenses this quarter?") 3 times. Every run
produced the identical, correct answer, literally citing
`[data/sample.pdf#0]` instead of guessing "text file" - the original bug
is fixed, with the exact real-world case that found it used as the
regression test.

## 15. Re-enabling strict citation checking in the verifier
With the root cause fixed at the source (step 14) and both `verifier` and
`synthesizer` now on the stronger Groq model, re-enabled the citation
accuracy check in `VERIFIER_PROMPT` that had been relaxed back in step
12. The verifier now checks two things again: hallucination (is every
fact actually supported by the context) and citation accuracy (is a fact
attributed to the correct specific source) - both are real correctness
issues, and the earlier relaxation was a workaround for a weak model that
kept getting citation checking itself wrong, not a permanent design
decision.

Re-ran the same 3-case test (good, mislabeled-source, hallucinated) 3
times. Every run correctly returned `True`, `False`, `False` with
accurate, self-consistent reasoning each time (e.g. explicitly naming
"the PDF, not the text file" as the correct source for the mislabeled
case) - the stronger model handles the stricter check reliably, closing
the loop: the verifier is now both a hallucination check and a citation
check, backing up the synthesizer's now-accurate citations as a safety
net rather than a single point of failure.

## 16. React frontend
Built the first real UI: `frontend/` (Vite + React + TypeScript +
Tailwind), a chat interface calling the FastAPI `/ask` endpoint. Includes
a message list with user/assistant bubbles, a "Verified"/"Unverified"
badge reflecting the real `grounded` field, a collapsible sources panel,
and a relevant-excerpt highlighter (`lib/excerpt.ts`) that finds the
best-matching sentence within a source chunk by keyword overlap instead
of showing an arbitrary text cutoff. Later extended with a ChatGPT-style
sidebar (multiple chats, persisted to `localStorage`, create/delete) and
a full visual redesign to a warm, Claude.ai-inspired palette with
`framer-motion` animations throughout (message entrances, sidebar
list/delete transitions, sources panel accordion expand) after initial
feedback that the first dark-theme version felt flat and generic.

## 17. Larger sample documents
Added `data/sample_large.txt` and `data/sample_large.pdf` (~900 words
each, multiple distinct sections) since the original 2 samples were too
short to produce more than 1 chunk each, meaning retrieval had nothing to
meaningfully narrow down between. Verified real narrowing behavior: e.g.
"Was there a security incident?" correctly retrieved specifically
`sample_large.pdf` chunk 2 of 5 (the Security Incidents section), not the
whole document.

## 18. Message router: skipping retrieval for non-document messages
Found via manual testing: sending a plain "Hello" still ran full
retrieval and showed 5 unrelated source chunks marked "Verified" - there
was no step distinguishing a real document question from conversational
chit-chat. Added a `route` node (role=`"router"`, the config had reserved
this role since the project's first commit but nothing used it until
now) that classifies each message, branching to either a direct
conversational reply (no retrieval, no verification, no sources) or the
existing retrieve/synthesize/verify loop. Confirmed: greetings and
"thanks" correctly skip retrieval entirely (0 chunks), real questions are
unaffected.

## 19. Hardening the verifier against multi-claim distortion
Manual testing surfaced a serious gap: a dense, multi-fact answer
("tell me about Q2") contained two real errors - a revenue comparison
that conflated a year-over-year stat with a quarter-over-quarter one, and
an SMB revenue trend with the direction inverted (said "up" when the
source said "down") and attributed to a fabricated "Q1" reference - and
the verifier still marked it `Verified`. Root cause: the verifier judged
answers holistically rather than checking each individual claim, and
strayed further once the answer's claim count grew.

Fix: rewrote `VERIFIER_PROMPT` to require an explicit numbered
claim-by-claim breakdown before any verdict, with specific instructions
to check comparison direction and reference period for each claim, not
just whether the same numbers appear somewhere in the context. Confirmed
fixed, 3/3 consistent runs.

This surfaced a **false alarm** worth recording: an early version of this
fix appeared to break the working citation-accuracy check from step 15
(a mislabeled-source case started passing again). Investigating properly
- by directly inspecting file contents rather than re-guessing at prompts
- found the real cause: `sample_large.txt` (step 17) happened to reuse
near-identical wording from the original `sample.pdf`, so the "wrong"
citation in the test was no longer actually wrong once both documents
were in the same index. The verifier was right; the test had gone stale.
Rewrote the test against a fact confirmed (by directly loading and
grep-checking the source files) to be unique to one document, and
re-confirmed both the citation check and the new multi-claim check pass
reliably together, 3/3 runs. Lesson: when a previously-passing test
starts failing after an unrelated change, verify the test's assumptions
against current reality before assuming the code regressed.

## 20. Fixing the "honest refusal" exception being too permissive
Manual testing: asked "what is 1+1" (obviously outside the indexed
documents). The synthesizer replied that the context doesn't contain the
answer - correctly - and then answered anyway from general knowledge
("the answer to 1+1 is 2"), which directly violates its own instruction
to say so instead of guessing. Worse: the verifier still marked this
`Verified`. Its own stated reason gave away the bug: it admitted the
answer "does provide an unsolicited true fact" and passed it anyway.

Root cause: the honest-refusal exception in `VERIFIER_PROMPT` said an
answer passes if it "states the context lacks the info and does not
invent an answer anyway" - the model was reading "invent" narrowly as
"lie about what's in the context," not "add any claim not sourced from
the context at all," so a refusal-plus-outside-knowledge-guess slipped
through as if it were a pure refusal.

Fix: rewrote the exception to require that refusing is *all* the answer
does - the moment it supplies any value beyond that, even something as
obviously true as "1+1 is 2," it no longer qualifies, and gets checked
as a normal unsupported claim (which correctly fails, since it isn't in
the context). Verified 3/3 runs on both the bug case (now correctly
`NOT_GROUNDED`) and a genuine pure-refusal case (still correctly
`GROUNDED`) - no regression.
