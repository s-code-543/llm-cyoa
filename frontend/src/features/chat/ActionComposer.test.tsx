import { afterEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, act } from "@testing-library/react";
import { ActionComposer } from "./ActionComposer";

afterEach(() => vi.unstubAllGlobals());
const props = {
  choices: [],
  busy: false,
  finished: false,
  draft: "",
  onDraft: vi.fn(),
  onSubmit: vi.fn(),
};
test("the opening shortcut submits the normal opening action", () => {
  const submit = vi.fn();
  render(<ActionComposer {...props} opening onSubmit={submit} />);
  fireEvent.click(screen.getByRole("button", { name: "Begin the Adventure" }));
  expect(submit).toHaveBeenCalledWith("Begin the Adventure");
});
test("dictation adds an editable transcript and blocks sending while recording", async () => {
  let callbacks: {
    onStateChange: (state: string, error: string | null) => void;
    onTranscriptReady: (text: string) => void;
  };
  const recorder = {
    init: vi.fn(async (value) => {
      callbacks = value;
      return null;
    }),
    startRecording: vi.fn(async () =>
      callbacks.onStateChange("recording", null),
    ),
    stopRecording: vi.fn(() => callbacks.onStateChange("processing", null)),
    cancelRecording: vi.fn(),
  };
  vi.stubGlobal("CYOARecorder", recorder);
  const draft = vi.fn();
  render(<ActionComposer {...props} draft="I enter." onDraft={draft} />);
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Dictate action" })),
  );
  expect(screen.getByRole("button", { name: "Send action" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Stop dictation" }));
  expect(recorder.stopRecording).toHaveBeenCalledOnce();
  act(() => {
    callbacks.onStateChange("success", null);
    callbacks.onTranscriptReady("Take the key.");
  });
  expect(draft).toHaveBeenCalledWith("I enter. Take the key.");
  expect(screen.getByRole("button", { name: "Send action" })).toBeEnabled();
});
