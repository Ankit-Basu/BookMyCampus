import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)


def mask_key(k: str) -> str:
    if not k or len(k) < 10:
        return "***"
    return f"{k[:7]}...{k[-4:]}"


class GroqClient:
    """
    Production-ready Groq API client with:
    1. Automatic API key rotation across multiple configured keys on rate limit (429) or error.
    2. Model fallback cascade (e.g. gpt-oss-120b -> gpt-oss-20b -> qwen3.8-27b).
    3. Native function/tool calling support.
    """

    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        self._lock = threading.Lock()
        self._key_index = 0

    @property
    def keys(self) -> List[str]:
        keys = getattr(settings, "GROQ_API_KEYS", [])
        if not keys and hasattr(settings, "GROQ_API_KEY") and settings.GROQ_API_KEY:
            return [settings.GROQ_API_KEY]
        return [k.strip() for k in keys if k and k.strip()]

    def get_current_key(self) -> Optional[str]:
        keys = self.keys
        if not keys:
            return None
        with self._lock:
            return keys[self._key_index % len(keys)]

    def rotate_key(self, reason: str = "") -> Optional[str]:
        keys = self.keys
        if not keys or len(keys) <= 1:
            return None
        with self._lock:
            old_k = keys[self._key_index % len(keys)]
            self._key_index = (self._key_index + 1) % len(keys)
            new_k = keys[self._key_index % len(keys)]
            logger.warning(
                "Rotating Groq API Key from %s to %s. Reason: %s",
                mask_key(old_k),
                mask_key(new_k),
                reason,
            )
            return new_k

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """
        Execute chat completion with automatic failover across keys and model fallbacks.
        Returns the parsed message dict from choices[0]['message'].
        """
        keys = self.keys
        if not keys:
            raise RuntimeError("No Groq API keys configured in settings.GROQ_API_KEYS.")

        models_to_try = [getattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b")]
        fallback_models = getattr(
            settings,
            "GROQ_FALLBACK_MODELS",
            ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"],
        )
        for fm in fallback_models:
            if fm not in models_to_try:
                models_to_try.append(fm)

        max_key_attempts = len(keys) * 2
        last_error = None

        for model_name in models_to_try:
            for key_attempt in range(max_key_attempts):
                active_key = self.get_current_key()
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = tool_choice

                req = urllib.request.Request(
                    self.ENDPOINT,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {active_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "BookMyCampus-Copilot/1.0",
                    },
                )

                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        choice = data["choices"][0]
                        msg = choice["message"]
                        msg["_model_used"] = model_name
                        msg["_key_used_masked"] = mask_key(active_key)
                        return msg

                except urllib.error.HTTPError as e:
                    body = e.read().decode("utf-8", errors="ignore")
                    last_error = f"HTTP {e.code}: {body}"
                    # HTTP 429 = Rate limited, HTTP 503 = Service Unavailable
                    if e.code in (429, 503):
                        self.rotate_key(f"Rate limited or unavailable ({e.code})")
                        continue
                    # Model not found or decommissioned, break inner loop to try next model
                    if e.code in (404, 400) and ("model" in body.lower() or "decommissioned" in body.lower()):
                        logger.warning("Groq model %s unavailable: %s. Trying fallback model.", model_name, body)
                        break
                    # For other 4xx errors, rotate key and retry once
                    self.rotate_key(f"HTTP {e.code}: {body[:120]}")
                    continue

                except Exception as e:
                    last_error = str(e)
                    self.rotate_key(f"Network error: {e}")
                    continue

        raise RuntimeError(f"All Groq models and keys exhausted. Last error: {last_error}")


groq_client = GroqClient()
