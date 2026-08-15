import { motion } from "framer-motion";
import type { ChatMessage as ChatMessageType } from "../types";
import { SourcesPanel } from "./SourcesPanel";

function GroundedBadge({ grounded, attempts }: { grounded: boolean; attempts: number }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <motion.span
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 400, damping: 20, delay: 0.1 }}
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
          grounded ? "bg-sage-light text-sage" : "bg-amber-light text-amber"
        }`}
      >
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          {grounded ? (
            <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
          ) : (
            <path
              d="M12 9v4m0 4h.01M10.3 3.9L2.7 17a2 2 0 001.7 3h15.2a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}
        </svg>
        {grounded ? "Verified" : "Unverified"}
      </motion.span>
      {attempts > 0 && (
        <span className="text-[11px] text-stone">
          self-corrected · {attempts} {attempts === 1 ? "retry" : "retries"}
        </span>
      )}
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex items-center gap-1.5">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-coral/60"
          animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }}
          transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.15, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}

const bubbleMotion = {
  initial: { opacity: 0, y: 10, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, scale: 0.97 },
  transition: { type: "spring" as const, stiffness: 350, damping: 28 },
};

export function ChatMessage({ message }: { message: ChatMessageType }) {
  if (message.role === "user") {
    return (
      <motion.div {...bubbleMotion} className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-coral px-4 py-2.5 text-[15px] text-white shadow-sm">
          {message.question}
        </div>
      </motion.div>
    );
  }

  if (message.pending) {
    return (
      <motion.div {...bubbleMotion} className="flex justify-start">
        <div className="max-w-[75%] rounded-2xl rounded-bl-sm border border-line bg-card px-4 py-3 shadow-sm">
          <ThinkingBubble />
        </div>
      </motion.div>
    );
  }

  if (message.error) {
    return (
      <motion.div {...bubbleMotion} className="flex justify-start">
        <div className="max-w-[75%] rounded-2xl rounded-bl-sm border border-coral/30 bg-coral-light px-4 py-3 text-sm text-coral-dark">
          {message.error}
        </div>
      </motion.div>
    );
  }

  const response = message.response!;
  return (
    <motion.div {...bubbleMotion} className="flex justify-start">
      <div className="max-w-[80%] rounded-2xl rounded-bl-sm border border-line bg-card px-4 py-3 shadow-sm">
        <p className="text-[15px] leading-relaxed text-ink">{response.answer}</p>
        {!response.is_chitchat && (
          <>
            <GroundedBadge grounded={response.grounded} attempts={response.attempts} />
            <SourcesPanel sources={response.sources} question={message.question ?? ""} />
          </>
        )}
      </div>
    </motion.div>
  );
}
