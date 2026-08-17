# VerifiedRAG — Development Log

Notes to myself as I build this, so I don't forget why I made a decision
or how I found/fixed a bug. Mostly useful for when I have to explain this
project later (interview, whatever) and want the real story instead of a
vague "yeah it works."

## 1. Project scaffolding
`.gitignore`, `README.md`, `requirements.txt`, `.env.example`. No code
yet, just the basic setup every repo needs before I touch anything real.

## 2. Model abstraction layer
`app/config.py` + `app/models/llm_router.py`. Every agent calls one
function, `call_llm(role, messages)`, and a config dict decides which
provider (Ollama locally, or OpenAI/Anthropic) actually handles that
role. I wanted swapping a model later to be a one-line config change,
not a code change — turned out to matter a lot more than I expected
(see step 13, 28).

## 3. Document ingestion
`app/ingestion/loaders.py` (PDF/text → plain string) and `chunker.py`
(splits text into overlapping word-window chunks, so an answer that
straddles a chunk boundary doesn't get cut in half). Tested via
`scripts/test_ingestion.py` against `data/sample.txt` and `data/sample.pdf`
(two short Q3 financial docs I made up as sample data, used everywhere
below).

## 4. Dense embeddings
`app/retrieval/embeddings.py` wraps `fastembed` (ONNX, not torch —
smaller footprint, I was thinking ahead to Docker) using
`BAAI/bge-small-en-v1.5`. Turns text into 384-number vectors so
semantically similar text ends up numerically close. Smoke-tested by
embedding a couple of sample strings and checking the output shape.

## 5. Vector store (dense/semantic search)
`app/retrieval/vector_store.py` wraps **Qdrant** in local embedded mode
(`QdrantClient(path=...)`, no separate server). `add_chunks()` embeds and
stores; `dense_search()` embeds a query and returns nearest matches by
cosine similarity. I originally planned to use ChromaDB but swapped to
Qdrant mid-build for the embedded mode and the fastembed pairing. Tested
with a tiny 3-sentence set — a query about the Eiffel Tower correctly
ranked the Eiffel Tower sentence top.

## 6. Sparse search (BM25 keyword search)
`app/retrieval/sparse.py`, classic keyword ranking, no AI involved. It
rebuilds its index in memory from whatever's already in Qdrant instead
of keeping a second copy of the documents around. Tested with a "Python
programming language" query, which correctly ranked the Python sentence
top by literal word overlap.

## 7. Hybrid search (RRF fusion)
`app/retrieval/hybrid.py` combines dense + BM25 rankings using
Reciprocal Rank Fusion — merges by rank position rather than raw score,
since cosine similarity and BM25 scores aren't comparable numbers.
`hybrid_search()` is the one function I call for retrieval everywhere
else in the project.

## 8. Real end-to-end retrieval test
`scripts/build_index.py` and `scripts/test_hybrid.py`. Ran real
questions through `hybrid_search()` against the two sample docs and
checked the results actually made sense: "risk factors" and "operating
expenses" questions correctly ranked the PDF higher (that content's only
in there); "SMB segment" ranked the `.txt` file higher; "What was Q3
revenue?" came back a near-tie, which is correct since both files state
that fact.

## 9. LangGraph retrieve → synthesize agent (baseline loop)
`app/agent/graph.py` wires `hybrid_search()` and
`call_llm(role="synthesizer", ...)` into a two-node graph: retrieve →
synthesize. Kept it deliberately dumb for now, no verification yet.
Had to install `langgraph` (it pulls in `langchain-core`, but not the
full LangChain framework) and get Ollama running locally with `llama3.2`
pulled — wasted a bit of time on a mismatch with an older `llama3` pull
I already had.

Tested with two real questions:
- "What was Q3 revenue...?" → correct, grounded answer.
- "What is driving operating expenses...?" → the facts were right, but
  it said "the text file" when that sentence was actually from the PDF.
  Not a retrieval bug — it pulled the right chunks — the model was just
  being loosely accurate instead of strictly grounded. This is basically
  a live demo of the exact problem I'm about to build a fix for.

## 10. Verifier / self-correction loop
The actual point of this whole project. `app/agent/verify.py` adds a
separate LLM call (role `"verifier"`) that judges whether a synthesized
answer is genuinely backed by the retrieved context. Tested it standalone
first against the real "right facts, wrong source" case from step 9, and
it correctly told the two apart (`grounded: True` vs `False`).

Rewired `graph.py` into the full loop: retrieve → synthesize → verify,
with a branch — if not grounded, `rewrite_query` (new LLM call, role
`"query_rewrite"`) rephrases the search and it retries, capped by
`max_attempts` so it can't loop forever.

Checked two behaviors:
- Easy question ("What was Q3 revenue?"): passed on the first try, 0
  retries — good, it's not retrying when it doesn't need to.
- Hard question ("What is driving operating expenses...?"): failed all 3
  attempts, hit the cap, and correctly returned the best-effort answer
  flagged `grounded: False` instead of pretending it worked. Watching the
  steps stream by, the verifier's rejection reason was kind of nitpicky
  each time ("a factor" vs "the main reason") rather than catching the
  actual source-mislabeling bug from step 9. Honestly a useful thing to
  find: the retry mechanism works, but it's only as good as the judgment
  of whatever model is doing the verifying. Which is exactly why I built
  `ROLE_MODELS` to let me swap a stronger model into just the `verifier`
  role later — I knew I'd need this.

## 11. FastAPI backend
`app/main.py` — one endpoint, `POST /ask`, takes a question and returns
the answer plus sources and verification status (`grounded`, `attempts`,
`verification_reason`) so a future frontend can show not just an answer
but how sure the system actually is. Also `/health` and free interactive
docs at `/docs` (nice FastAPI perk).

Tested for real: started the server, sent an actual HTTP POST to `/ask`,
got back the correct grounded answer with full source chunks as JSON —
same result as calling `answer_question()` directly in Python, now
reachable over HTTP.

## 12. Manual testing via /docs, and hardening the verifier
Poked at the API by hand through `/docs` and found two real problems.

**Honest refusals were being wrongly punished.** Asked "What was Q2
revenue?" (neither doc mentions Q2 at all). The synthesizer correctly
said "I don't know" — no hallucination — but the verifier still marked
it `NOT_GROUNDED`, because my original prompt only asked "is every claim
supported" and a refusal doesn't cleanly fit that framing. Fixed by
telling the verifier explicitly that an honest "the context doesn't say"
is always a pass. Re-ran the same question and got `grounded: True` on
the first try.

**The verifier sometimes contradicted itself** — writing a reason that
clearly described a pass, then outputting `NOT_GROUNDED` anyway. Turned
out my prompt asked for `VERDICT` before `REASON`, so the model was
committing to a conclusion before it had actually reasoned through
anything. Reordered it so reasoning comes first and the verdict follows
from it. Ran the same good/bad test 3 times at `temperature=0.0` and got
identical, self-consistent results every time.

Also rethought what "grounded" should even mean. My original prompt
treated citing the wrong document (e.g. "the text file" when it was
really the PDF) as a failure, since it felt close to the step 9 bug. On
reflection that's conflating two different things — hallucination
(stating something not actually in any retrieved doc) vs. citation
accuracy (naming the right specific source for a true fact). Only the
first one is what I actually care about for a hallucination-rate metric.
Reworded the prompt to stop penalizing correct-fact/wrong-file-label
answers and focus purely on whether facts are real.

**Still not fully fixed, and I want to be honest about that.** Even
after both changes, a follow-up test caught the verifier still marking a
correct-fact/wrong-file-label answer `NOT_GROUNDED`, with a reason that
itself described a pass. So the self-contradiction thing is reduced, not
gone. Actual made-up facts, though, got caught reliably every time (e.g.
an invented "50% increase due to a new office lease" was correctly
rejected with an accurate reason). My read: this is a capability ceiling
of `llama3.2` (a small free local ~3B model) doing this kind of
self-consistent judgment, not something more prompt tweaking is going to
fix. Sticking with the plan from step 10 — swap `ROLE_MODELS["verifier"]`
to something stronger once I have API keys.

## 13. Swapping the verifier to a stronger model (Groq)
Added Groq as a fourth provider in `llm_router.py`. Groq's API is
OpenAI-compatible so I just pointed the existing `openai` SDK at their
endpoint instead of writing a whole new integration. Also caught a real
gap while I was in there: `python-dotenv` had been sitting in
`requirements.txt` since my very first commit, but nothing ever actually
called `load_dotenv()` — my `.env` keys were silently never being read.
Fixed that too.

`ROLE_MODELS["verifier"]` now points at `llama-3.3-70b-versatile` via
Groq instead of local `llama3.2` — kept `synthesizer` on free Ollama
since the consistency problem was specific to judgment, not generation.

Re-ran the same 3-case test from step 12 (good / wrong-source / made-up)
3 times back to back. Every run, every case, correct **and**
self-consistent — the reasoning matched the verdict every time, even
correctly calling the mislabeled-source case "a minor labeling slip"
instead of a failure. Zero contradictions across 9 verdict/reason pairs.
Confirms my theory from step 12 — small-model capability ceiling, not a
flaw in the approach.

## 14. Fixing citation accuracy in the written answer
Separate from the verifier's own judgment, the synthesizer's actual
written text still had the step-9 bug — it would say "the text file" or
"the PDF" in prose, sometimes wrong, even though the underlying fact was
true and the retrieval metadata itself never lies about where a chunk
came from.

Two changes: told `SYNTHESIZER_PROMPT` that each chunk is labeled with an
exact bracketed source (e.g. `[data/sample.pdf#0]`) and to cite that
literal label instead of guessing a source name from memory; switched
`synthesizer` to the same Groq model now used for `verifier`.

Re-ran the exact question that exposed this bug ("What is driving the
operating expenses this quarter?") 3 times. Every run, identical correct
answer, literally citing `[data/sample.pdf#0]` — bug's fixed, and I used
the real case that found it as my regression test.

## 15. Re-enabling strict citation checking in the verifier
With the root cause fixed and both roles on the stronger model,
re-enabled the citation check I'd relaxed in step 12. Now checking two
things again: hallucination and citation accuracy, both legit concerns —
the earlier relaxation was a workaround for a weak model, not a real
design decision.

Re-ran the same 3-case test 3 times. Every run: `True`, `False`, `False`,
consistent reasoning, explicitly naming "the PDF, not the text file" for
the mislabeled case. The stronger model handles the stricter check fine.

## 16. React frontend
Built the actual UI: `frontend/` (Vite + React + TypeScript + Tailwind).
Chat interface hitting `/ask`. Message bubbles, a Verified/Unverified
badge tied to the real `grounded` field, a collapsible sources panel, and
a relevant-excerpt highlighter (`lib/excerpt.ts`) that finds the
best-matching sentence in a chunk by keyword overlap instead of just
cutting off text arbitrarily. Later added a ChatGPT-style sidebar
(multiple chats, saved to `localStorage`) and redid the whole visual
style — warm Claude.ai-ish palette with `framer-motion` animations —
after the first dark-theme pass felt flat.

## 17. Larger sample documents
Added `data/sample_large.txt` and `data/sample_large.pdf` (~900 words
each) because my first two samples were too short to ever split into
more than 1 chunk, so retrieval had nothing to actually narrow down
between. Checked real narrowing: "Was there a security incident?"
correctly pulled specifically chunk 2 of 5 from `sample_large.pdf` (the
Security Incidents section), not the whole doc.

## 18. Message router: skipping retrieval for non-document messages
Found this by just typing "Hello" into the chat — it still ran full
retrieval and showed me 5 unrelated source chunks marked "Verified."
Nothing was distinguishing a real document question from small talk.
Added a `route` node (role `"router"` — I'd reserved this in config since
day one but never actually used it) that classifies each message and
branches to a direct reply or the retrieve/synthesize/verify loop.
Confirmed greetings and "thanks" now skip retrieval entirely.

## 19. Hardening the verifier against multi-claim distortion
Asked "tell me about Q2" and got a dense multi-fact answer with two real
errors — a revenue comparison that mixed up year-over-year with
quarter-over-quarter, and an SMB trend with the direction flipped (said
"up" when the source said "down") plus a made-up "Q1" reference — and the
verifier still marked it `Verified`. It was judging answers holistically
instead of checking each claim, and got worse the more claims there
were.

Rewrote `VERIFIER_PROMPT` to force an explicit numbered claim-by-claim
breakdown before any verdict, specifically checking comparison direction
and time period per claim, not just "do these numbers appear somewhere."
Confirmed fixed, 3/3.

**False alarm worth writing down.** An early version of this fix looked
like it broke the citation check from step 15 — a mislabeled-source case
started passing again. Checked properly instead of guessing at the
prompt some more, and found the real cause: `sample_large.txt` (step 17)
happened to reuse near-identical wording from `sample.pdf`, so the
"wrong" citation in my test wasn't actually wrong anymore once both docs
were in the index. The verifier was right, my test had just gone stale.
Rewrote the test against a fact I confirmed (by grepping the source
files directly) was unique to one doc, and both checks passed together,
3/3. Lesson for myself: when something that used to pass starts failing
after an unrelated change, check the test's assumptions before assuming
I broke the code.

## 20. Fixing the "honest refusal" exception being too permissive
Asked "what is 1+1" (obviously not in my docs). The synthesizer said the
context doesn't have it — correct — then answered anyway from general
knowledge ("the answer to 1+1 is 2"), directly against its own
instructions. Worse, the verifier still marked it `Verified`, and its own
stated reason gave the bug away: it literally admitted the answer
"provides an unsolicited true fact" and passed it anyway.

The honest-refusal exception said an answer passes if it "states the
context lacks the info and does not invent an answer anyway" — the model
was reading "invent" narrowly as "lie about the context" rather than "add
anything not sourced from it," so a refusal-plus-guess slipped through as
if it were a clean refusal.

Fixed by requiring refusing to be *all* the answer does — the second it
adds any value at all, even something obviously true, it stops counting
as a refusal and gets checked as a normal claim (which fails correctly,
since it's not in the context). 3/3 on both the bug case and a genuine
pure refusal, no regression.

## 21. Tightening the synthesizer's refusal wording
Step 20 fixed the verifier side, but the underlying issue — same CSK
trivia and 1+1 questions showed it — was that the synthesizer's refusals
were just bad even when caught correctly: rambling about what the context
*is* about instead of saying it doesn't know, and for 1+1 specifically
still tacking "the answer is 2" on the end.

Rewrote `SYNTHESIZER_PROMPT` to require a refusal be *only* a short
direct "I don't have that information" — no summary, no explanation, and
an explicit no on guessing from outside knowledge, calling out arithmetic
by name since that's exactly what slipped through. Both questions now
give a clean one-liner and pass immediately, no retry needed.

## 22. A third route: honestly-labeled general knowledge
After step 21, "what is 1+1" correctly refuses — but that raised a real
question: is flatly refusing trivial general knowledge actually the
right call, or just annoying? I considered letting the verifier be
lenient about "obviously safe" stuff, but rejected that — it would dilute
what "Verified" means everywhere else, since the line between "safe to
guess" and "risky claim" is exactly the thing this whole project exists
to remove.

Better fix: a third router category, `GENERAL_KNOWLEDGE`, next to
`DOCUMENT_QUESTION`/`CHITCHAT`. `route_type` (a string) replaced the old
`is_chitchat` boolean since a boolean can't hold three states. These
questions now get answered directly and honestly badged "General
knowledge — not from your documents" (neutral gray, not the green
Verified badge) — `grounded` is explicitly `False` for these by design,
since they really aren't grounded in my docs; the badge is what keeps
that honest instead of confusing.

Also added `is_refusal` tracking — hides the sources panel on a refusal
(retrieved-but-unused chunks aren't real evidence for "I don't know"),
and skips the retry loop immediately on a refusal instead of burning 2
retries rewriting a query that was never going to find something that
doesn't exist. Tested 5 cases end to end and all behaved as expected.

## 23. Fixing a real "stuck on Thinking..." bug
Hit Groq's daily quota mid-request and the UI just sat on "Thinking..."
forever instead of showing an error. Checked the actual server logs
instead of guessing and found `/ask` had zero exception handling, so an
unhandled `RateLimitError` produced a mess the frontend couldn't parse —
and separately, the frontend's own error handling was already broken:
`api.ts` threw away the response body on failure, and `App.tsx`'s catch
block discarded whatever it caught in favor of one hardcoded message.

Fixed all three: `/ask` now catches `RateLimitError` and returns a clean
`503`, plus a generic `500` fallback; `api.ts` reads and surfaces the
real error detail; `App.tsx` uses the actual caught message. Turned an
unexplained stuck state into a real error the user can act on.

## 24. Evaluation harness (built, not yet validated with a live run)
Built the actual measurement behind my hallucination-rate claim instead
of just asserting it. `app/eval/cases.py`: 11 hand-written questions with
ground truth I checked by re-reading all four docs myself — 7 answerable
with specific expected facts, 4 the docs genuinely don't answer.
`scorer.py` scores each run; `run_eval.py` runs the set and writes a JSON
report.

Kept it to 11 cases on purpose — each question can cost thousands of
tokens with retries, and I'm on a free daily quota, so a bigger batch
risked blowing the whole thing in one run.

Tried to validate on 2 cases and immediately hit the Groq quota wall
(99,669/100,000 used from today's testing). The harness code itself ran
fine up to the actual network call, so I know it's sound — just no real
numbers yet.

## 25. First real eval run: 9.1%, then expanded to a categorized 39-case set
Once quota freed up, ran it for real: 9.1% (1/11). The one failure was
useful, not random — "What was Q2 revenue?" produced a live calculation
off the year-over-year growth figure, the same comparison-period mixup
from step 19 resurfacing under different phrasing.

Talked myself through whether 9.1% needed to look better before I'd trust
it — decided no. A suspiciously perfect 0% would actually look less
credible than an honest number with one well-understood failure. The
real gap was that 11 cases is a small, mostly-one-shaped set. Expanded
`cases.py` to 39 across 5 categories that each stress something
different: 15 simple lookups, 10 paraphrased (same facts, different
wording, to stress dense vs. BM25 differently), 5 multi-hop, 6
unanswerable/adversarial (the category that matters most for what this
project claims to do), 3 exact-figure. `run_eval.py` now reports
hallucination rate per category, and I re-verified every fact against the
source docs again rather than trust my memory.

Also made the harness resumable — hitting quota mid-run used to mean
losing everything (or at least not crashing, after step 24's fix, but
still re-spending tokens on stuff I already had answers for).
`run_eval.py` now skips already-scored questions and merges into a
cumulative report.

Ended this session at 7/39 actually run (simple lookups only, 0%), the
categories that matter most still untested, blocked purely by quota.

## 26. Spreadsheet ingestion, and a real BM25 tokenization bug it surfaced
Started on multimodal ingestion — spreadsheets first since they need no
LLM calls, no quota risk. `load_spreadsheet()` reads `.csv`/`.xlsx`/`.xls`
via pandas, turning each row into a "Column: value" line instead of a raw
table dump. Added `data/sample_expenses.csv` and indexed it.

Testing it surfaced a real bug that had nothing to do with spreadsheets
specifically: "How much was spent on marketing campaigns in August?"
didn't return the CSV chunk in the top 3 at all, even though it literally
contains those words. Traced it to my BM25 tokenizer, which has just used
`.lower().split()` since I first wrote it — that leaves punctuation glued
to words, so `"august,"` and `"august?"` are different tokens and never
match. I'd actually flagged this as a known simplification way back in
`chunker.py`'s docstring, but it never actually bit me until spreadsheet
rows (way more comma-dense than prose) exposed it.

Fixed with a regex tokenizer that only pulls out alphanumeric chunks.
Checked precisely: before the fix the CSV chunk ranked 8th out of 13 for
that query; after, it ranked 1st by a wide margin. This helps hybrid
search generally, not just spreadsheets.

## 27. Scanned-PDF OCR via a vision model
Second half of multimodal ingestion. Checked pricing before building
anything — none of Groq, OpenAI, or Anthropic have a free vision model
right now; Groq's (`qwen/qwen3.6-27b`) is paid preview. Decided to eat
the small cost since there's no free option with the providers I already
have set up.

`app/ingestion/vision.py` sends a base64 image through
`call_llm(role="vision_ocr", ...)` — didn't even need to touch
`llm_router.py` since it just passes messages through as-is. `load_pdf()`
now checks each page's extracted text length and routes short-text pages
(likely scanned) through OCR instead of pypdf.

Built a real test file instead of assuming it'd work — rendered text onto
an image, embedded it in a PDF with no text layer (confirmed via pypdf
extracting exactly 0 characters — a genuinely fake "scan," not just a
normal PDF). First OCR test worked but the model — a "thinking" model —
leaked its raw reasoning in `<think>` tags despite being told not to.
Fixed by stripping those tags. Re-tested, clean output, indexed it for
real, and it correctly ranked #1 for a question about its content.

## 28. Groq deprecated my text model out from under me
Trying to pick the eval harness back up, every call started failing with
`model_not_found` instead of the usual rate limit — clearly a different
problem. Checked properly: Groq deprecated `llama-3.3-70b-versatile` (the
model every real role had been using since step 13) literally the day
before I noticed. Their recommended replacement is `openai/gpt-oss-120b`,
also free-tier, with a notably bigger daily quota.

Updated all four roles. Verified in two steps before trusting it — a raw
call succeeded, then a full `answer_question()` run through the whole
graph also succeeded with a correct answer. Lesson for future me: a
sudden `model_not_found` after hours of things working fine means check
for a provider-side deprecation, don't just assume I broke something.

## 29. Windows console crash, a scorer bug, and the final eval result: 0%
Resuming the harness with the new model, `run_eval.py` crashed outright
mid-print with a `UnicodeEncodeError` — Windows' console can't display a
lot of Unicode characters LLMs commonly output. Fixed by forcing UTF-8 on
stdout at the top of the script.

Re-running surfaced something more interesting: 11 of 38 cases came back
"HALLUCINATED," 28.9%. But reading the actual flagged answers, several
plainly *contained* the fact they were supposedly missing. Checked the
raw bytes instead of trusting the number and found `openai/gpt-oss-120b`
writes numbers with a narrow no-break space instead of a regular space —
so "1.3 million" in the answer never literally matched my ASCII "1.3
million" keyword, even though no human would notice a difference. Same
issue from a different angle broke refusal detection: the model uses a
curly apostrophe in "don't," which never matched my straight-ASCII prefix
check. One more case failed for an unrelated but real reason — the model
wrote "108%" where my test expected "108 percent."

Fixed properly: added `app/text_utils.py` to normalize this whole class
of "smart typography" to plain ASCII, used consistently in both refusal
detection and keyword scoring. Loosened the two percentage test cases to
just "108" so either format matches.

Instead of re-spending quota re-answering 38 questions I already had
correct answers for, wrote `scripts/rescore_eval.py` — re-applies the
fixed scorer to already-collected answers with zero new LLM calls, since
the bug was in my measurement, not in what the agent actually said. All
11 false positives flipped to correctly-passing, and importantly nothing
else changed, which told me the fix was precise and not just more
lenient across the board. Ran the one case that had hit a rate limit
blip, completing all 39.

**Final result: 39/39 scored, 0.0% hallucination, across all five
categories.** I want to be honest about why I actually believe this
number instead of being suspicious of it: I didn't get here by loosening
what counts as a pass — every fix this step was a precise correction to
a specific, root-caused bug in my scoring, verified not to touch any
other case. The agent's real answers were correct in all 11 originally-
flagged cases the whole time; only my scoring was broken. Still worth
remembering: 39 cases is a real but modest sample, not a big benchmark.

## 30. Spot-checking historical fixes against the new model, and a real router miss
Swapping the model (step 28) is exactly the kind of change that deserves
re-checking known-risky scenarios directly instead of just trusting the
clean aggregate number, so I re-ran three of my earlier bug cases
specifically against `openai/gpt-oss-120b`.

Two turned out fine. The citation test (step 15) looked like a
regression at first — verifier said `Verified` on a fake "according to
the text file" answer I fed it — but checking the actual retrieved chunk
showed `sample_large.txt` genuinely contains that phrase now (added in
step 17), same stale-test situation as step 19, not a real regression.
The strict-refusal behavior (step 21) also held up fine on a clean,
unambiguous Q2 question.

One was real and new: "tell me about q2" got classified
`GENERAL_KNOWLEDGE` and answered with a dictionary definition of what a
fiscal quarter is, instead of checking the docs — different from how the
old model handled it. My router prompt only said to use general
knowledge when a question was "unrelated" to the documents, without
saying which way to guess on genuinely ambiguous phrasing. For a tool
whose entire indexed content is a company's quarterly reports, "Q2" isn't
a neutral word.

Fixed by rewriting the prompt to explicitly bias ambiguous-but-plausible
business references toward `DOCUMENT_QUESTION`, keeping
`GENERAL_KNOWLEDGE` for things with no plausible connection to business
content at all. Verified: "tell me about q2" now correctly hits the
document path and honestly refuses, and my two genuine general-knowledge
controls (1+1, CSK trophies) still route correctly — so the fix was
targeted, not an overcorrection.

## 31. An honest gap: no baseline ablation existed before I trusted "0%"
Got asked a fair question I hadn't actually answered myself: had I ever
run the same 39 cases *without* the verifier/retry loop, to show what it
actually contributes instead of just assuming it matters? No — every eval
run so far went through the full pipeline. Built it properly rather than
hand-wave an answer: `build_graph()`/`answer_question()` now take a
`with_verification` flag; `False` compiles a genuinely smaller graph
(route → retrieve → synthesize → stop, verify/retry nodes never even
added), not a fake simulation of skipping them.
`scripts/run_eval_baseline.py` mirrors the resumable pattern against a
separate results file so it can't touch my real numbers.

Ran it: 9 of 39 completed before I hit the quota wall again. One real
difference showed up — "Was there a security incident this quarter?"
answered incompletely without verification (missing the 40-minute
duration) but completely with it. But I want to be honest about what
this does and doesn't prove: the with-verification run shows
`attempts: 0`, meaning the verifier approved it on the first try — the
retry mechanism never actually fired. So this specific difference could
just be normal sampling variance between two separate API calls, not
proof the verifier caused anything. One suggestive data point isn't a
real ablation result yet.

Where this leaves me: real infrastructure, real partial data, not yet a
complete comparison (30 of 39 still pending, and no case yet where a
retry actually fired and visibly fixed something). I'm holding off on
any claim that the verifier *causes* the measured rate until this
finishes — right now the mechanism and the outcome are two separately-
true facts, not a proven cause and effect. Picking this back up with
`scripts/run_eval_baseline.py` whenever quota allows, watching
specifically for a case where `attempts > 0` in the full run.

## 32. Broke my own Unicode fix while editing, caught it before committing
Doing a pass on this file's wording, I rewrote `text_utils.py` and, while
retyping the special-character dict, accidentally collapsed two different
invisible characters (narrow no-break space and non-breaking space) into
the same literal ASCII space — silently overwriting one dict entry with
the other and turning both into no-ops. Didn't assume the edit was fine
just because it looked right; ran the actual function against explicit
`chr(0x2019)`/`chr(0x202f)` test input and it failed. Checked the dict's
real code points directly and found only 8 distinct entries where there
should be 9.

Also hit a second, dumber version of the same class of mistake trying to
fix it — wrote a Python script to regenerate the file programmatically,
but used `{{`/`}}` out of f-string habit in a plain string, which
`ast.parse()` happily accepted as valid syntax (parses fine as nested
literals) but which fails at actual runtime (`unhashable type: 'dict'`
trying to use a dict as another dict's key). Good reminder that syntax
validity isn't the same as correctness — parsing without errors doesn't
mean the code does what I think it does.

Fixed for real by writing the file line-by-line with explicit `\uXXXX`
escape text instead of literal characters, verified against actual
`chr()` code points afterward, not just eyeballed. Small thing, but a
good example of why I check my own edits instead of assuming a rewrite
that "looks right" actually is.
