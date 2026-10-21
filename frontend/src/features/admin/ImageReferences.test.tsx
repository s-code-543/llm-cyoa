import { expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ImageReferences } from "./ImageReferences";
import { apiFetch } from "../../api/client";
vi.mock("../../api/client", () => ({ apiFetch: vi.fn() }));

test("upload sends a reference file and role, previews saved references, and allows removal", async () => {
  const reference = {
    id: "abc",
    name: "hero.png",
    kind: "character" as const,
    url: "/reference/abc",
  };
  vi.mocked(apiFetch).mockResolvedValue(reference);
  const change = vi.fn();
  const busy = vi.fn();
  const { rerender } = render(
    <ImageReferences value={[]} onChange={change} onBusyChange={busy} />,
  );
  const file = new File(["png"], "hero.png", { type: "image/png" });
  fireEvent.change(screen.getByLabelText("Upload character sheet"), {
    target: { files: [file] },
  });
  await waitFor(() => expect(change).toHaveBeenCalledWith([reference]));
  const payload = vi.mocked(apiFetch).mock.calls[0][1]!.payload as FormData;
  expect(payload.get("image")).toBe(file);
  expect(payload.get("kind")).toBe("character");
  expect(busy.mock.calls).toEqual([[true], [false]]);
  rerender(
    <ImageReferences
      value={[reference]}
      onChange={change}
      onBusyChange={busy}
    />,
  );
  expect(screen.getByRole("img", { name: "hero.png" })).toHaveAttribute(
    "src",
    "/reference/abc",
  );
  fireEvent.click(screen.getByRole("button", { name: "Remove hero.png" }));
  expect(change).toHaveBeenLastCalledWith([]);
});
