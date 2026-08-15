// Finds the sentence within a source chunk that best matches the question
// (by simple keyword overlap) so the UI can show the reasoning-relevant part
// of a source instead of an arbitrary line cutoff. This is deliberately a
// lightweight heuristic, not a re-run of the backend's real embedding/BM25
// search - it only needs to be good enough to point a human at the right
// sentence to verify, not to rank sources itself.

const STOPWORDS = new Set([
  "a", "an", "the", "is", "are", "was", "were", "of", "in", "on", "at", "to", "for",
  "and", "or", "what", "how", "why", "when", "where", "who", "which", "did", "do",
  "does", "this", "that", "it", "its", "with", "by", "as", "be", "been", "being",
  "from", "about", "into", "over",
]);

function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function keywords(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2 && !STOPWORDS.has(w));
}

export interface Excerpt {
  before: string;
  match: string;
  after: string;
  isFullText: boolean;
}

export function getRelevantExcerpt(text: string, question: string): Excerpt {
  const sentences = splitSentences(text);
  if (sentences.length <= 3) {
    return { before: "", match: text, after: "", isFullText: true };
  }

  const questionWords = new Set(keywords(question));
  let bestIndex = 0;
  let bestScore = -1;
  sentences.forEach((sentence, i) => {
    const score = keywords(sentence).filter((w) => questionWords.has(w)).length;
    if (score > bestScore) {
      bestScore = score;
      bestIndex = i;
    }
  });

  const start = Math.max(0, bestIndex - 1);
  const end = Math.min(sentences.length, bestIndex + 2);
  return {
    before: sentences.slice(start, bestIndex).join(" "),
    match: sentences[bestIndex],
    after: sentences.slice(bestIndex + 1, end).join(" "),
    isFullText: start === 0 && end === sentences.length,
  };
}
