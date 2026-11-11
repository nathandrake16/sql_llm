"""
src/llm.py
~~~~~~~~~~
Thin wrapper around the Gemini Interactions API using the `google-genai` SDK.

Uses server-side state (`store=True` + `previous_interaction_id`) so the
self-correction loop in agent.py can ask Gemini to fix SQL errors in follow-up
turns without manually resending conversation history.
"""

import os
import sys

from google import genai

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


class GeminiError(Exception):
    """Raised when the Gemini API returns an error or empty output."""


def _get_client() -> genai.Client:
    """Build a Gemini client, preferring config.GEMINI_API_KEY then env vars."""
    api_key = (
        config.GEMINI_API_KEY
        or os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
    )
    if not api_key:
        raise EnvironmentError(
            "No Gemini API key found.\n"
            "Set GEMINI_API_KEY in your environment or paste it into config.py.\n"
            "Get a free key at: https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=api_key)


def call_llm(
    user_input: str,
    system_instruction: str,
    previous_interaction_id: str | None = None,
) -> tuple[str, str]:
    """
    Send a turn to the Gemini Interactions API and return (reply_text, interaction_id).

    Note: In the Interactions API, `system_instruction` and `generation_config`
    are interaction-scoped, so we pass them on every turn even when chaining
    `previous_interaction_id`.

    Args:
        user_input:              The prompt text (schema + question, or SQL error trace).
        system_instruction:      Rigid system prompt enforcing raw SQL output.
        previous_interaction_id: Prior interaction ID for multi-turn self-correction.

    Returns:
        A 2-tuple of (reply_text, interaction_id).

    Raises:
        GeminiError:      If the API request fails or returns empty text.
        EnvironmentError: If no API key is configured.
    """
    client = _get_client()

    kwargs: dict = {
        "model":              config.GEMINI_MODEL,
        "input":              user_input,
        "system_instruction": system_instruction,
        "generation_config":  {"thinking_level": config.THINKING_LEVEL},
        "store":              True,   # required to chain previous_interaction_id
        "timeout":            config.REQUEST_TIMEOUT,
    }
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id

    try:
        interaction = client.interactions.create(**kwargs)
    except Exception as e:
        raise GeminiError(f"Gemini API error: {e}") from e

    if getattr(interaction, "status", None) == "failed":
        err = getattr(interaction, "error", None) or "Interaction failed."
        raise GeminiError(f"Gemini interaction failed: {err}")

    text = (interaction.output_text or "").strip()
    if not text:
        raise GeminiError("Gemini returned no text output.")

    return text, interaction.id
