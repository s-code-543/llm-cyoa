import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button, TextArea } from "@heroui/react";

declare const CYOARecorder: {
  init(callbacks: {
    onStateChange: (state: string, error: string | null) => void;
    onTranscriptReady: (text: string) => void;
  }): Promise<{ status: string; transcript?: string } | null>;
  startRecording(): Promise<void>;
  stopRecording(): void;
  cancelRecording(): void;
  retryTranscription(): Promise<void>;
  discardRecording(): Promise<void>;
};

type Props = {
  opening?: boolean;
  choices: string[];
  busy: boolean;
  finished: boolean;
  draft: string;
  onDraft: (draft: string) => void;
  onSubmit: (message: string) => void;
};
export function ActionComposer({
  opening = false,
  choices,
  busy,
  finished,
  draft,
  onDraft,
  onSubmit,
}: Props) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const field = textarea.current;
    if (!field) return;
    const resize = () => {
      field.style.height = "0px";
      field.style.height = `${Math.min(Math.max(field.scrollHeight, 44), 240)}px`;
      field.style.overflowY = field.scrollHeight > 240 ? "auto" : "hidden";
    };
    resize();
    if (typeof ResizeObserver === "undefined") return;
    let width = field.getBoundingClientRect().width;
    const observer = new ResizeObserver(() => {
      const nextWidth = field.getBoundingClientRect().width;
      if (nextWidth !== width) {
        width = nextWidth;
        resize();
      }
    });
    observer.observe(field);
    return () => observer.disconnect();
  }, [draft]);
  const [voice, setVoice] = useState("idle");
  const [voiceError, setVoiceError] = useState("");
  const latest = useRef({ draft, onDraft });
  latest.current = { draft, onDraft };
  const active = useRef(false);
  useEffect(() => {
    if (typeof CYOARecorder === "undefined") return;
    let mounted = true;
    void CYOARecorder.init({
      onStateChange(state, error) {
        if (!mounted) return;
        active.current = state === "recording";
        setVoice(state);
        setVoiceError(error ?? "");
      },
      onTranscriptReady(text) {
        if (!mounted) return;
        const current = latest.current;
        current.onDraft(
          [current.draft.trim(), text.trim()].filter(Boolean).join(" "),
        );
      },
    })
      .then((pending) => {
        if (!mounted || !pending) return;
        if (pending.status === "transcribed" && pending.transcript) {
          setVoice("error");
          setVoiceError(
            "A previous recording is available. Retry to recover its transcript.",
          );
        } else {
          setVoice("error");
          setVoiceError(
            "An unfinished recording is available. Retry transcription or discard it.",
          );
        }
      })
      .catch((error) => {
        if (mounted) setVoiceError(String(error));
      });
    return () => {
      mounted = false;
      if (active.current) CYOARecorder.cancelRecording();
    };
  }, []);
  const voiceBusy = voice === "recording" || voice === "processing";
  const swatches = [
    "bg-grape-soft text-grape hover:border-grape",
    "bg-coral-soft text-coral hover:border-coral",
    "bg-mint-soft text-mint hover:border-mint",
    "bg-sun-soft text-sun hover:border-sun",
  ];
  return (
    <div className="flex flex-col gap-2 max-lg:mt-auto lg:gap-4">
      {opening && !finished && (
        <Button
          variant="primary"
          size="lg"
          className="self-start text-white bg-linear-to-r from-brand to-brand-coral"
          isDisabled={busy || voiceBusy}
          onPress={() => onSubmit("Begin the Adventure")}
        >
          Begin the Adventure
        </Button>
      )}
      {!finished && choices.length > 0 && (
        <div
          className="grid gap-3 sm:grid-cols-2"
          aria-label="Suggested actions"
        >
          {choices.map((choice, index) => (
            <button
              key={index}
              disabled={busy || voiceBusy}
              onClick={() => onSubmit(choice)}
              className={`group flex items-center gap-3 rounded-2xl border-2 border-transparent p-3 lg:p-4 text-left font-semibold text-foreground shadow-sm transition hover:-translate-y-0.5 hover:shadow-md disabled:pointer-events-none disabled:opacity-50 ${swatches[index % swatches.length]}`}
            >
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface text-xs font-bold shadow-sm">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="flex-1">{choice}</span>
              <b className="opacity-0 transition group-hover:opacity-100">↗</b>
            </button>
          ))}
        </div>
      )}
      <form
        className="action-composer sticky bottom-1 z-10 flex items-center gap-2 rounded-[24px] border border-grape/15 bg-surface p-2 shadow-lg shadow-grape/10 focus-within:border-grape/50"
        onSubmit={(e) => {
          e.preventDefault();
          if (!voiceBusy) onSubmit(draft);
        }}
      >
        <TextArea
          ref={textarea}
          aria-label="Your action"
          placeholder="What do you do next?"
          value={draft}
          rows={1}
          maxLength={20000}
          disabled={busy || finished}
          className="min-h-11 min-w-0 flex-1 resize-none border-0 bg-transparent shadow-none outline-none"
          onChange={(e) => onDraft(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              if (!voiceBusy) onSubmit(draft);
            }
          }}
        />
        <Button
          type="button"
          variant="secondary"
          isIconOnly
          aria-label={
            voice === "recording"
              ? "Stop dictation"
              : voice === "processing"
                ? "Transcribing…"
                : "Dictate action"
          }
          className={`shrink-0 rounded-full ${voice === "recording" ? "animate-pulse bg-brand-coral text-white" : ""}`}
          isDisabled={busy || finished || voice === "processing"}
          onPress={() => {
            if (typeof CYOARecorder === "undefined") {
              setVoiceError("Dictation is unavailable. Reload the page.");
              return;
            }
            if (voice === "recording") CYOARecorder.stopRecording();
            else
              void CYOARecorder.startRecording().catch((error) =>
                setVoiceError(String(error)),
              );
          }}
        >
          <svg
            aria-hidden="true"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {voice === "recording" ? (
              <rect
                x="6"
                y="6"
                width="12"
                height="12"
                rx="2"
                fill="currentColor"
                stroke="none"
              />
            ) : (
              <>
                <rect x="9" y="2" width="6" height="12" rx="3" />
                <path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8" />
              </>
            )}
          </svg>
        </Button>
        <Button
          type="submit"
          variant="primary"
          isIconOnly
          className="shrink-0 rounded-full text-white bg-linear-to-br from-brand to-brand-coral"
          isDisabled={busy || voiceBusy || finished || !draft.trim()}
          aria-label="Send action"
        >
          <svg
            aria-hidden="true"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 19V5m-6 6 6-6 6 6" />
          </svg>
        </Button>
      </form>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {voice === "recording" && (
          <Button
            size="sm"
            variant="ghost"
            onPress={() => CYOARecorder.cancelRecording()}
          >
            Cancel recording
          </Button>
        )}
        {voice === "error" && (
          <>
            <Button
              size="sm"
              variant="secondary"
              isDisabled={busy || finished}
              onPress={() => void CYOARecorder.retryTranscription()}
            >
              Retry transcription
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onPress={() => void CYOARecorder.discardRecording()}
            >
              Discard recording
            </Button>
          </>
        )}
        {voiceError && (
          <p role="alert" className="text-danger">
            {voiceError}
          </p>
        )}
        {voice === "processing" && (
          <p role="status">Transcribing your recording…</p>
        )}
        <p className="ml-auto hidden text-xs text-muted sm:block">
          Enter to send · Shift + Enter for a new line
        </p>
      </div>
    </div>
  );
}
