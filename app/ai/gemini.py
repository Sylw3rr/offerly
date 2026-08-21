"""The one place that talks to Gemini.

Plain HTTP over the httpx already in the requirements, rather than the vendor
SDK: the call is one POST with a JSON schema attached, and a dependency that
pulls in its own auth stack and transport is a poor trade for that.

Everything here fails soft. An extractor that raises takes the webhook down
with it, and a mail router that gets a 500 retries — so a bad afternoon at the
model provider would become duplicated messages in someone's inbox. When this
cannot answer, it returns nothing and the message stays untouched, which is
exactly where it sat before this module existed.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Long enough for a large digest, short enough that the caller is not held.
TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def available() -> bool:
    settings = get_settings()
    return bool(settings.gemini_api_key)


def structured(prompt: str, schema: dict[str, Any]) -> Any | None:
    """Ask for JSON matching `schema`, or None if the model could not be asked.

    `responseSchema` makes the model answer in the shape we want instead of in
    prose that happens to contain JSON, which removes the whole category of
    parsing the reply.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return None

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            # Extraction, not composition: there is one right answer sitting in
            # the text and no reason to sample around it.
            "temperature": 0,
        },
    }

    try:
        response = httpx.post(
            ENDPOINT.format(model=settings.gemini_model),
            json=payload,
            headers={"x-goog-api-key": settings.gemini_api_key},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as failure:
        log.warning("gemini call failed: %s", failure)
        return None

    try:
        import json

        text = body["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError) as failure:
        # A refusal, a safety block, or an empty candidate list all land here.
        log.warning("gemini returned nothing usable: %s", failure)
        return None
