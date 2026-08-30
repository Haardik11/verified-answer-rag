"""
Runs the real OCR path (app.ingestion.vision.ocr_image, a paid Groq vision
model call) against data/sample_scanned.pdf N times and scores each run
against a ground truth established by directly viewing the rendered page
(there is no ground-truth text file checked into the repo for this fixture,
so the comparison text below was read off the image by hand, not guessed).

Reports Word Error Rate (substitutions + insertions + deletions, aligned
with a standard edit-distance alignment) rather than exact-string match,
since exact-string match would trivially fail on any trailing whitespace or
punctuation difference that a human wouldn't consider an error.

Run with: PYTHONPATH=. python3 scripts/ocr_accuracy.py [n_runs]
"""

import sys

import pymupdf

from app.ingestion.vision import ocr_image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GROUND_TRUTH = (
    "Q3 Facilities Report The Austin office lease was renewed for 3 more years. "
    "Total facilities spend for the quarter was 95,000 dollars."
)

N_RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def word_error_rate(reference: str, hypothesis: str) -> tuple[float, int, int, int, int]:
    ref = reference.split()
    hyp = hypothesis.split()
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    # Backtrack to split total edits into substitutions/insertions/deletions.
    i, j = n, m
    subs = ins = dele = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hyp[j - 1]:
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            subs += 1
            i, j = i - 1, j - 1
        elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            ins += 1
            j -= 1
        else:
            dele += 1
            i -= 1
    return dp[n][m] / n, dp[n][m], subs, ins, dele


doc = pymupdf.open("data/sample_scanned.pdf")
image_bytes = doc[0].get_pixmap(dpi=200).tobytes("png")

print(f"Ground truth ({len(GROUND_TRUTH.split())} words): {GROUND_TRUTH}\n")

rates = []
for run in range(1, N_RUNS + 1):
    output = ocr_image(image_bytes)
    wer, edits, subs, ins, dele = word_error_rate(GROUND_TRUTH, output)
    rates.append(wer)
    print(f"--- Run {run} ---")
    print(f"Raw output: {output!r}")
    print(f"WER: {wer*100:.1f}%  ({edits} edits: {subs} sub, {ins} ins, {dele} del, over {len(GROUND_TRUTH.split())} ref words)\n")

avg = sum(rates) / len(rates)
print(f"=== Average WER over {N_RUNS} run(s): {avg*100:.1f}% ===")
