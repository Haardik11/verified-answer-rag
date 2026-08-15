import { AnimatePresence, motion } from "framer-motion";
import type { Chat } from "../types";

function relativeTime(timestamp: number): string {
  const diffMs = Date.now() - timestamp;
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function Sidebar({
  chats,
  activeChatId,
  onSelect,
  onNewChat,
  onDelete,
}: {
  chats: Chat[];
  activeChatId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
}) {
  const sorted = [...chats].sort((a, b) => b.createdAt - a.createdAt);

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-line bg-cream-dark">
      <div className="flex items-center gap-2 px-4 py-4">
        <motion.div
          whileHover={{ rotate: -6, scale: 1.05 }}
          transition={{ type: "spring", stiffness: 300, damping: 15 }}
          className="flex h-7 w-7 items-center justify-center rounded-lg bg-coral text-sm font-bold text-white shadow-sm"
        >
          V
        </motion.div>
        <span className="text-sm font-semibold text-ink">VerifiedRAG</span>
      </div>

      <div className="px-3">
        <motion.button
          onClick={onNewChat}
          whileHover={{ scale: 1.015 }}
          whileTap={{ scale: 0.98 }}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-line bg-card py-2 text-sm font-medium text-ink shadow-sm transition-colors hover:border-coral/40 hover:text-coral"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M12 5v14M5 12h14" strokeLinecap="round" />
          </svg>
          New chat
        </motion.button>
      </div>

      <div className="mt-3 flex-1 space-y-1 overflow-y-auto px-2 pb-3">
        {sorted.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-stone">No chats yet</p>
        )}
        <AnimatePresence initial={false}>
          {sorted.map((chat) => (
            <motion.div
              layout
              key={chat.id}
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.15 } }}
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
              onClick={() => onSelect(chat.id)}
              className={`group relative flex cursor-pointer items-center justify-between rounded-lg px-2.5 py-2 text-sm transition-colors ${
                chat.id === activeChatId
                  ? "bg-coral-light text-ink"
                  : "text-ink-light hover:bg-cream"
              }`}
            >
              {chat.id === activeChatId && (
                <motion.span
                  layoutId="active-chat-indicator"
                  className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-coral"
                />
              )}
              <div className="min-w-0">
                <p className="truncate">{chat.title ?? "New chat"}</p>
                <p className="text-[11px] text-stone-light">{relativeTime(chat.createdAt)}</p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(chat.id);
                }}
                className="ml-2 shrink-0 rounded p-1 text-stone-light opacity-0 transition-opacity hover:bg-line hover:text-coral-dark group-hover:opacity-100"
                aria-label="Delete chat"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                </svg>
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </aside>
  );
}
