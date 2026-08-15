import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { askQuestion } from "./api";
import { ChatMessage } from "./components/ChatMessage";
import { Sidebar } from "./components/Sidebar";
import { loadChats, saveChats } from "./lib/storage";
import type { Chat, ChatMessage as ChatMessageType } from "./types";

const EXAMPLE_QUESTIONS = [
  "What was Q3 revenue?",
  "Was there a security incident this quarter?",
  "How did the SMB segment perform?",
  "What was Q2 revenue?",
];

function makeChat(): Chat {
  return { id: crypto.randomUUID(), title: null, messages: [], createdAt: Date.now() };
}

function App() {
  const [chats, setChats] = useState<Chat[]>(() => {
    const stored = loadChats();
    return stored.length > 0 ? stored : [makeChat()];
  });
  const [activeChatId, setActiveChatId] = useState<string>(() => chats[0].id);
  const [input, setInput] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const activeChat = chats.find((c) => c.id === activeChatId) ?? chats[0];

  useEffect(() => {
    saveChats(chats);
  }, [chats]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeChat?.messages.length]);

  function updateChat(chatId: string, updater: (chat: Chat) => Chat) {
    setChats((prev) => prev.map((c) => (c.id === chatId ? updater(c) : c)));
  }

  function handleNewChat() {
    const chat = makeChat();
    setChats((prev) => [chat, ...prev]);
    setActiveChatId(chat.id);
  }

  function handleDeleteChat(id: string) {
    const next = chats.filter((c) => c.id !== id);
    if (next.length === 0) {
      const fresh = makeChat();
      setChats([fresh]);
      setActiveChatId(fresh.id);
      return;
    }
    setChats(next);
    if (id === activeChatId) {
      setActiveChatId(next[0].id);
    }
  }

  async function handleAsk(question: string) {
    if (!question.trim() || isAsking) return;
    const chatId = activeChatId;

    const userMsg: ChatMessageType = { id: crypto.randomUUID(), role: "user", question };
    const pendingMsg: ChatMessageType = { id: crypto.randomUUID(), role: "assistant", pending: true, question };

    updateChat(chatId, (chat) => ({
      ...chat,
      title: chat.title ?? question.slice(0, 60),
      messages: [...chat.messages, userMsg, pendingMsg],
    }));
    setInput("");
    setIsAsking(true);

    try {
      const response = await askQuestion(question);
      updateChat(chatId, (chat) => ({
        ...chat,
        messages: chat.messages.map((m) => (m.id === pendingMsg.id ? { ...m, pending: false, response } : m)),
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Couldn't reach the backend. Is the FastAPI server running?";
      updateChat(chatId, (chat) => ({
        ...chat,
        messages: chat.messages.map((m) =>
          m.id === pendingMsg.id ? { ...m, pending: false, error: message } : m,
        ),
      }));
    } finally {
      setIsAsking(false);
    }
  }

  return (
    <div className="flex h-screen bg-cream">
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelect={setActiveChatId}
        onNewChat={handleNewChat}
        onDelete={handleDeleteChat}
      />

      <div className="flex flex-1 flex-col">
        <header className="border-b border-line px-6 py-4">
          <h1 className="text-sm font-medium text-ink-light">{activeChat?.title ?? "New chat"}</h1>
          <p className="text-xs text-stone">Self-correcting document Q&amp;A — retrieve · synthesize · verify</p>
        </header>

        <main className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto flex max-w-2xl flex-col gap-4">
            {(activeChat?.messages.length ?? 0) === 0 && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="mt-16 text-center"
              >
                <div className="animate-breathe mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-coral text-xl font-bold text-white shadow-md shadow-coral/20">
                  V
                </div>
                <p className="mt-4 text-sm text-stone">Ask a question about the indexed documents.</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {EXAMPLE_QUESTIONS.map((q, i) => (
                    <motion.button
                      key={q}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.15 + i * 0.06 }}
                      whileHover={{ y: -2, boxShadow: "0 4px 12px rgba(201,100,66,0.15)" }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => handleAsk(q)}
                      className="rounded-full border border-line bg-card px-3 py-1.5 text-xs text-ink-light transition-colors hover:border-coral/40 hover:text-coral"
                    >
                      {q}
                    </motion.button>
                  ))}
                </div>
              </motion.div>
            )}
            <AnimatePresence initial={false}>
              {activeChat?.messages.map((m) => (
                <ChatMessage key={m.id} message={m} />
              ))}
            </AnimatePresence>
            <div ref={bottomRef} />
          </div>
        </main>

        <footer className="border-t border-line px-6 py-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAsk(input);
            }}
            className="mx-auto flex max-w-2xl items-center gap-2"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about the indexed documents..."
              className="flex-1 rounded-xl border border-line bg-card px-4 py-2.5 text-[15px] text-ink placeholder-stone-light outline-none transition-shadow focus:border-coral/50 focus:shadow-[0_0_0_3px_rgba(201,100,66,0.12)]"
              disabled={isAsking}
            />
            <motion.button
              type="submit"
              disabled={isAsking || !input.trim()}
              whileHover={!isAsking && input.trim() ? { scale: 1.03 } : {}}
              whileTap={!isAsking && input.trim() ? { scale: 0.96 } : {}}
              className="rounded-xl bg-coral px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isAsking ? "Thinking…" : "Ask"}
            </motion.button>
          </form>
        </footer>
      </div>
    </div>
  );
}

export default App;
