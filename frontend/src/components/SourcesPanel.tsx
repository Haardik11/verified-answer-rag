import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { getRelevantExcerpt } from "../lib/excerpt";
import type { Source } from "../types";

function fileName(source: string) {
  return source.split("/").pop() ?? source;
}

function SourceCard({ source, question }: { source: Source; question: string }) {
  const [showFull, setShowFull] = useState(false);
  const excerpt = getRelevantExcerpt(source.text, question);

  return (
    <div className="rounded-lg border border-line bg-cream p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-coral-dark">
          {fileName(source.source)}#{source.chunk_index}
        </span>
        <span className="text-[10px] text-stone-light">score {source.score.toFixed(4)}</span>
      </div>

      {showFull || excerpt.isFullText ? (
        <p className="mt-1.5 text-xs leading-relaxed text-ink-light">{source.text}</p>
      ) : (
        <p className="mt-1.5 text-xs leading-relaxed">
          {excerpt.before && <span className="text-stone">…{excerpt.before} </span>}
          <span className="rounded bg-coral-light px-0.5 text-ink">{excerpt.match}</span>
          {excerpt.after && <span className="text-stone"> {excerpt.after}…</span>}
        </p>
      )}

      {!excerpt.isFullText && (
        <button
          onClick={() => setShowFull((v) => !v)}
          className="mt-1.5 text-[11px] font-medium text-stone hover:text-coral"
        >
          {showFull ? "Show relevant excerpt" : "Show full source"}
        </button>
      )}
    </div>
  );
}

export function SourcesPanel({ sources, question }: { sources: Source[]; question: string }) {
  const [open, setOpen] = useState(false);
  if (sources.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-xs font-medium text-stone transition-colors hover:text-coral"
      >
        <motion.svg
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 20 }}
          className="h-3 w-3"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
        >
          <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
        </motion.svg>
        {sources.length} source{sources.length > 1 ? "s" : ""}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="mt-2 space-y-2">
              {sources.map((s) => (
                <SourceCard key={`${s.source}-${s.chunk_index}`} source={s} question={question} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
