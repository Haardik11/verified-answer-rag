export interface Source {
  source: string;
  chunk_index: number;
  score: number;
  text: string;
}

export interface AskResponse {
  answer: string;
  is_chitchat: boolean;
  grounded: boolean;
  attempts: number;
  verification_reason: string;
  sources: Source[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  question?: string;
  response?: AskResponse;
  error?: string;
  pending?: boolean;
}

export interface Chat {
  id: string;
  title: string | null; // null until the first question is asked, then set from it
  messages: ChatMessage[];
  createdAt: number;
}
