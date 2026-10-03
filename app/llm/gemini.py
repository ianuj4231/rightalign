"""Google Gemini structured-output implementation."""

import logging
import time

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.exceptions import LLMProviderError
from app.llm.base import INTENT_SYSTEM_PROMPT
from app.schemas.llm import IntentClassification

logger = logging.getLogger(__name__)

MAX_GEMINI_ATTEMPTS = 3
INITIAL_RETRY_DELAY_SECONDS = 1.0


class GeminiLLMClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def classify_intent(self, customer_message: str) -> IntentClassification:
        response = None
        for attempt_number in range(1, MAX_GEMINI_ATTEMPTS + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=customer_message,
                    config=types.GenerateContentConfig(
                        system_instruction=INTENT_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_json_schema=IntentClassification.model_json_schema(),
                        temperature=0,
                    ),
                )
                break
            except errors.APIError as exc:
                is_transient_error = exc.code == 429 or exc.code >= 500
                if not is_transient_error:
                    raise LLMProviderError(
                        f"Gemini intent request failed: {exc}"
                    ) from exc
                if attempt_number == MAX_GEMINI_ATTEMPTS:
                    raise LLMProviderError(
                        "Gemini intent request failed after "
                        f"{MAX_GEMINI_ATTEMPTS} transient-error attempts: {exc}"
                    ) from exc

                retry_delay_seconds = INITIAL_RETRY_DELAY_SECONDS * (
                    2 ** (attempt_number - 1)
                )
                logger.warning(
                    "Transient Gemini intent request failure; retrying: "
                    "attempt=%s max_attempts=%s status_code=%s "
                    "retry_delay_seconds=%s",
                    attempt_number,
                    MAX_GEMINI_ATTEMPTS,
                    exc.code,
                    retry_delay_seconds,
                )
                time.sleep(retry_delay_seconds)
            except Exception as exc:
                raise LLMProviderError(f"Gemini intent request failed: {exc}") from exc

        try:
            if response is None:
                raise LLMProviderError("Gemini returned no intent response.")
            if not response.text:
                raise LLMProviderError("Gemini returned an empty intent response.")
            return IntentClassification.model_validate_json(response.text)
        except LLMProviderError:
            raise
        except ValidationError as exc:
            raise LLMProviderError(
                f"Gemini returned invalid structured intent output: {exc}"
            ) from exc
        except Exception as exc:
            raise LLMProviderError(f"Gemini intent request failed: {exc}") from exc
