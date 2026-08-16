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

## 21. Tightening the synthesizer's refusal wording
Step 20 fixed the verifier catching this case, but the underlying
question - the CSK trophies question and 1+1 both showed it - was that
the synthesizer's own refusals were poor quality even when caught
correctly: it would ramble describing what the context *is* about
("the context appears to be related to a company's quarterly report,
discussing revenue...") instead of just saying it doesn't know, and for
1+1 specifically it kept tacking "the answer is 2" onto the end despite
already being told not to guess.

Rewrote `SYNTHESIZER_PROMPT` to require that a refusal be *only* a short,
direct "I don't have that information" - no context summary, no
explanation, and an explicit ban on supplying an answer from outside
general knowledge, calling out arithmetic specifically since that was
the exact case that slipped through. Verified: both the CSK and 1+1
questions now produce a one-sentence "I don't have that information."
and pass immediately (`grounded=True, attempts=0`) instead of needing
the verifier to catch and retry a bad first attempt.

## 22. A third route: honestly-labeled general knowledge
After step 21, "what is 1+1" correctly refused - but that raised a real
design question: is flatly refusing trivial general knowledge actually
the right behavior, or just annoying? The tempting fix (let the verifier
be lenient about "obviously safe" general knowledge) was rejected - that
would dilute what "Verified" means for every other answer, since the
line between "safe to guess" and "risky ungrounded claim" is exactly the
ambiguity this project exists to remove.

The better fix: a third router category, `GENERAL_KNOWLEDGE`, alongside
the existing `DOCUMENT_QUESTION`/`CHITCHAT` split. Router prompt updated
to a 3-way classification; `route_type` (a string) replaces the old
`is_chitchat` boolean throughout the state, API response, and frontend
types, since a boolean couldn't represent three routes. Matching
questions get answered directly and honestly badged in the UI as
"General knowledge — not from your documents" (a neutral gray badge,
distinct from green "Verified" and amber "Unverified") - `grounded` is
explicitly `False` for these by design, since they genuinely aren't
grounded in the indexed documents; the badge is what makes that honest
rather than confusing.

Also added `is_refusal` tracking (checks if the synthesizer's answer is
the exact short refusal phrase) for two reasons: (1) the frontend now
hides the sources panel entirely on a refusal, since retrieved-but-unused
chunks aren't meaningful evidence for an "I don't know," and (2) the
graph now skips the retry loop immediately on a refusal rather than
spending 2 retries rewriting a query that was never going to find an
answer that doesn't exist - a real efficiency win, relevant after
today's Groq quota exhaustion from heavy testing.

Verified 5 cases end to end: chitchat (no sources, friendly reply),
general knowledge x2 (1+1 -> "2", CSK trophies -> a real fact, both
honestly un-badged as unverified), a normal document question (unchanged
behavior), and an out-of-scope-but-plausible business question
(correctly stayed on the document path and refused honestly, sources now
hidden).

## 23. Fixing a real "stuck on Thinking..." bug
Manual testing: a question hit Groq's daily quota again mid-request, and
the UI just sat on "Thinking..." forever instead of showing an error.
Checked the actual server logs (not guessed) and found the real cause:
`app/main.py`'s `/ask` endpoint had no exception handling at all, so an
unhandled `RateLimitError` produced an ungraceful failure the frontend
couldn't parse cleanly - and separately, the frontend's own error path
was already broken: `api.ts` discarded the response body on a failed
request instead of reading it, and `App.tsx`'s catch block used a bare
`catch {}` that threw away whatever error it caught in favor of one
hardcoded generic message regardless of the real cause.

Three-part fix: (1) `/ask` now catches `RateLimitError` specifically and
returns a proper `503` with a clear message, plus a generic `500`
fallback for anything else - confirmed the response is fast (under 1s)
and parseable instead of a generic unhandled error. (2) `api.ts` now
reads the response body and surfaces the backend's actual `detail`
message. (3) `App.tsx`'s catch block now uses the real caught error's
message instead of discarding it. Together this turns an indefinite,
unexplained "stuck" state into an honest, specific error message the
user can actually act on.

## 24. Evaluation harness (built, not yet validated with a live run)
Built the actual measurement behind this project's core claim, instead
of leaving "reduces hallucination" as an unverified assertion.
`app/eval/cases.py` defines 11 hand-written test cases with ground truth
verified by directly re-reading all four indexed documents in full (not
guessed) - 7 answerable questions with specific expected facts (exact
figures like "4.2 million," "108 percent," "142" employees), and 4
questions the documents genuinely don't answer (including the "Q2
revenue" and "1+1" cases already investigated in steps 20-22).
`app/eval/scorer.py` scores each run: for answerable cases, hallucinated
if any expected fact is missing from the answer, or if the system
refused something it should have answered; for unanswerable cases,
hallucinated only if the system gave a confident document-grounded
answer instead of refusing or routing to general knowledge.
`scripts/run_eval.py` runs the full set (or a `[limit]` subset) through
the real agent, prints per-case results, and writes a full JSON report.

Deliberately kept to 11 cases, not a much larger set: each question can
cost thousands of tokens once retries are counted (worked out in detail
earlier today), so a bigger batch risked exceeding the entire daily free
quota in a single run, not just needing a short wait.

Honest status: attempted to validate on a 2-case subset and immediately
hit the same Groq daily quota wall (99,669/100,000 used, no headroom
left at all from today's heavy testing). The harness code itself is
confirmed sound - it ran correctly through routing, retrieval, and the
first LLM call before failing on the actual network request, and all
modules import cleanly with no errors - but a real end-to-end run with
actual hallucination-rate numbers has not happened yet. That's the
immediate next step once quota is available again.

## 25. First real eval run: 9.1%, then expanded to a categorized 39-case set
Once quota freed up, ran the 11-case harness for real for the first
time: **9.1% hallucination rate (1/11)**. The one failure was itself
informative, not a mystery: "What was Q2 revenue?" produced a live
calculation from the stated year-over-year growth figure (4.2 / 1.12 =
3.75 million) - the exact conflation-of-comparison-periods error
investigated in step 19, just resurfacing on a different specific
phrasing. 10/11 correct, including all 7 answerable questions and 3/4
unanswerable ones handled correctly.

Discussed whether 9.1% needed to be "improved" before it's usable - the
conclusion: no. A suspiciously perfect 0% would look less credible in an
interview than an honest number with one well-understood failure mode.
The real gap was elsewhere: 11 cases is a small, mostly one-shaped test
set (simple factual lookups). Redesigned `app/eval/cases.py` to 39 cases
across 5 categories that each stress a different part of the pipeline:
15 simple lookups, 10 paraphrased (same facts, deliberately different
wording, to stress dense vs. BM25 retrieval differently), 5 multi-hop
(answer requires combining facts from two different chunks or
documents), 6 unanswerable/adversarial (the most important category for
this project specifically), and 3 exact-figure lookups. `run_eval.py`
now reports hallucination rate per category, not just one aggregate
number, and every new fact was verified by re-reading all four source
documents in full again, not assumed correct from memory.

Also made the harness genuinely resumable: hitting the daily quota
mid-run used to mean losing the whole run's results (or, after the step
24 resilience fix, at least not crashing, but still re-spending tokens
on already-answered questions on the next attempt). `run_eval.py` now
reads any existing `eval_results.json`, skips questions already scored,
and only spends new quota on cases not yet run, merging results into a
cumulative report across multiple passes.

Honest current status: across three separate attempts (including one on
a fresh day, after the quota's rolling 24-hour window had time to
partially recover), only **7 of the 39 cases have actually run** -
`simple_lookup` questions only, 0% hallucination on all 7. The categories
that matter most for proving this project's actual claim - paraphrased
wording, multi-hop reasoning, and especially the unanswerable/adversarial
set - have not been scored yet, blocked purely by Groq free-tier daily
quota, not by any code issue. Next session: keep resuming with
`run_eval.py` until all 39 are scored, or consider the paid tier if
waiting stays impractical.

## 26. Spreadsheet ingestion, and a real BM25 tokenization bug it surfaced
Started on the multimodal document router (still-open roadmap item):
spreadsheets first, since unlike scanned-PDF OCR it needs no LLM calls
and carries no quota risk. `load_spreadsheet()` in `app/ingestion/loaders.py`
reads `.csv`/`.xlsx`/`.xls` via `pandas`, turning each row into a
"Column: value, Column: value" line - readable prose for chunking, not a
raw table dump. `load_document()`'s dispatcher now routes these
extensions there. Added `data/sample_expenses.csv` (a monthly
expense-by-department breakdown) as real test data and indexed it
alongside the existing documents.

Testing retrieval on it surfaced a genuine bug, not a spreadsheet-specific
one: asking "How much was spent on marketing campaigns in August?" didn't
return the CSV chunk in the top 3 results at all, despite it containing
those exact words. Traced it to `app/retrieval/sparse.py`'s BM25
tokenizer, which has used plain `.lower().split()` since it was first
built - this leaves punctuation glued to words, so `"august,"` (from a
comma-delimited CSV row) and `"august?"` (from a naturally-phrased
question) are different tokens and never match. This was always a latent
issue (flagged as a known simplification in `chunker.py`'s docstring
early in the project) but never actually caused a visible problem until
now, since spreadsheet rows are far more comma-dense than prose.

Fixed by replacing the tokenizer with a regex that extracts only
alphanumeric tokens (`re.findall(r"[a-z0-9]+", text.lower())`), applied
consistently to both indexing and querying. Verified precisely: before
the fix, BM25 ranked the CSV chunk 8th out of 13 for that query (score
1.60); after the fix, it ranked 1st, more than double the next result
(score 6.32, vs. 2.86). This is a real quality improvement to hybrid
search generally, not just for spreadsheets - any query or document with
different punctuation around shared words was affected.
