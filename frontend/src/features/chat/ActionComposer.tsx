type Props = {
  choices: string[];
  busy: boolean;
  finished: boolean;
  draft: string;
  onDraft: (draft: string) => void;
  onSubmit: (message: string) => void;
};
export function ActionComposer({
  choices,
  busy,
  finished,
  draft,
  onDraft,
  onSubmit,
}: Props) {
  return (
    <div className="composer-area">
      {!finished && choices.length > 0 && (
        <div className="choices" aria-label="Suggested actions">
          {choices.map((choice, index) => (
            <button
              key={index}
              disabled={busy}
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
          onSubmit(draft);
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
              onSubmit(draft);
            }
          }}
        />
        <button
          className="send"
          type="submit"
          disabled={busy || finished || !draft.trim()}
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
