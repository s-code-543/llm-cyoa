import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { SectionSpy } from "./SectionSpy";

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.spyOn(Element.prototype, "getClientRects").mockReturnValue([
    {},
  ] as unknown as DOMRectList);
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function setup() {
  render(
    <>
      <SectionSpy
        title="Configuration"
        sections={[
          { id: "judges", label: "Judge steps" },
          { id: "workflow", label: "Workflow" },
        ]}
      />
      <h2 id="judges" tabIndex={-1}>
        Judges
      </h2>
      <h2 id="workflow" tabIndex={-1}>
        Workflow settings
      </h2>
    </>,
  );
  const judges = document.getElementById("judges")!;
  const workflow = document.getElementById("workflow")!;
  vi.spyOn(judges, "getBoundingClientRect").mockReturnValue({
    top: 96,
  } as DOMRect);
  vi.spyOn(workflow, "getBoundingClientRect").mockReturnValue({
    top: 130,
  } as DOMRect);
  const nav = within(screen.getByRole("navigation", { name: "Page sections" }));
  return { judges, workflow, nav };
}

test("uses Ant Design Anchor and tracks headings with the same offset as jumps", async () => {
  const { judges, workflow, nav } = setup();
  fireEvent.scroll(window);
  await waitFor(() =>
    expect(nav.getByRole("link", { name: "Judge steps" })).toHaveClass(
      "ant-anchor-link-title-active",
    ),
  );
  vi.mocked(judges.getBoundingClientRect).mockReturnValue({
    top: -40,
  } as DOMRect);
  vi.mocked(workflow.getBoundingClientRect).mockReturnValue({
    top: 80,
  } as DOMRect);
  fireEvent.scroll(window);
  await waitFor(() =>
    expect(nav.getByRole("link", { name: "Workflow" })).toHaveClass(
      "ant-anchor-link-title-active",
    ),
  );
});

test("a clicked short section stays selected through subsequent scroll events until manual scrolling", async () => {
  const { judges, workflow, nav } = setup();
  fireEvent.click(nav.getByRole("link", { name: "Judge steps" }));
  expect(document.activeElement).toBe(judges);
  expect(location.hash).toBe("#judges");
  vi.mocked(judges.getBoundingClientRect).mockReturnValue({
    top: -40,
  } as DOMRect);
  vi.mocked(workflow.getBoundingClientRect).mockReturnValue({
    top: 80,
  } as DOMRect);
  // Let Anchor's scrolling animation finish, then simulate a late scroll/layout event.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 500));
  });
  fireEvent.scroll(window);
  expect(nav.getByRole("link", { name: "Judge steps" })).toHaveClass(
    "ant-anchor-link-title-active",
  );
  fireEvent.wheel(window);
  fireEvent.scroll(window);
  await waitFor(() =>
    expect(nav.getByRole("link", { name: "Workflow" })).toHaveClass(
      "ant-anchor-link-title-active",
    ),
  );
});

test("mobile section menu uses an Ant Design popover and closes after navigation", async () => {
  setup();
  fireEvent.click(screen.getByRole("button", { name: "Show page sections" }));
  const menu = await screen.findByRole("navigation", {
    name: "Mobile page sections",
  });
  fireEvent.click(within(menu).getByRole("link", { name: "Workflow" }));
  expect(
    screen.getByRole("button", { name: "Show page sections" }),
  ).toHaveAttribute("aria-expanded", "false");
  expect(location.hash).toBe("#workflow");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 500));
  });
});
