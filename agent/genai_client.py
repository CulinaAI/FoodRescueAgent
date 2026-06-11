from __future__ import annotations
import os

from google import genai


def get_genai_client() -> genai.Client:
    """Build the GenAI client.

    Vertex AI (ADC auth) when GOOGLE_GENAI_USE_VERTEXAI is truthy — this is the
    production path and matches the .NET backend (project culinaai-backend,
    europe-west3). Falls back to a Gemini Developer API key for local dev / tests.
    """
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes"):
        return genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "europe-west3"),
        )
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))


def model_name() -> str:
    """Model id for vision + rescue planning.

    Note: `gemini-flash-latest` is a Developer-API alias and is NOT a valid Vertex
    model id. On Vertex use a versioned id; default mirrors the backend.
    """
    return os.getenv("FRA_GEMINI_MODEL", "gemini-3.5-flash")
