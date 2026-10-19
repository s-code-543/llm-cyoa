import type { ModelPricing } from "../../api/admin";

// Catalog token rates are USD per token, not per million tokens.
const rates: [string, string, number][] = [
  ["prompt", "input / 1M tokens", 1_000_000],
  ["completion", "output / 1M tokens", 1_000_000],
  ["request", "/ request", 1],
  ["image", "/ input image", 1],
  ["image_token", "/ 1M image tokens", 1_000_000],
  ["web_search", "/ web search", 1],
  ["internal_reasoning", "/ 1M reasoning tokens", 1_000_000],
  ["input_cache_write", "/ 1M cache-write tokens", 1_000_000],
];
const dollars = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumSignificantDigits: 6,
});

export function ModelCosts({
  pricing,
  updatedAt,
  section,
}: {
  pricing?: ModelPricing;
  updatedAt?: string | null;
  section?: "prompt" | "completion" | "other";
}) {
  const visibleRates =
    section === "other"
      ? rates.filter(([key]) => key !== "prompt" && key !== "completion")
      : section
        ? rates.filter(([key]) => key === section)
        : rates;
  const shown = visibleRates.flatMap(([key, label, multiplier]) => {
    const value = pricing?.[key];
    if (
      (typeof value !== "number" && typeof value !== "string") ||
      String(value).trim() === ""
    )
      return [];
    const number = Number(value);
    if (!Number.isFinite(number) || !Number.isFinite(number * multiplier))
      return [];
    return [
      <div key={key}>
        {number < 0 ? "Variable" : dollars.format(number * multiplier)} {label}
      </div>,
    ];
  });
  return (
    <div className="model-costs">
      {shown.length ? (
        shown
      ) : (
        <span>{section === "other" ? "—" : "Pricing unavailable"}</span>
      )}
      {Array.isArray(pricing?.overrides) && pricing.overrides.length > 0 && (
        <small>Conditional rates also apply.</small>
      )}
      {updatedAt && (
        <small>Checked {new Date(updatedAt).toLocaleString()}</small>
      )}
    </div>
  );
}
