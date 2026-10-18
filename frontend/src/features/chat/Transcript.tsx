import { useEffect, useRef } from "react";
import Markdown from "react-markdown";
import { Button, Chip } from "@heroui/react";
import type { Message } from "../../api/chat";

type Props = {
  messages: Message[];
  busy: boolean;
  waiting: boolean;
  debugEnabled?: boolean;
  onDebug?: (message: Message) => void;
  onRollback: (message: Message) => void;
};
export function Transcript({
  messages,
  busy,
  waiting,
  onRollback,
  debugEnabled,
  onDebug,
}: Props) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);
  return (
    <div
      className="flex flex-col gap-3 max-lg:flex-1 lg:gap-5"
      aria-label="Conversation"
    >
      {!messages.length && (
        <div className="rounded-3xl border-2 border-dashed border-grape/25 bg-surface/60 px-6 py-8 text-center lg:py-12">
          <span className="text-4xl text-sun">✦</span>
          <h2 className="mt-2 font-story text-2xl">
            How does your story begin?
          </h2>
          <p className="mt-1 text-muted">Describe your first action below.</p>
        </div>
      )}
      {messages.map((message, index) => {
        const time = new Date(message.created_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
        if (message.role === "user")
          return (
            <article
              key={message.id}
              className="ml-auto flex max-w-[92%] lg:max-w-[85%] flex-col items-end gap-1.5"
            >
              <div className="flex items-center gap-2 text-xs font-bold tracking-widest text-grape">
                YOUR MOVE
                <span className="font-normal text-muted">{time}</span>
              </div>
              <p className="rounded-[16px] rounded-tr-[6px] text-white bg-linear-to-br from-brand to-brand-coral px-5 py-3 whitespace-pre-wrap lg:px-5 lg:py-3 text-white shadow-lg shadow-grape/25">
                {message.content}
              </p>
            </article>
          );
        return (
          <article
            key={message.id}
            className={`relative max-w-full overflow-hidden rounded-[16px] rounded-tl-[6px] border bg-surface p-4 pl-6 lg:max-w-[95%] lg:p-6 lg:pl-8 shadow-lg shadow-grape/10 ${
              message.is_error
                ? "border-danger/40 bg-coral-soft"
                : "border-grape/10"
            }`}
          >
            <span
              aria-hidden
              className={`absolute inset-y-0 left-0 w-1 ${
                message.is_error
                  ? "bg-danger"
                  : "bg-linear-to-b from-sun via-coral to-grape"
              }`}
            />
            <div className="mb-3 flex items-center gap-2">
              <Chip color={message.is_error ? "danger" : "accent"} size="sm">
                {message.is_error ? "HICCUP" : "NARRATOR"}
              </Chip>
              <span className="text-xs text-muted">{time}</span>
              {debugEnabled && (
                <Button
                  size="sm"
                  variant="ghost"
                  onPress={() => onDebug?.(message)}
                  aria-label={`Debug narrator response ${message.id}`}
                >
                  Debug
                </Button>
              )}
            </div>
            {message.image_url && (
              <img
                src={message.image_url}
                alt="Storybook illustration of this adventure scene"
                className="mb-4 block h-auto w-auto max-w-full rounded-[16px]"
                loading="lazy"
              />
            )}
            {message.image_failed && (
              <p className="mb-3 text-xs text-muted">
                The scene illustration couldn’t be generated this turn.
              </p>
            )}
            <div className="story-prose">
              <Markdown skipHtml>{message.content}</Markdown>
            </div>
            {!message.is_error && index < messages.length - 1 && (
              <Button
                size="sm"
                variant="ghost"
                className="mt-3"
                isDisabled={busy}
                onPress={() => onRollback(message)}
              >
                ↶ Continue from here
              </Button>
            )}
          </article>
        );
      })}
      {waiting && (
        <div
          className="flex items-center gap-3 self-start rounded-full bg-surface px-5 py-3 text-sm text-muted shadow-md"
          role="status"
        >
          <span className="flex gap-1.5" aria-hidden>
            <span className="dot-bob bg-grape" />
            <span className="dot-bob bg-coral" />
            <span className="dot-bob bg-sun" />
          </span>
          The narrator is writing your next chapter…
        </div>
      )}
      <div ref={end} />
    </div>
  );
}
