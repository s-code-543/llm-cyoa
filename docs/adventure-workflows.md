# Adventure workflows

Start with `cyoa-game-server/game/engine/turn_execution.py`. Its default node list,
registry, and `execute_turn()` show the entire turn path. Mechanics are in
`nodes.py`; HTTP handlers only authorize the player and call the executor.

In the admin configuration editor, expand **Turn workflow (advanced)** and paste
workflow JSON. `{}` selects the default. See `workflows/arctic-example.json` for
an opt-in Arctic example; no existing adventure is switched automatically.

Version 1 is a sequence with conditional steps, not an arbitrary cyclic graph.
A step can include `"when": {"key": "has_key", "equals": true}` to skip it when a
state field does not match. Generation, validation, and saving are unconditional.
Unknown nodes and unsafe orderings are rejected before execution. At most 32
nodes, 16 model calls, and 180 seconds are allowed per turn; existing refusal and
judge retries remain bounded within this budget. There is no mandatory planning
model call.

## Nodes

| Type | Settings and effect |
| --- | --- |
| RunPython | `code` transforms the working `state` dictionary; `input` contains action, turn, max_turns, and visible history. |
| GateInventory | Optional `probability` (default 0.25), `cooldown_turns` (default 2), `max_new_items` (default 1). Rolls once before generation; concatenated state tells the narrator whether an acquisition is permitted. Requires inventory extraction/merging. `verify_narrative` defaults to true and uses the correction model for a factual consistency check (false disables it). |
| ApplyDifficulty | Uses the existing configuration's random-death curve. Omit if the adventure supplies another mechanism. |
| ApplyRandomPrompt | `probability` (0–1), or `probability_key` naming a state field; appends `prompt` when selected. `ending: true` forces a terminal turn. |
| ConcatenatePrompt | `prompt`, `include_state` (default true), `target` (`system` or `user`). Injects context without changing the saved player action. |
| GenerateTurn | Uses the configuration's storyteller model, prompt, and timeout. Exactly one per turn. |
| ReWriteRefusal | Uses configured cheap classifier and correction model; `max_attempts` is 1–3 including the initial candidate. First-turn refusals still block. |
| ReWriteJudge | Optional configured judge pipeline. Skips terminal candidates and forced endings. |
| ExtractJSON | Removes exactly one fenced `game-state`, standard `json`, or unlabeled fenced JSON object from the final model response; missing or malformed metadata gets at most one extraction repair call (`repair_attempts: 0` disables it). `mode: merge` proposes changes; `deterministic` discards proposed changes. |
| ApplyStateChanges | `allowed_keys` lists narrator-owned top-level fields. Other proposed changes fail the turn. Merges replace whole top-level values; they are not recursive patches. |
| ValidateTurn | Checks state serialization and final narration: two choices while ongoing, no choices for endings, required endings preserved. `strict: false` permits legacy narrative formatting; empty output and hidden-state fences are still rejected. |
| SaveGame | Must follow ValidateTurn and be last. Atomically saves narration, hidden state, workflow, random results, and audit trace. |

When ExtractJSON is configured, the engine supplies the output contract to the
storyteller and correction models automatically. The narrator should return only
proposed changes to allowed fields, for example:

````text
Turn 2 of 10
You pick up the torch.
1) Enter the corridor
2) Return to the stairs
```game-state
{"inventory": ["torch"]}
```
````

Python-controlled fields cannot be changed by the narrator unless explicitly
listed in `allowed_keys`. Identity, ownership, credentials, turn counters, and
terminal flags are engine data outside the editable state dictionary. Hidden
state and model-attempt traces are available to administrators, not player API
responses. The inventory list, when it contains strings, is explicitly projected
into the player-facing inventory display. Prompt instructions still need to prevent the narrator from revealing
secrets in ordinary prose; this is not a guarantee against narrative spoilers.

## Python steps

RunPython uses a separate Python interpreter with an empty environment and a
scratch working directory, a three-second wall timeout, two CPU seconds, and
a 128 MB address-space limit on Linux. macOS does not apply the address-space
limit because Darwin rejects it; the CPU, wall-time, file-descriptor, and
payload limits still apply. Existing lower hard limits are respected.
Use the Linux Docker deployment when the memory limit is required.
Scripts are restricted to data operations: assignment, conditions, loops,
comprehensions, safe collection methods, and basic builtins. `random()`,
`randint(a, b)`, and `choice(values)` use an engine-supplied seeded generator.
Imports, file access, arbitrary function calls, private names, class definitions,
and arbitrary attribute access are rejected before execution. Scripts cannot
access Django or application credentials. Input and output are limited to 1 MB.

This is a restricted Python subset for administrator-authored scripts, **not a
general-purpose sandbox for hostile third-party code**. Do not accept scripts from
players or execute code emitted by a model. Supporting untrusted authors would
require a separate OS/container security boundary.

## Persistence and recovery

Workflow JSON is pinned on the first successful turn; later configuration edits
apply to new games. Model and prompt settings still come from the configuration.
Python and random-prompt nodes derive reproducible draws from the saved game seed,
turn number, and node position. Narration repairs never rerun those nodes. The
legacy difficulty roll remains sampled once during the turn.

Failed execution commits neither the action nor state. A refusal block records an
error exchange without advancing state. SaveGame detects stale concurrent turns.
Rollback restores the target turn's state, workflow, seed, and difficulty metadata.
Rolling back old turns without snapshots resets hidden state to an empty object.
There is no durable mid-turn resume: restarting a failed request may reroll the
legacy difficulty draw, and a failed opening turn has no committed random seed.

Narrative/state validation failures return a recoverable failed request rather
than silently committing invalid state. State metadata repair is bounded to one model call and never rewrites accepted
narrative prose. A visual graph editor is not included in this first version.

## Item-award policies

Place GateInventory before ConcatenatePrompt and GenerateTurn. It writes the
engine-owned inventory_policy object into hidden state. A probability success is
permission, not a requirement to award an item. A two-turn cooldown after an
award on turn 1 blocks turns 2 and 3; turn 4 can roll again. The cooldown begins
only after an accepted unsolicited inventory addition. Consuming, dropping, and using existing
items remain possible on every turn. Starting items can be authored with an
initialization RunPython node before GateInventory.

Suggested starting presets: Haunted House probability 0.20, cooldown_turns 3,
max_new_items 1; Pirate probability 0.80, cooldown_turns 0, max_new_items 3. These
are per-adventure settings, not global defaults. If a narrator violates the award
permission, ApplyStateChanges attempts one full narrative/state repair, then
rejects a still-invalid candidate without advancing the game. Item names are
stable strings; spelling aliases and quantities are not yet a full item-ID system.


Sparse Haunted House and plentiful Pirate examples are in
`workflows/sparse-haunted-house.json` and `workflows/plentiful-pirate.json`.
Narrative consistency verification uses the correction model (falling back to the
classifier/storyteller), with reasoning disabled through OpenRouter's
`reasoning.effort: none` option. It is a fallible model-based fact check, distinct
from the deterministic probability, cooldown, and state-change limits. A failure
can trigger one narrative repair and recheck, within the shared call budget.
Metadata-only repair and classification calls do not inherit narrator output
instructions. Explicit plain `game-state: {...}` output is also supported.
The quota covers unsolicited narrator gifts, not deliberate taking or theft of
available portable objects. The narrator lists successful requested acquisitions
in temporary `_requested_items` metadata alongside `inventory`. The engine removes
this metadata before saving and exempts those items from the unsolicited quota;
only unsolicited awards start cooldown. Optional narrative verification checks
source attribution as well as inventory consistency; this semantic judgment is
fallible. Endings may include darkly comic items such as charred remains.


## Editing and accounting

The configuration editor displays ordered step cards with descriptions, reorder
controls, and ordinary fields for loot settings, prompt text, state fields and
Python. Raw workflow JSON remains available for advanced settings and conditions.
Model choices remain in the storyteller, classifier and correction sections.

Each new execution audit retains `model_requests`: model, status, duration and,
for OpenRouter responses, generation ID and provider usage (including cost when
supplied). Failed turn attempts retain these records too. Missing billing fields
mean unavailable, not free; older requests cannot be reconstructed from this.
