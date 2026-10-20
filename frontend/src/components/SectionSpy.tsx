import { Anchor, Button, ConfigProvider, Popover, theme } from "antd";
import { useCallback, useEffect, useState } from "react";

export type SpySection = { id: string; label: string };
const HEADER_OFFSET = 96;

function readTheme() {
  const root = document.documentElement;
  const styles = getComputedStyle(root);
  return {
    algorithm: root.classList.contains("dark")
      ? theme.darkAlgorithm
      : theme.defaultAlgorithm,
    token: {
      colorPrimary: styles.getPropertyValue("--primary").trim() || "#315d91",
      fontFamily: getComputedStyle(document.body).fontFamily || "sans-serif",
    },
    components: { Anchor: { linkPaddingBlock: 8 } },
  };
}

/** Ant Design owns the links, scrolling, tracking and active indicator. */
export function SectionSpy({
  sections,
  title,
}: {
  sections: SpySection[];
  title: string;
}) {
  const [appearance, setAppearance] = useState(readTheme);
  const [open, setOpen] = useState(false);
  // Preserve explicit navigation when a short section cannot align above the fold.
  const [destination, setDestination] = useState<string | null>(null);
  useEffect(() => {
    const observer = new MutationObserver(() => setAppearance(readTheme()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });
    const resume = () => setDestination(null);
    const onKey = (event: KeyboardEvent) => {
      if (
        [
          "ArrowDown",
          "ArrowUp",
          "PageDown",
          "PageUp",
          "Home",
          "End",
          " ",
        ].includes(event.key)
      )
        resume();
    };
    const onPointer = (event: PointerEvent) => {
      if (
        !(event.target instanceof Element) ||
        !event.target.closest(
          ".section-spy, .section-spy-popover, .section-spy-toggle",
        )
      )
        resume();
    };
    window.addEventListener("wheel", resume, { passive: true });
    window.addEventListener("touchmove", resume, { passive: true });
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      observer.disconnect();
      window.removeEventListener("wheel", resume);
      window.removeEventListener("touchmove", resume);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, []);
  const first = sections[0]?.id;
  const getCurrentAnchor = useCallback(
    (href: string) => destination || href || (first ? `#${first}` : ""),
    [destination, first],
  );
  if (!sections.length) return null;
  const links = (
    <Anchor
      affix={false}
      showInkInFixed
      replace
      bounds={1}
      targetOffset={HEADER_OFFSET}
      getCurrentAnchor={getCurrentAnchor}
      items={sections.map(({ id, label }) => ({
        key: id,
        href: `#${id}`,
        title: label,
      }))}
      onClick={(_event, { href }) => {
        setDestination(href);
        document.getElementById(href.slice(1))?.focus({ preventScroll: true });
        setOpen(false);
      }}
    />
  );
  return (
    <ConfigProvider theme={appearance}>
      <nav aria-label="Page sections" className="section-spy">
        <p className="section-spy-title text-xs font-semibold text-muted mb-2">
          {title}
        </p>
        {links}
      </nav>
      <Popover
        trigger="click"
        placement="left"
        open={open}
        onOpenChange={setOpen}
        classNames={{ root: "section-spy-popover" }}
        content={<nav aria-label="Mobile page sections">{links}</nav>}
        title={title}
      >
        <Button
          className="section-spy-toggle"
          aria-label="Show page sections"
          aria-expanded={open}
        >
          Sections
        </Button>
      </Popover>
    </ConfigProvider>
  );
}
