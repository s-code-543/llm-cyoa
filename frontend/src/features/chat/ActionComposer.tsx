import { useEffect, useRef, useState } from "react";

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
  return (
    <div className="composer-area">
      {opening && !finished && (
        <button
          className="primary"
          disabled={busy || voiceBusy}
          onClick={() => onSubmit("Begin the Adventure")}
        >
          Begin the Adventure
        </button>
      )}
      <div className="voice-controls">
        <button
          type="button"
          disabled={busy || finished || voice === "processing"}
          onClick={() => {
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
          {voice === "recording"
            ? "Stop dictation"
            : voice === "processing"
              ? "Transcribing…"
              : "Dictate action"}
        </button>
        {voice === "recording" && (
          <button type="button" onClick={() => CYOARecorder.cancelRecording()}>
            Cancel recording
          </button>
        )}
        {voice === "error" && (
          <>
            <button
              type="button"
              disabled={busy || finished}
              onClick={() => void CYOARecorder.retryTranscription()}
            >
              Retry transcription
            </button>
            <button
              type="button"
              onClick={() => void CYOARecorder.discardRecording()}
            >
              Discard recording
            </button>
          </>
        )}
        {voiceError && <p role="alert">{voiceError}</p>}
        {voice === "processing" && (
          <p role="status">Transcribing your recording…</p>
        )}
      </div>
      {!finished && choices.length > 0 && (
        <div className="choices" aria-label="Suggested actions">
          {choices.map((choice, index) => (
            <button
              key={index}
              disabled={busy || voiceBusy}
              onClick={() => onSubmit(choice)}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              {choice}
              <b>↗</b>
            </button>
          ))}
        </div>
      )}
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          if (!voiceBusy) onSubmit(draft);
        }}
      >
        <label className="sr-only" htmlFor="action">
          Your action
        </label>
        <textarea
          id="action"
          placeholder="What do you do next?"
          value={draft}
          maxLength={20000}
          disabled={busy || finished}
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
        <button
          className="send"
          type="submit"
          disabled={busy || voiceBusy || finished || !draft.trim()}
          aria-label="Send action"
        >
          ↑
        </button>
      </form>
      <p className="composer-hint">
        Enter to send · Shift + Enter for a new line
      </p>
    </div>
  );
}
