import { afterEach, expect, test, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { confirmAction, notify } from "./notifications";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

test("confirmations resolve only after a choice and restore focus", async () => {
  vi.spyOn(HTMLDialogElement.prototype, "showModal").mockImplementation(
    function (this: HTMLDialogElement) {
      this.setAttribute("open", "");
    },
  );
  vi.spyOn(HTMLDialogElement.prototype, "close").mockImplementation(() => {});
  const trigger = document.createElement("button");
  document.body.append(trigger);
  trigger.focus();
  const pending = confirmAction("Delete this adventure?");
  expect(screen.getByRole("dialog")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(await pending).toBe(false);
  expect(document.activeElement).toBe(trigger);
  const accepted = confirmAction("Delete this adventure?");
  fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
  expect(await accepted).toBe(true);
  const escaped = confirmAction("Delete this adventure?");
  fireEvent(
    screen.getByRole("dialog"),
    new Event("cancel", { cancelable: true }),
  );
  expect(await escaped).toBe(false);
});

test("save toasts can be dismissed and expire", () => {
  vi.useFakeTimers();
  notify("Configuration saved.");
  expect(screen.getByRole("status").textContent).toContain(
    "Configuration saved.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(screen.queryByRole("status")).toBeNull();
  notify("Configuration saved.");
  vi.advanceTimersByTime(6000);
  expect(screen.queryByRole("status")).toBeNull();
});
