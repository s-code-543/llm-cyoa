"""
title: Hard Mode CYOA Filter
version: 0.1.0
description: Adds a low and increasing chance of death on each real CYOA choice, after a short grace period.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
import hashlib


class Filter:
    class Valves(BaseModel):
        debug: bool = Field(
            default=True,
            description="Log Hard Mode decisions to stdout.",
        )
        grace_choices: int = Field(
            default=2,
            description="Number of early choices with zero death chance.",
        )
        min_p: float = Field(
            default=0.05,
            description="Starting death probability after the grace period.",
        )
        max_p: float = Field(
            default=0.40,
            description="Maximum death probability after ramping.",
        )
        ramp_choices: int = Field(
            default=10,
            description="Number of choices over which to ramp from min_p to max_p.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.toggle = True  # per-chat toggle in UI

    # ----------------- helpers -----------------

    def _extract_text(self, msg: dict) -> str:
        """Normalize content to a single string."""
        content = msg.get("content", "")
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(parts)
        return str(content)

    def _set_text(self, msg: dict, new_text: str) -> None:
        """Write text back, handling string or list formats."""
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    item["text"] = new_text
                    msg["content"] = content
                    return
            content.append({"type": "text", "text": new_text})
            msg["content"] = content
        else:
            msg["content"] = new_text

    def _choice_index(self, messages: List[dict], last_user_idx: int) -> Optional[int]:
        """
        Compute the 1-based index of this user message as a *real CYOA choice*.

        A real choice = user message that occurs AFTER at least one assistant message.
        We count how many such user-after-assistant messages happened before this one.
        If this last user message is not a real choice, return None.
        """
        seen_assistant = False
        prior_choices = 0

        for i, m in enumerate(messages[:last_user_idx]):
            role = m.get("role")
            if role == "assistant":
                seen_assistant = True
            elif role == "user" and seen_assistant:
                prior_choices += 1

        # For the last user message itself:
        if not messages[last_user_idx].get("role") == "user":
            return None

        if not seen_assistant:
            # No assistant before this user -> pre-game setup, not a choice.
            return None

        # This user message is a real choice; its index is prior_choices + 1
        return prior_choices + 1

    def _death_probability(self, choice_idx: int) -> float:
        """
        Stateless probability curve based on choice index:

        - For choice_idx <= grace_choices: 0.0 (no death chance).
        - Then ramp from min_p to max_p over ramp_choices choices.
        - After that, stay at max_p.
        """
        g = self.valves.grace_choices
        min_p = self.valves.min_p
        max_p = self.valves.max_p
        r = self.valves.ramp_choices

        if choice_idx <= g:
            return 0.0

        # How many choices since grace ended
        effective = choice_idx - g

        if effective >= r:
            return max_p

        # Linearly interpolate between min_p and max_p over [1..r]
        # effective = 1 -> min_p, effective = r -> max_p
        if r <= 1:
            return max_p

        frac = (effective - 1) / (r - 1)
        return min_p + frac * (max_p - min_p)

    def _deterministic_roll(
        self, chat_id: str, choice_idx: int, user_text: str
    ) -> float:
        """
        Pseudo-random value in [0.0, 1.0) derived from chat_id, choice_idx, and user_text.
        Same inputs => same roll, so duplicate filter runs behave identically.
        """
        seed = f"{chat_id}|{choice_idx}|{user_text}"
        h = hashlib.sha256(seed.encode("utf-8")).digest()
        return int.from_bytes(h[:4], "big") / 2**32

    # ----------------- inlet -----------------

    async def inlet(
        self,
        body: dict,
        __event_emitter__,
        __user__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __request__=None,
    ) -> dict:
        if not self.toggle:
            return body

        try:
            messages: List[dict] = body.get("messages", [])
            if not messages:
                return body

            chat_id = (
                body.get("chat_id")
                or body.get("conversation_id")
                or body.get("id")
                or "default"
            )

            # Find last user message
            last_user_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    last_user_idx = i
                    break

            if last_user_idx is None:
                return body

            last_msg = messages[last_user_idx]
            user_text = self._extract_text(last_msg)

            # If this exact user message already has a directive, do nothing
            if "<GAME_DIRECTIVE>" in user_text:
                if self.valves.debug:
                    print(
                        "[HARD_MODE] last user msg already has GAME_DIRECTIVE; skipping."
                    )
                return body

            # Determine if this is a real choice and what its index is
            choice_idx = self._choice_index(messages, last_user_idx)
            if choice_idx is None:
                if self.valves.debug:
                    print("[HARD_MODE] last user msg is not a real choice; skipping.")
                return body

            # Compute probability and deterministic roll
            p_death = self._death_probability(choice_idx)
            roll = self._deterministic_roll(chat_id, choice_idx, user_text)
            will_die = (p_death > 0.0) and (roll < p_death)

            if will_die:
                directive = (
                    "<GAME_DIRECTIVE>"
                    "HARD MODE: On this turn, the player character must die or "
                    "suffer an irreversible failure that ends the adventure. "
                    "End the story fully on THIS turn and do not offer further choices."
                    "</GAME_DIRECTIVE>"
                )
            else:
                directive = (
                    "<GAME_DIRECTIVE>"
                    "HARD MODE: Continue the adventure into the next turn. Apply "
                    "realistic and meaningful consequences for the player's choice, "
                    "keep the difficulty high, and present exactly two non-trivial options."
                    "</GAME_DIRECTIVE>"
                )

            new_text = user_text.rstrip() + "\n\n" + directive
            self._set_text(last_msg, new_text)

            if self.valves.debug:
                print(
                    "[HARD_MODE] chat=%s choice_idx=%d p_death=%.3f roll=%.4f will_die=%s"
                    % (chat_id, choice_idx, p_death, roll, will_die)
                )

            body["messages"] = messages
            return body

        except Exception as e:
            print(f"[HARD_MODE] ERROR in inlet: {e!r}")
            return body

    # ----------------- passthroughs -----------------

    def stream(self, event: dict) -> dict:
        return event

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        return body
