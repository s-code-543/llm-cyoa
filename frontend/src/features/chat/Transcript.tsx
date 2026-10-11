import { useEffect, useRef } from "react";
import Markdown from "react-markdown";
import type { Message } from "../../api/chat";

type Props = {
  messages: Message[];
  busy: boolean;
  waiting: boolean;
  onRollback: (message: Message) => void;
};
export function Transcript({ messages, busy, waiting, onRollback }: Props) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);
  return (
    <div className="transcript" aria-label="Conversation">
      {!messages.length && (
        <div className="empty">
          <span className="ornament">✦</span>
          <h2>How does your story begin?</h2>
          <p>Describe your first action below.</p>
        </div>
      )}
      {messages.map((message, index) => (
        <article
          key={message.id}
          className={`message ${message.role} ${message.is_error ? "error-message" : ""}`}
        >
          <div className="message-label">
            {message.role === "user" ? "YOUR MOVE" : "NARRATOR"}
            <span>
              {new Date(message.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
          {message.role === "assistant" ? (
            <div className="prose">
              <Markdown skipHtml>{message.content}</Markdown>
            </div>
          ) : (
            <p className="user-text">{message.content}</p>
          )}
          {message.role === "assistant" &&
            !message.is_error &&
            index < messages.length - 1 && (
              <button
                className="text-button"
                disabled={busy}
                onClick={() => onRollback(message)}
              >
                ↶ Continue from here
              </button>
            )}
        </article>
      ))}
      {waiting && (
        <div className="narrating" role="status">
          <span />
          The narrator is writing your next chapter…
        </div>
      )}
      <div ref={end} />
    </div>
  );
}
