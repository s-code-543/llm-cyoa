import { Button, Card } from "@heroui/react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createDifficulty,
  deleteDifficulty,
  getDifficulties,
  updateDifficulty,
  type Difficulty,
} from "../../api/admin";
import { Failure, Field, Loading, fieldErrors } from "./ui";

const key = ["admin", "difficulty"];
const DEFAULT_CURVE = [0.05, 0.1, 0.2, 0.35, 0.4];

export function CurvePreview({ points }: { points: number[] }) {
  const coords = points
    .map((p, i) => `${(i / (points.length - 1)) * 100},${100 - p * 100}`)
    .join(" ");
  return (
    <svg
      viewBox="0 0 100 100"
      role="img"
      aria-label="Difficulty curve preview"
      width="240"
      height="120"
      preserveAspectRatio="none"
    >
      <rect
        width="100"
        height="100"
        fill="none"
        stroke="currentColor"
        opacity="0.3"
      />
      <polyline
        points={coords}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function DifficultyListPage() {
  const navigate = useNavigate();
  const profiles = useQuery({ queryKey: key, queryFn: getDifficulties });
  if (profiles.isPending) return <Loading />;
  if (profiles.error) return <Failure error={profiles.error} />;
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Difficulty profiles</h1>
          <p className="text-muted">
            Manage the challenge curves used in your adventures.
          </p>
        </div>
        <Button onPress={() => navigate("/manage/difficulty/new")}>
          New profile
        </Button>
      </div>
      {profiles.data.profiles.length === 0 ? (
        <p className="empty">No profiles yet.</p>
      ) : (
        <div className="profile-grid">
          {profiles.data.profiles.map((p) => (
            <Card key={p.id} className="admin-panel">
              <Card.Content>
                <h2 className="profile-title">{p.name}</h2>
                <p className="text-muted">
                  {p.description || "No description provided."}
                </p>
                <div className="curve-preview">
                  {p.curve_points ? (
                    <CurvePreview points={p.curve_points} />
                  ) : (
                    <code>{p.function}</code>
                  )}
                </div>
                <Button
                  variant="secondary"
                  onPress={() => navigate(`/manage/difficulty/${p.id}`)}
                >
                  Edit profile
                </Button>
              </Card.Content>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}

function DifficultyForm({ profile }: { profile?: Difficulty }) {
  const navigate = useNavigate();
  const cache = useQueryClient();
  const [name, setName] = useState(profile?.name ?? "");
  const [description, setDescription] = useState(profile?.description ?? "");
  const [mode, setMode] = useState<"curve" | "function">(
    profile && !profile.curve_points ? "function" : "curve",
  );
  const [points, setPoints] = useState(profile?.curve_points ?? DEFAULT_CURVE);
  const [fn, setFn] = useState(profile?.function ?? "");
  const [notice, setNotice] = useState("");

  const input = {
    name,
    description,
    ...(mode === "curve" ? { curve_points: points } : { function: fn }),
  };
  const save = useMutation({
    mutationFn: () =>
      profile ? updateDifficulty(profile.id, input) : createDifficulty(input),
    onSuccess: (saved) => {
      cache.invalidateQueries({ queryKey: key });
      setFn(saved.function);
      if (profile) setNotice("Saved");
      else navigate(`/manage/difficulty/${saved.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteDifficulty(profile!.id),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: key });
      navigate("/manage/difficulty");
    },
  });
  const errors = fieldErrors(save.error);
  const failure =
    remove.error ?? (Object.keys(errors).length ? null : save.error);

  return (
    <form
      className="form"
      onSubmit={(event) => {
        event.preventDefault();
        setNotice("");
        save.mutate();
      }}
    >
      <Field label="Name" error={errors.name}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </Field>
      <Field label="Description">
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      <fieldset>
        <legend>Define by</legend>
        <label>
          <input
            type="radio"
            checked={mode === "curve"}
            onChange={() => setMode("curve")}
          />{" "}
          Curve
        </label>{" "}
        <label>
          <input
            type="radio"
            checked={mode === "function"}
            onChange={() => setMode("function")}
          />{" "}
          Function
        </label>
      </fieldset>
      {mode === "curve" ? (
        <>
          {points.map((value, i) => (
            <label key={i}>
              Point {i + 1}: {value.toFixed(2)}
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={value}
                onChange={(e) =>
                  setPoints(
                    points.map((p, j) =>
                      j === i ? Number(e.target.value) : p,
                    ),
                  )
                }
              />
            </label>
          ))}
          <CurvePreview points={points} />
          {errors.curve_points && (
            <span role="alert" className="field-error">
              {errors.curve_points}
            </span>
          )}
        </>
      ) : (
        <Field
          label="Function of x (turn) and n (total turns)"
          error={errors.function}
        >
          <input
            value={fn}
            onChange={(e) => setFn(e.target.value)}
            placeholder="0.05 + 0.35 * (x/n)**2"
          />
        </Field>
      )}
      {notice && <p role="status">{notice}</p>}
      <Failure error={failure} />
      <div className="toolbar">
        <button type="submit" disabled={save.isPending}>
          {profile ? "Save changes" : "Create profile"}
        </button>
        {profile && (
          <button
            type="button"
            className="danger"
            onClick={() =>
              window.confirm(`Delete ${profile.name}?`) && remove.mutate()
            }
          >
            Delete
          </button>
        )}
      </div>
    </form>
  );
}

export const DifficultyNewPage = () => (
  <>
    <h1>New difficulty profile</h1>
    <DifficultyForm />
  </>
);

export function DifficultyEditPage() {
  const id = Number(useParams().id);
  const profiles = useQuery({ queryKey: key, queryFn: getDifficulties });
  if (profiles.isPending) return <Loading />;
  const profile = profiles.data?.profiles.find((p) => p.id === id);
  if (!profile)
    return (
      <p className="empty" role="alert">
        Profile not found.
      </p>
    );
  return (
    <>
      <h1>{profile.name}</h1>
      <DifficultyForm key={profile.id} profile={profile} />
    </>
  );
}
