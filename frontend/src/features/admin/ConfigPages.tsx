import { SectionSpy } from "../../components/SectionSpy";
import { ImageReferences } from "./ImageReferences";
import { confirmAction, notify } from "../../components/notifications";
import { Toggle } from "../../components/Toggle";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createConfig,
  deleteConfig,
  getConfig,
  getConfigOptions,
  getConfigs,
  updateConfig,
  type ConfigData,
  type ConfigOptions,
  type JudgeStepData,
} from "../../api/admin";
import { WorkflowEditor } from "./WorkflowEditor";
import { Failure, Field, Loading, asId, fieldErrors } from "./ui";

const key = ["admin", "configurations"];

const blankStep = (n: number): JudgeStepData => ({
  name: `Step ${n}`,
  enabled: true,
  classifier_prompt: null,
  classifier_model: null,
  classifier_timeout: 10,
  classifier_question: "",
  classifier_use_full_context: false,
  rewrite_prompt: null,
  rewrite_model: null,
  rewrite_timeout: 60,
  rewrite_instruction: "",
  rewrite_use_full_context: false,
  max_rewrite_attempts: 3,
  compare_prompt: null,
  compare_model: null,
  compare_timeout: 60,
  compare_question: "",
  compare_use_full_context: false,
});

const blankConfig = (): ConfigData => ({
  is_active: false,
  name: "",
  description: "",
  adventure_prompt: null,
  storyteller_model: null,
  storyteller_timeout: 60,
  game_ending_prompt: null,
  game_ending_turn_correction_prompt: null,
  difficulty: null,
  total_turns: 10,
  phase1_turns: 3,
  phase2_turns: 3,
  phase3_turns: 3,
  phase4_turns: 1,
  enable_tts: false,
  enable_image_generation: false,
  image_references: [],
  image_meta_prompt: null,
  character_prompt: null,
  image_model: null,
  image_aspect_ratio: "16:9",
  image_timeout: 60,
  enable_refusal_detection: false,
  turn_correction_prompt: null,
  turn_correction_model: null,
  turn_correction_timeout: 60,
  classifier_prompt: null,
  classifier_model: null,
  classifier_timeout: 60,
  classifier_question: "Is this a content policy refusal?",
  workflow: {},
  judge_steps: [],
});

type Choice = { id: number; name: string };

function Pick({
  label,
  value,
  onChange,
  choices,
  error,
  optional,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  choices: Choice[];
  error?: string;
  optional?: boolean;
}) {
  return (
    <Field label={label} error={error}>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(asId(e.target.value))}
      >
        <option value="">{optional ? "None" : "Select…"}</option>
        {choices.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </Field>
  );
}

function Num({
  label,
  value,
  onChange,
  error,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  error?: string;
}) {
  return (
    <Field label={label} error={error}>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </Field>
  );
}

const promptChoices = (
  list: { id: number; name: string; version: number }[],
): Choice[] => list.map((p) => ({ id: p.id, name: `${p.name} v${p.version}` }));

function StepEditor({
  step,
  index,
  options,
  errors,
  onChange,
  onRemove,
}: {
  step: JudgeStepData;
  index: number;
  options: ConfigOptions;
  errors: Record<string, string>;
  onChange: (next: JudgeStepData) => void;
  onRemove: () => void;
}) {
  const err = (name: string) => errors[`judge_steps.${index}.${name}`];
  const set = <K extends keyof JudgeStepData>(
    name: K,
    value: JudgeStepData[K],
  ) => onChange({ ...step, [name]: value });
  const prompts = promptChoices(options.judge_prompts);
  const classifierPrompts = promptChoices(options.classifier_prompts);
  const models = options.models.map((m) => ({ id: m.id, name: m.name }));
  return (
    <fieldset>
      <legend>Judge step {index + 1}</legend>
      <Field label="Step name">
        <input
          value={step.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </Field>
      <Toggle
        checked={step.enabled}
        onChange={(checked) => set("enabled", checked)}
      >
        Enabled
      </Toggle>
      <h4>Classifier (optional)</h4>
      <Pick
        label="Classifier prompt"
        value={step.classifier_prompt}
        onChange={(v) => set("classifier_prompt", v)}
        choices={classifierPrompts}
        error={err("classifier_prompt")}
        optional
      />
      <Pick
        label="Classifier model"
        value={step.classifier_model}
        onChange={(v) => set("classifier_model", v)}
        choices={models}
        error={err("classifier_model")}
        optional
      />
      <Num
        label="Classifier timeout (s)"
        value={step.classifier_timeout}
        onChange={(v) => set("classifier_timeout", v)}
        error={err("classifier_timeout")}
      />
      <Field label="Classifier question">
        <input
          value={step.classifier_question}
          onChange={(e) => set("classifier_question", e.target.value)}
        />
      </Field>
      <Toggle
        checked={step.classifier_use_full_context}
        onChange={(checked) => set("classifier_use_full_context", checked)}
      >
        Give classifier full conversation context
      </Toggle>
      <h4>Rewrite</h4>
      <Pick
        label="Rewrite prompt"
        value={step.rewrite_prompt}
        onChange={(v) => set("rewrite_prompt", v)}
        choices={prompts}
        error={err("rewrite_prompt")}
      />
      <Pick
        label="Rewrite model"
        value={step.rewrite_model}
        onChange={(v) => set("rewrite_model", v)}
        choices={models}
        error={err("rewrite_model")}
      />
      <Num
        label="Rewrite timeout (s)"
        value={step.rewrite_timeout}
        onChange={(v) => set("rewrite_timeout", v)}
        error={err("rewrite_timeout")}
      />
      <Num
        label="Maximum rewrite attempts"
        value={step.max_rewrite_attempts}
        onChange={(v) => set("max_rewrite_attempts", v)}
        error={err("max_rewrite_attempts")}
      />
      <Field label="Rewrite instruction">
        <input
          value={step.rewrite_instruction}
          onChange={(e) => set("rewrite_instruction", e.target.value)}
        />
      </Field>
      <Toggle
        checked={step.rewrite_use_full_context}
        onChange={(checked) => set("rewrite_use_full_context", checked)}
      >
        Give rewriter full conversation context
      </Toggle>
      <h4>Compare</h4>
      <Pick
        label="Compare prompt"
        value={step.compare_prompt}
        onChange={(v) => set("compare_prompt", v)}
        choices={prompts}
        error={err("compare_prompt")}
      />
      <Pick
        label="Compare model"
        value={step.compare_model}
        onChange={(v) => set("compare_model", v)}
        choices={models}
        error={err("compare_model")}
      />
      <Num
        label="Compare timeout (s)"
        value={step.compare_timeout}
        onChange={(v) => set("compare_timeout", v)}
        error={err("compare_timeout")}
      />
      <Field label="Compare question">
        <input
          value={step.compare_question}
          onChange={(e) => set("compare_question", e.target.value)}
        />
      </Field>
      <Toggle
        checked={step.compare_use_full_context}
        onChange={(checked) => set("compare_use_full_context", checked)}
      >
        Give comparator full conversation context
      </Toggle>
      <div className="toolbar">
        <button type="button" onClick={onRemove}>
          Remove judge step {index + 1}
        </button>
      </div>
    </fieldset>
  );
}

function ConfigForm({
  initial,
  options,
}: {
  initial: ConfigData;
  options: ConfigOptions;
}) {
  const navigate = useNavigate();
  const cache = useQueryClient();
  const [form, setForm] = useState(initial);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState("");
  const set = <K extends keyof ConfigData>(name: K, value: ConfigData[K]) =>
    setForm((current) => ({ ...current, [name]: value }));

  const save = useMutation({
    mutationFn: () =>
      initial.id ? updateConfig(initial.id, form) : createConfig(form),
    onSuccess: (saved) => {
      notify("Configuration saved.");
      cache.invalidateQueries({ queryKey: key });
      cache.setQueryData([...key, saved.id], saved);
      if (initial.id) {
        setForm(saved);
      } else navigate(`/manage/configurations/${saved.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteConfig(initial.id!),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: key });
      navigate("/manage/configurations");
    },
  });
  const errors = fieldErrors(save.error);
  const models = options.models.map((m) => ({ id: m.id, name: m.name }));
  const totalPhases =
    form.phase1_turns +
    form.phase2_turns +
    form.phase3_turns +
    form.phase4_turns;

  return (
    <form
      className="form configuration-form"
      onSubmit={async (event) => {
        event.preventDefault();
        setNotice("");
        if (initial.id && initial.is_active && !form.is_active) {
          try {
            const current = await getConfig(initial.id);
            if (
              !(await confirmAction(
                `Disable this configuration? ${current.in_progress_count ?? 0} adventures in progress will be unable to continue until it is reactivated.`,
              ))
            )
              return;
          } catch {
            setNotice("Could not check affected adventures. Please try again.");
            return;
          }
        }
        if (!uploading) save.mutate();
      }}
    >
      <SectionSpy
        title={initial.id ? initial.name : "New configuration"}
        sections={[
          { id: "config-basics", label: "Overview" },
          { id: "config-story", label: "Story" },
          { id: "config-pacing", label: "Pacing" },
          { id: "config-images", label: "Scene illustrations" },
          { id: "config-refusal", label: "Refusal detection" },
          { id: "config-judges", label: "Judge steps" },
          { id: "config-workflow", label: "Turn workflow" },
          { id: "config-save", label: "Save changes" },
        ]}
      />
      <h2 id="config-basics" tabIndex={-1}>
        Overview
      </h2>
      <Toggle
        checked={form.is_active ?? true}
        onChange={(v) => set("is_active", v)}
      >
        Active (published for players)
      </Toggle>
      <p>
        Inactive configurations are hidden from new adventures and prevent
        existing adventures from continuing.
      </p>
      <Field label="Name" error={errors.name}>
        <input
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </Field>
      <Field label="Description">
        <textarea
          rows={2}
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
        />
      </Field>

      <h2 id="config-story" tabIndex={-1}>
        Story
      </h2>
      <Pick
        label="Adventure prompt"
        value={form.adventure_prompt}
        onChange={(v) => set("adventure_prompt", v)}
        choices={promptChoices(options.adventure_prompts)}
        error={errors.adventure_prompt}
      />
      <Pick
        label="Storyteller model"
        value={form.storyteller_model}
        onChange={(v) => set("storyteller_model", v)}
        choices={models}
        error={errors.storyteller_model}
      />
      <Num
        label="Storyteller timeout (s)"
        value={form.storyteller_timeout}
        onChange={(v) => set("storyteller_timeout", v)}
        error={errors.storyteller_timeout}
      />
      <Pick
        label="Game ending prompt"
        value={form.game_ending_prompt}
        onChange={(v) => set("game_ending_prompt", v)}
        choices={promptChoices(options.game_ending_prompts)}
        error={errors.game_ending_prompt}
      />
      <Pick
        label="Difficulty profile"
        value={form.difficulty}
        onChange={(v) => set("difficulty", v)}
        choices={options.difficulties}
        error={errors.difficulty}
        optional
      />

      <h2 id="config-pacing" tabIndex={-1}>
        Pacing
      </h2>
      <Num
        label="Total turns"
        value={form.total_turns}
        onChange={(v) => set("total_turns", v)}
        error={errors.total_turns}
      />
      <Num
        label="Phase 1 turns"
        value={form.phase1_turns}
        onChange={(v) => set("phase1_turns", v)}
        error={errors.phase1_turns}
      />
      <Num
        label="Phase 2 turns"
        value={form.phase2_turns}
        onChange={(v) => set("phase2_turns", v)}
        error={errors.phase2_turns}
      />
      <Num
        label="Phase 3 turns"
        value={form.phase3_turns}
        onChange={(v) => set("phase3_turns", v)}
        error={errors.phase3_turns}
      />
      <Num
        label="Phase 4 turns"
        value={form.phase4_turns}
        onChange={(v) => set("phase4_turns", v)}
        error={errors.phase4_turns}
      />
      <p>
        Phases add up to {totalPhases} of {form.total_turns} turns.
      </p>
      <Toggle
        checked={form.enable_tts}
        onChange={(checked) => set("enable_tts", checked)}
      >
        Enable text-to-speech
      </Toggle>

      <h2 id="config-images" tabIndex={-1}>
        Scene illustrations
      </h2>
      <Toggle
        checked={form.enable_image_generation}
        onChange={(checked) => set("enable_image_generation", checked)}
      >
        Enable image generation
      </Toggle>
      {form.enable_image_generation && (
        <>
          <p>
            Manage styles under Image Meta Prompts and appearance descriptions
            under Character Prompts. Import image models from an OpenRouter
            provider on the Providers page.
          </p>
          <Pick
            label="Image meta prompt"
            value={form.image_meta_prompt}
            onChange={(v) => set("image_meta_prompt", v)}
            choices={promptChoices(options.image_meta_prompts ?? [])}
            error={errors.image_meta_prompt}
            optional={!form.enable_image_generation}
          />
          <Pick
            label="Character prompt"
            value={form.character_prompt}
            onChange={(v) => set("character_prompt", v)}
            choices={promptChoices(options.character_prompts ?? [])}
            error={errors.character_prompt}
            optional
          />
          <Pick
            label="OpenRouter image model"
            value={form.image_model}
            onChange={(v) => set("image_model", v)}
            choices={options.image_models ?? []}
            error={errors.image_model}
            optional={!form.enable_image_generation}
          />
          <Field label="Image aspect ratio" error={errors.image_aspect_ratio}>
            <select
              value={form.image_aspect_ratio}
              onChange={(e) => set("image_aspect_ratio", e.target.value)}
            >
              {["16:9", "1:1", "9:16", "4:3", "3:4", "3:2", "2:3"].map(
                (ratio) => (
                  <option key={ratio} value={ratio}>
                    {ratio}
                  </option>
                ),
              )}
            </select>
          </Field>
          <Num
            label="Image timeout (s)"
            value={form.image_timeout}
            onChange={(v) => set("image_timeout", v)}
            error={errors.image_timeout}
          />

          {!!form.image_references?.length &&
            options.image_models?.find((model) => model.id === form.image_model)
              ?.reference_limit === 0 && (
              <p role="alert">
                This image model does not accept reference images. Choose one
                with image input.
              </p>
            )}
          <ImageReferences
            value={form.image_references ?? []}
            onChange={(images) => set("image_references", images)}
            onBusyChange={setUploading}
          />
          {errors.image_references && (
            <p role="alert">{errors.image_references}</p>
          )}
        </>
      )}
      <h2 id="config-refusal" tabIndex={-1}>
        Refusal detection
      </h2>
      <Toggle
        checked={form.enable_refusal_detection}
        onChange={(checked) => set("enable_refusal_detection", checked)}
      >
        Detect and correct refusals
      </Toggle>
      {form.enable_refusal_detection && (
        <>
          <Pick
            label="Classifier prompt"
            value={form.classifier_prompt}
            onChange={(v) => set("classifier_prompt", v)}
            choices={promptChoices(options.classifier_prompts)}
            error={errors.classifier_prompt}
          />
          <Pick
            label="Classifier model"
            value={form.classifier_model}
            onChange={(v) => set("classifier_model", v)}
            choices={models}
            error={errors.classifier_model}
          />
          <Num
            label="Classifier timeout (s)"
            value={form.classifier_timeout}
            onChange={(v) => set("classifier_timeout", v)}
            error={errors.classifier_timeout}
          />
          <Field label="Classifier question">
            <input
              value={form.classifier_question}
              onChange={(e) => set("classifier_question", e.target.value)}
            />
          </Field>
          <Pick
            label="Turn correction prompt"
            value={form.turn_correction_prompt}
            onChange={(v) => set("turn_correction_prompt", v)}
            choices={promptChoices(options.turn_correction_prompts)}
            error={errors.turn_correction_prompt}
          />
          <Pick
            label="Turn correction model"
            value={form.turn_correction_model}
            onChange={(v) => set("turn_correction_model", v)}
            choices={models}
            error={errors.turn_correction_model}
          />
          <Num
            label="Turn correction timeout (s)"
            value={form.turn_correction_timeout}
            onChange={(v) => set("turn_correction_timeout", v)}
            error={errors.turn_correction_timeout}
          />
          <Pick
            label="Game ending turn correction prompt"
            value={form.game_ending_turn_correction_prompt}
            onChange={(v) => set("game_ending_turn_correction_prompt", v)}
            choices={promptChoices(options.turn_correction_prompts)}
            error={errors.game_ending_turn_correction_prompt}
            optional
          />
        </>
      )}

      <h2 id="config-judges" tabIndex={-1}>
        Judge steps
      </h2>
      {form.judge_steps.map((step, index) => (
        <StepEditor
          key={step.id ?? `new-${index}`}
          step={step}
          index={index}
          options={options}
          errors={errors}
          onChange={(next) =>
            set(
              "judge_steps",
              form.judge_steps.map((s, i) => (i === index ? next : s)),
            )
          }
          onRemove={() =>
            set(
              "judge_steps",
              form.judge_steps.filter((_, i) => i !== index),
            )
          }
        />
      ))}
      <div className="toolbar">
        <button
          type="button"
          onClick={() =>
            set("judge_steps", [
              ...form.judge_steps,
              blankStep(form.judge_steps.length + 1),
            ])
          }
        >
          Add judge step
        </button>
      </div>

      <h2 id="config-workflow" tabIndex={-1}>
        Turn workflow
      </h2>
      <WorkflowEditor
        value={form.workflow}
        onChange={(workflow) => set("workflow", workflow)}
      />
      {errors.workflow && (
        <span role="alert" className="field-error">
          {errors.workflow}
        </span>
      )}

      {notice && <p role="status">{notice}</p>}
      <Failure error={remove.error ?? save.error} />
      <div
        id="config-save"
        tabIndex={-1}
        className="toolbar config-save-actions"
      >
        <button type="submit" disabled={save.isPending || uploading}>
          {initial.id ? "Save changes" : "Create configuration"}
        </button>
        {initial.id && (
          <button
            type="button"
            className="danger"
            onClick={async () =>
              (await confirmAction(`Delete ${form.name}?`)) && remove.mutate()
            }
          >
            Delete
          </button>
        )}
      </div>
    </form>
  );
}

export function ConfigListPage() {
  const configs = useQuery({ queryKey: key, queryFn: getConfigs });
  if (configs.isPending) return <Loading />;
  if (configs.error) return <Failure error={configs.error} />;
  return (
    <>
      <h1>Configurations</h1>
      <p>
        <Link to="/manage/configurations/new">New configuration</Link>
      </p>
      {configs.data.configurations.length === 0 ? (
        <p className="empty">No configurations yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Storyteller</th>
              <th>Turns</th>
              <th>Refusal detection</th>
              <th>Images</th>
              <th>Judges</th>
            </tr>
          </thead>
          <tbody>
            {configs.data.configurations.map((c) => (
              <tr key={c.id}>
                <td>
                  <Link to={`/manage/configurations/${c.id}`}>{c.name}</Link>
                </td>
                <td>{c.is_active ? "Active" : "Inactive"}</td>
                <td>{c.storyteller_model}</td>
                <td>{c.total_turns}</td>
                <td>{c.enable_refusal_detection ? "On" : "Off"}</td>
                <td>{c.enable_image_generation ? "On" : "Off"}</td>
                <td>{c.judge_step_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

export function ConfigNewPage() {
  const options = useQuery({
    queryKey: [...key, "options"],
    queryFn: getConfigOptions,
  });
  if (options.isPending) return <Loading />;
  if (options.error) return <Failure error={options.error} />;
  return (
    <>
      <h1>New configuration</h1>
      <ConfigForm initial={blankConfig()} options={options.data} />
    </>
  );
}

export function ConfigEditPage() {
  const id = Number(useParams().id);
  const options = useQuery({
    queryKey: [...key, "options"],
    queryFn: getConfigOptions,
  });
  const config = useQuery({
    queryKey: [...key, id],
    queryFn: () => getConfig(id),
  });
  if (options.isPending || config.isPending) return <Loading />;
  if (options.error || config.error)
    return <Failure error={(options.error ?? config.error) as Error} />;
  return (
    <>
      <h1>{config.data.name}</h1>
      <ConfigForm key={id} initial={config.data} options={options.data} />
    </>
  );
}
