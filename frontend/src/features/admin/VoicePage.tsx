import { Toggle } from "../../components/Toggle";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getTts, updateTts, type Tts } from "../../api/admin";
import { Failure, Field, Loading, fieldErrors } from "./ui";

function VoiceForm({ initial }: { initial: Tts }) {
  const cache = useQueryClient();
  const [form, setForm] = useState(initial);
  const [notice, setNotice] = useState("");
  const set = <K extends keyof Tts>(name: K, value: Tts[K]) =>
    setForm({ ...form, [name]: value });
  const save = useMutation({
    mutationFn: () => updateTts(form),
    onSuccess: (saved) => {
      cache.setQueryData(["admin", "tts"], saved);
      setNotice("Saved");
    },
  });
  const errors = fieldErrors(save.error);
  return (
    <form
      className="form"
      onSubmit={(event) => {
        event.preventDefault();
        setNotice("");
        save.mutate();
      }}
    >
      <Toggle
        checked={form.enabled}
        onChange={(checked) => set("enabled", checked)}
      >
        Text-to-speech enabled
      </Toggle>
      <Field label="Model" error={errors.openai_model}>
        <select
          value={form.openai_model}
          onChange={(e) => set("openai_model", e.target.value)}
        >
          {form.model_choices.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Voice" error={errors.openai_voice}>
        <select
          value={form.openai_voice}
          onChange={(e) => set("openai_voice", e.target.value)}
        >
          {form.voice_choices.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Maximum text length" error={errors.max_text_length}>
        <input
          type="number"
          value={form.max_text_length}
          onChange={(e) => set("max_text_length", Number(e.target.value))}
        />
      </Field>
      <Field label="Audio retention (days)" error={errors.audio_retention_days}>
        <input
          type="number"
          value={form.audio_retention_days}
          onChange={(e) => set("audio_retention_days", Number(e.target.value))}
        />
      </Field>
      <Toggle
        checked={form.auto_cleanup_enabled}
        onChange={(checked) => set("auto_cleanup_enabled", checked)}
      >
        Automatically clean up old audio
      </Toggle>
      {notice && <p role="status">{notice}</p>}
      <Failure error={Object.keys(errors).length ? null : save.error} />
      <div className="toolbar">
        <button type="submit" disabled={save.isPending}>
          Save settings
        </button>
      </div>
    </form>
  );
}

export function VoicePage() {
  const tts = useQuery({ queryKey: ["admin", "tts"], queryFn: getTts });
  if (tts.isPending) return <Loading />;
  if (tts.error) return <Failure error={tts.error} />;
  return (
    <>
      <h1>Voice settings</h1>
      <VoiceForm initial={tts.data} />
    </>
  );
}
