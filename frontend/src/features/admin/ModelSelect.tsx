import { Label, ListBox, Select } from "@heroui/react";

export function ModelSelect({
  label,
  value,
  onChange,
  options,
  hideLabel = false,
}: {
  hideLabel?: boolean;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <Select
      className="model-select"
      aria-label={label}
      value={value || "__all__"}
      onChange={(key) => onChange(String(key) === "__all__" ? "" : String(key))}
    >
      <Label className={hideLabel ? "sr-only" : undefined}>{label}</Label>
      <Select.Trigger className="h-10 min-h-10 pe-9">
        <Select.Value>{({ selectedText }) => selectedText}</Select.Value>
        <Select.Indicator className="end-3" />
      </Select.Trigger>
      <Select.Popover>
        <ListBox aria-label={label}>
          {options.map((option) => (
            <ListBox.Item
              key={option.value || "__all__"}
              id={option.value || "__all__"}
              textValue={option.label}
            >
              {option.label}
              <ListBox.ItemIndicator />
            </ListBox.Item>
          ))}
        </ListBox>
      </Select.Popover>
    </Select>
  );
}
