"""title: Anthropic Manifold Pipe
This one does not work. Maybe it could someday?
authors: justinh-rahb and christian-taillon
author_url: https://github.com/justinh-rahb

funding_url: https://github.com/open-webui

version: 0.2.5
required_open_webui_version: 0.3.17
license: MIT
"""

import os
import requests
import json
import time
import secrets
from typing import List, Union, Generator, Iterator
from pathlib import Path
from dataclasses import dataclass
from pydantic import BaseModel, Field
from open_webui.utils.misc import pop_system_message

# ==============================================================================
# GAME STATE MANAGEMENT
# ==============================================================================
# Directory for persisting player state across sessions

SAVE_DIR = Path("/data/wilderness_saves")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class PlayerState:
    """
    Persistent game state for each player/chat combo.
    Tracks progression and game status in the wilderness survival CYOA.
    """
    turn_index: int = 0  # Logical turn number (1-based)
    game_over: bool = False  # Set to True when game should end
    health: int = 100  # Placeholder for future mechanics
    hunger: int = 100  # Placeholder for future mechanics
    luck: int = 50  # Placeholder for future mechanics
    death_is_predictable: bool = True  # 75% predictable, 25% unexpected/comical
    last_processed_turn: int = 0  # Highest turn we've fully processed

def load_state(key: str) -> PlayerState:
    """
    Load a PlayerState from disk, or return a fresh one if it doesn't exist.
    """
    path = SAVE_DIR / f"{key}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return PlayerState(**data)
        except Exception as e:
            print(f"Failed to load state for {key}: {e}")
            return PlayerState()
    return PlayerState()

def save_state(key: str, state: PlayerState) -> None:
    """
    Persist a PlayerState to disk as JSON.
    """
    path = SAVE_DIR / f"{key}.json"
    try:
        path.write_text(json.dumps(state.__dict__))
        path.stat()
    except Exception as e:
        print(f"Failed to save state for {key}: {e}")

# ==============================================================================
# GAME MECHANICS
# ==============================================================================

def death_probability(turn: int, min_p: float = 0.05, max_p: float = 0.40, last_turn: int = 20) -> float:
    """
    Return a probability between 0 and 1 that this turn ends the run.
    - No death chance on turns 1–2.
    - Ramps up between min_p and max_p until turn 19.
    - Turn >= last_turn (20) is a guaranteed safe / finale turn.
    """
    if turn < 3:
        return 0.0
    if turn >= last_turn:
        return 0.0
    if turn >= last_turn - 1:
        return max_p
    slope = (max_p - min_p) / float(last_turn - 3)
    return min_p + (turn - 2) * slope

def should_die_this_turn(state: PlayerState, last_turn: int = 20) -> bool:
    """
    Determine whether this turn should end the game in failure.

    Turn 20+ is always a safe / finale turn.
    """
    if state.turn_index >= last_turn:
        return False

    p = death_probability(state.turn_index, last_turn=last_turn)
    roll = secrets.randbelow(10_000) / 10_000.0
    return roll < p


def determine_death_type(state: PlayerState, predictable_chance: float = 0.75) -> None:
    """
    Decide whether the player's death will be predictable vs. unexpected/comical.
    """
    roll = secrets.randbelow(10_000) / 10_000.0
    state.death_is_predictable = roll < predictable_chance

def process_game_mechanics(state: PlayerState, payload: dict, turn_number: int) -> tuple:
    """
    Execute game mechanics for THIS TURN and optionally inject a GAME_DIRECTIVE
    into the outgoing payload BEFORE the Anthropic API call.

    Returns: (control_text, diagnostic_block, game_over_now, current_death_prob)
    """
    # Set the logical turn index for this call
    state.turn_index = turn_number

    # Calculate death probability for this turn
    current_death_prob = death_probability(state.turn_index, last_turn=20)

    # Decide whether this turn ends the game
    game_over_now = should_die_this_turn(state)
    state.game_over = state.game_over or game_over_now

    if game_over_now:
        determine_death_type(state)

    control_text = None

    if game_over_now:
        death_style = (
            "that makes logical sense based on the player's choices and situation"
            if state.death_is_predictable
            else "that is unexpected and slightly comical, something the player could not foresee"
        )
        control_text = (
            "<GAME_DIRECTIVE>\n"
            "MANDATORY: The player's adventure has come to an END. Game Over.\n"
            "You must conclude the story. Describe how the player dies or fails - "
            f"{death_style}. "
            "DO NOT offer new choices. DO NOT continue the story. DO NOT allow the adventure to continue.\n"
            "Respond only with the death/failure narration. Be definitive.\n"
            "</GAME_DIRECTIVE>"
        )
    elif state.turn_index == 20:
        control_text = (
            "<GAME_DIRECTIVE>\n"
            "MANDATORY: The player's final choice awaits. "
            "Conclude the story based on their choice - they may succeed brilliantly or fail spectacularly. "
            "DO NOT offer further choices after this - this is THE END.\n"
            "</GAME_DIRECTIVE>"
        )

    if control_text is not None:
        payload["messages"].append(
            {
                "role": "user",
                "content": [{"type": "text", "text": control_text}],
            }
        )

    diagnostic_block = (
        f"\n\n[DIAGNOSTIC] turn={state.turn_index} | p_death={current_death_prob:.1%}"
    )

    return (control_text, diagnostic_block, game_over_now, current_death_prob)


class Pipe:
    class Valves(BaseModel):
        ANTHROPIC_API_KEY: str = Field(default="")

    def __init__(self):
        self.type = "manifold"
        self.id = "anthropic"
        self.name = "anthropic/"
        self.valves = self.Valves(
            **{"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "")}
        )

    def get_anthropic_models(self):
        return [
            {
                "id": "claude-haiku-4-5",
                "name": "ClaudeRPG w/engine",
            },
        ]

    def pipes(self) -> List[dict]:
        return self.get_anthropic_models()

    def pipe(self, body: dict, __user__=None) -> Union[str, Generator, Iterator]:
        # ==============================================================================
        # STATE LOADING
        # ==============================================================================
        user_id = "anon"
        if isinstance(__user__, dict) and __user__.get("id"):
            user_id = str(__user__["id"])

        chat_id = body.get("conversation_id") or body.get("id") or "default"
        state_key = f"{user_id}_{chat_id}"

        messages = body.get("messages", [])

        # NEW CHAT DETECTION: no assistant messages => fresh game
        has_assistant = any(m.get("role") == "assistant" for m in messages)
        if not has_assistant:
            state = PlayerState()
        else:
            state = load_state(state_key)

        # ==============================================================================
        # STANDARD MESSAGE PROCESSING
        # ==============================================================================
        system_message, messages = pop_system_message(body["messages"])

        processed_messages = []
        for message in messages:
            processed_content = []
            if isinstance(message.get("content"), list):
                for item in message["content"]:
                    if item["type"] == "text":
                        processed_content.append({"type": "text", "text": item["text"]})
            else:
                processed_content = [
                    {"type": "text", "text": message.get("content", "")}
                ]

            processed_messages.append(
                {"role": message["role"], "content": processed_content}
            )

        # ==============================================================================
        # TURN NUMBER + DEDUP CHECK
        # ==============================================================================
        # Logical turn number = (#assistant messages so far) + 1
        assistant_count = sum(
            1 for m in processed_messages if m.get("role") == "assistant"
        )
        incoming_turn_number = assistant_count + 1

        # If we've already fully processed this turn, DO NOTHING.
        if incoming_turn_number <= state.last_processed_turn:
            return ""

        # ==============================================================================
        # BUILD ANTHROPIC PAYLOAD
        # ==============================================================================
        payload = {
            "model": body["model"][body["model"].find(".") + 1 :],
            "messages": processed_messages,
            "max_tokens": body.get("max_tokens", 4096),
            "stop_sequences": body.get("stop", []),
            **({"system": str(system_message)} if system_message else {}),
            "stream": body.get("stream", False),
        }

        temperature = body.get("temperature", None)
        top_p = body.get("top_p", None)

        if temperature is not None:
            payload["temperature"] = temperature
        elif top_p is not None:
            payload["top_p"] = top_p
        else:
            payload["temperature"] = 0.8

        payload["top_k"] = body.get("top_k", 40)

        # ==============================================================================
        # GAME MECHANICS: RUN ONCE PER TURN, BEFORE API CALL
        # ==============================================================================
        control_text, diagnostic_block, game_over_now, current_death_prob = process_game_mechanics(
            state, payload, incoming_turn_number
        )

        headers = {
            "x-api-key": self.valves.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        url = "https://api.anthropic.com/v1/messages"

        try:
            if body.get("stream", False):
                return self.stream_response(
                    url,
                    headers,
                    payload,
                    state,
                    state_key,
                    incoming_turn_number,
                    diagnostic_block,
                )
            else:
                return self.non_stream_response(
                    url,
                    headers,
                    payload,
                    state,
                    state_key,
                    incoming_turn_number,
                    diagnostic_block,
                )
        except requests.exceptions.RequestException as e:
            return f"Error: Request failed: {e}"
        except Exception as e:
            return f"Error: {e}"

    def stream_response(
        self,
        url,
        headers,
        payload,
        state,
        state_key,
        turn_number,
        diagnostic_block,
    ):
        try:
            with requests.post(
                url, headers=headers, json=payload, stream=True, timeout=(3.05, 60)
            ) as response:
                if response.status_code != 200:
                    raise Exception(
                        f"HTTP Error {response.status_code}: {response.text}"
                    )

                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data["type"] == "content_block_start":
                                    yield data["content_block"]["text"]
                                elif data["type"] == "content_block_delta":
                                    yield data["delta"]["text"]
                                elif data["type"] == "message_stop":
                                    break
                                elif data["type"] == "message":
                                    for content in data.get("content", []):
                                        if content["type"] == "text":
                                            yield content["text"]

                                time.sleep(0.06)
                            except json.JSONDecodeError:
                                pass
                            except KeyError:
                                pass

                # After streaming completes, emit diagnostics and mark the turn as processed
                yield diagnostic_block
                state.last_processed_turn = max(state.last_processed_turn, turn_number)
                save_state(state_key, state)
        except requests.exceptions.RequestException as e:
            yield f"Error: Request failed: {e}"
        except Exception as e:
            yield f"Error: {e}"

    def non_stream_response(
        self,
        url,
        headers,
        payload,
        state,
        state_key,
        turn_number,
        diagnostic_block,
    ):
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=(3.05, 60)
            )
            if response.status_code != 200:
                raise Exception(f"HTTP Error {response.status_code}: {response.text}")

            res = response.json()
            reply_text = (
                res["content"][0]["text"] if "content" in res and res["content"] else ""
            )

            # Mark this logical turn as processed and persist state
            state.last_processed_turn = max(state.last_processed_turn, turn_number)
            save_state(state_key, state)

            return reply_text + diagnostic_block
        except requests.exceptions.RequestException as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"