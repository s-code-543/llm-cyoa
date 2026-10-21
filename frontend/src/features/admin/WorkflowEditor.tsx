import { Button } from "@heroui/react";
import { Toggle } from "../../components/Toggle";
import { useState } from "react";
import type { Workflow, WorkflowNode } from "../../api/admin";

export const WORKFLOW_HELP: Record<string, string> = {
  RunPython: "Prepare hidden state using restricted Python.",
  GateInventory:
    "Limit unsolicited loot. Deliberately taking available items is exempt.",
  ApplyDifficulty: "Roll the configured difficulty for an ending.",
  ApplyRandomPrompt: "Randomly append a narrative instruction.",
  ConcatenatePrompt: "Give the narrator instructions and hidden state.",
  GenerateTurn: "Write the turn using the storyteller model.",
  ReWriteRefusal: "Detect refusals and try an in-world correction.",
  ReWriteJudge: "Run the optional judges configured below.",
  ExtractJSON: "Separate hidden state from visible narration.",
  ApplyStateChanges: "Accept permitted narrator changes to hidden state.",
  ValidateTurn: "Check the turn before committing it.",
  SaveGame: "Save the accepted turn and hidden state together.",
};
const PRE_GENERATION = [
  "RunPython",
  "GateInventory",
  "ApplyDifficulty",
  "ApplyRandomPrompt",
  "ConcatenatePrompt",
];
export const DEFAULT_NODES: WorkflowNode[] = [
  { type: "ApplyDifficulty" },
  { type: "ConcatenatePrompt", include_state: false },
  { type: "GenerateTurn" },
  { type: "ReWriteRefusal" },
  { type: "ReWriteJudge" },
  { type: "ValidateTurn" },
  { type: "SaveGame" },
];

type FieldSpec = {
  key: string;
  label: string;
  kind: "text" | "number" | "checkbox" | "textarea" | "list";
  fallback: unknown;
};

function fieldsFor(type: string): FieldSpec[] {
  const fields: FieldSpec[] = [
    { key: "name", label: "Step name (optional)", kind: "text", fallback: "" },
  ];
  if (type === "GateInventory")
    fields.push(
      {
        key: "probability",
        label: "Unsolicited loot probability (0–1)",
        kind: "number",
        fallback: 0.25,
      },
      {
        key: "cooldown_turns",
        label: "Quiet turns after a gift",
        kind: "number",
        fallback: 2,
      },
      {
        key: "max_new_items",
        label: "Maximum unsolicited items",
        kind: "number",
        fallback: 1,
      },
      {
        key: "verify_narrative",
        label: "Verify inventory with correction model (adds a call)",
        kind: "checkbox",
        fallback: true,
      },
    );
  if (type === "RunPython")
    fields.push({
      key: "code",
      label: "Python code",
      kind: "textarea",
      fallback: "",
    });
  if (type === "ConcatenatePrompt")
    fields.push(
      {
        key: "prompt",
        label: "Narrator instructions",
        kind: "textarea",
        fallback: "",
      },
      {
        key: "include_state",
        label: "Include hidden state",
        kind: "checkbox",
        fallback: true,
      },
      {
        key: "target",
        label: "Prompt role (system or user)",
        kind: "text",
        fallback: "system",
      },
    );
  if (type === "ApplyRandomPrompt")
    fields.push(
      {
        key: "probability",
        label: "Probability (0–1)",
        kind: "number",
        fallback: 0,
      },
      { key: "prompt", label: "Instruction", kind: "textarea", fallback: "" },
    );
  if (type === "ApplyStateChanges")
    fields.push({
      key: "allowed_keys",
      label: "Editable state fields (comma separated)",
      kind: "list",
      fallback: [],
    });
  return fields;
}

function StepField({
  spec,
  step,
  onChange,
}: {
  spec: FieldSpec;
  step: WorkflowNode;
  onChange: (value: unknown) => void;
}) {
  const value = step[spec.key] ?? spec.fallback;
  if (spec.kind === "checkbox")
    return (
      <Toggle
        checked={Boolean(value)}
        onChange={(checked) => onChange(checked)}
      >
        {spec.label}
      </Toggle>
    );
  if (spec.kind === "textarea")
    return (
      <label>
        {spec.label}
        <textarea
          rows={4}
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    );
  if (spec.kind === "list")
    return (
      <label>
        {spec.label}
        <input
          defaultValue={(value as string[]).join(", ")}
          onBlur={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean),
            )
          }
        />
      </label>
    );
  return (
    <label>
      {spec.label}
      <input
        type={spec.kind}
        step={spec.kind === "number" ? "any" : undefined}
        value={String(value)}
        onChange={(e) =>
          onChange(
            spec.kind === "number" ? Number(e.target.value) : e.target.value,
          )
        }
      />
    </label>
  );
}

export function WorkflowEditor({
  value,
  onChange,
}: {
  value: Workflow;
  onChange: (next: Workflow) => void;
}) {
  const isDefault = !value.nodes?.length;
  const nodes = isDefault ? DEFAULT_NODES : value.nodes!;
  const [advanced, setAdvanced] = useState(false);
  const [jsonMode, setJsonMode] = useState(false);
  const [kind, setKind] = useState("ApplyRandomPrompt");
  const [draft, setDraft] = useState<string | null>(null);
  const [rawError, setRawError] = useState("");
  const emit = (next: WorkflowNode[]) => {
    setDraft(null);
    setRawError("");
    onChange(next.length ? { version: 1, nodes: next } : {});
  };
  const patch = (index: number, key: string, fieldValue: unknown) =>
    emit(nodes.map((n, i) => (i === index ? { ...n, [key]: fieldValue } : n)));
  const move = (from: number, to: number) => {
    const next = [...nodes];
    [next[from], next[to]] = [next[to], next[from]];
    emit(next);
  };
  const add = () => {
    const base = nodes.length
      ? [...nodes]
      : DEFAULT_NODES.map((n) => ({ ...n }));
    const at = base.findIndex(
      (n) =>
        n.type ===
        (PRE_GENERATION.includes(kind) ? "GenerateTurn" : "ValidateTurn"),
    );
    base.splice(at, 0, { type: kind });
    emit(base);
  };
  const raw = draft ?? JSON.stringify(value, null, 2);

  return (
    <div className="workflow" role="group" aria-label="Turn workflow">
      {isDefault && (
        <p>
          Default: difficulty → context → storyteller → refusal repair →
          optional judge → validate → save.
        </p>
      )}
      {!advanced && (
        <ol aria-label="Workflow steps" className="workflow-summary">
          {(nodes.length ? nodes : DEFAULT_NODES).map((step, index) => (
            <li key={index}>
              <strong>{String(step.name || step.type)}</strong> —{" "}
              {WORKFLOW_HELP[step.type]}
            </li>
          ))}
        </ol>
      )}
      <Toggle checked={advanced} onChange={setAdvanced}>
        Advanced mode
      </Toggle>
      {advanced && (
        <>
          <Toggle checked={jsonMode} onChange={setJsonMode}>
            JSON mode (recommended for robots)
          </Toggle>
          {!jsonMode && (
            <>
              {isDefault && (
                <p>Using the default workflow. Add a step to customize it.</p>
              )}
              {nodes.map((step, index) => (
                <div className="workflow-step" key={index}>
                  <div className="workflow-step-heading">
                    <span className="workflow-step-number">{index + 1}</span>
                    <div>
                      <strong>{String(step.name || step.type)}</strong>
                      <p>{WORKFLOW_HELP[step.type] ?? ""}</p>
                    </div>
                  </div>
                  <details className="workflow-step-settings">
                    <summary>Step settings</summary>
                    {fieldsFor(step.type).map((spec) => (
                      <StepField
                        key={spec.key}
                        spec={spec}
                        step={step}
                        onChange={(v) => patch(index, spec.key, v)}
                      />
                    ))}
                  </details>
                  <div className="workflow-step-actions">
                    <Button
                      size="sm"
                      variant="secondary"
                      type="button"
                      aria-label={`Move step ${index + 1} up`}
                      isDisabled={index === 0}
                      onPress={() => move(index, index - 1)}
                    >
                      ↑
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      type="button"
                      aria-label={`Move step ${index + 1} down`}
                      isDisabled={index === nodes.length - 1}
                      onPress={() => move(index, index + 1)}
                    >
                      ↓
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      type="button"
                      aria-label={`Remove step ${index + 1}`}
                      onPress={() => emit(nodes.filter((_, i) => i !== index))}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
              <div className="workflow-add">
                <label>
                  Add a workflow step
                  <select
                    aria-label="Step type"
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
                    {Object.keys(WORKFLOW_HELP).map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                </label>
                <Button size="sm" type="button" onPress={add}>
                  Add step
                </Button>
                {nodes.length > 0 && (
                  <Button
                    size="sm"
                    variant="secondary"
                    type="button"
                    onPress={() => emit([])}
                  >
                    Reset to default
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted">{WORKFLOW_HELP[kind]}</p>
            </>
          )}
          {jsonMode && (
            <>
              <p>
                Edit the complete workflow as JSON. An empty object uses the
                default workflow.
              </p>
              <textarea
                aria-label="Workflow JSON"
                rows={10}
                value={raw}
                onChange={(e) => {
                  setDraft(e.target.value);
                  try {
                    const parsed = e.target.value.trim()
                      ? JSON.parse(e.target.value)
                      : {};
                    if (
                      !parsed ||
                      typeof parsed !== "object" ||
                      Array.isArray(parsed) ||
                      (Object.keys(parsed).length > 0 &&
                        (parsed.version !== 1 ||
                          !Array.isArray(parsed.nodes) ||
                          !parsed.nodes.every(
                            (node: WorkflowNode) =>
                              node && typeof node.type === "string",
                          )))
                    )
                      throw new Error("Invalid workflow");
                    e.target.setCustomValidity("");
                    setRawError("");
                    onChange(parsed);
                  } catch {
                    e.target.setCustomValidity(
                      "Enter a workflow object with version 1 and a nodes array, or {} for defaults.",
                    );
                    setRawError(
                      "Enter a workflow object with version 1 and a nodes array, or {} for defaults.",
                    );
                  }
                }}
              />
              {rawError && (
                <span role="alert" className="field-error">
                  {rawError}
                </span>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
