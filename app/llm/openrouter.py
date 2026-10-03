"""OpenRouter structured-output implementation."""

from openai import OpenAI
from pydantic import ValidationError

from app.exceptions import LLMProviderError
from app.llm.base import INTENT_SYSTEM_PROMPT
from app.schemas.llm import IntentClassification


class OpenRouterLLMClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._model = model

    def classify_intent(self, customer_message: str) -> IntentClassification:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": customer_message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "intent_classification",
                        "strict": True,
                        "schema": IntentClassification.model_json_schema(),
                    },
                },
                temperature=0,
            )
            content = response.choices[0].message.content
            if not content:
                raise LLMProviderError("OpenRouter returned an empty intent response.")
            return IntentClassification.model_validate_json(content)
        except LLMProviderError:
            raise
        except (ValidationError, IndexError, AttributeError) as exc:
            raise LLMProviderError(
                f"OpenRouter returned invalid structured intent output: {exc}"
            ) from exc
        except Exception as exc:
            raise LLMProviderError(f"OpenRouter intent request failed: {exc}") from exc
