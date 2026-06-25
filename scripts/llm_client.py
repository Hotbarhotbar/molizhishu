"""
Small OpenAI-compatible LLM client used by the topic scout MVP.

It intentionally depends only on the Python standard library so the workflow can
run in a clean environment. The default mode is no LLM call; callers opt in by
providing an API key and model.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "model": "qwen-plus",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "model": "moonshot-v1-8k",
    },
    "custom": {
        "base_url": "",
        "api_key_env": "LLM_API_KEY",
        "model": "",
    },
}


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout: int = 30
    temperature: float = 0.3
    max_tokens: int = 900

    @classmethod
    def from_sources(
        cls,
        *,
        provider: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> "LLMConfig":
        default_provider = "custom" if os.environ.get("LLM_BASE_URL") else "openai"
        selected_provider = (provider or os.environ.get("LLM_PROVIDER") or default_provider).lower()
        defaults = PROVIDER_DEFAULTS.get(selected_provider, PROVIDER_DEFAULTS["custom"])

        resolved_base_url = (
            base_url
            or os.environ.get("LLM_BASE_URL")
            or defaults.get("base_url", "")
        ).rstrip("/")
        key_env = defaults.get("api_key_env", "LLM_API_KEY")
        resolved_api_key = (
            api_key
            or os.environ.get("LLM_API_KEY")
            or os.environ.get(key_env)
            or ""
        )
        resolved_model = model or os.environ.get("LLM_MODEL") or defaults.get("model", "")

        return cls(
            provider=selected_provider,
            base_url=resolved_base_url,
            api_key=resolved_api_key,
            model=resolved_model,
            timeout=timeout or int(os.environ.get("LLM_TIMEOUT", "30")),
            temperature=temperature
            if temperature is not None
            else float(os.environ.get("LLM_TEMPERATURE", "0.3")),
            max_tokens=max_tokens or int(os.environ.get("LLM_MAX_TOKENS", "900")),
        )

    def missing_reason(self) -> str:
        if not self.base_url:
            return "llm_base_url_missing"
        if not self.api_key:
            return "llm_api_key_missing"
        if not self.model:
            return "llm_model_missing"
        return ""

    def is_ready(self) -> bool:
        return not self.missing_reason()


@dataclass(frozen=True)
class LLMResult:
    ok: bool
    content: str = ""
    error: str = ""
    raw: dict[str, Any] | None = None


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    def chat(self, messages: list[dict[str, str]]) -> LLMResult:
        missing = self.config.missing_reason()
        if missing:
            return LLMResult(ok=False, error=missing)

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return LLMResult(ok=False, error=f"http_{exc.code}: {detail[:300]}")
        except Exception as exc:
            return LLMResult(ok=False, error=str(exc))

        try:
            parsed = json.loads(body)
            content = parsed["choices"][0]["message"]["content"]
            return LLMResult(ok=True, content=str(content), raw=parsed)
        except Exception as exc:
            return LLMResult(ok=False, error=f"invalid_llm_response: {exc}; body={body[:300]}")


def parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(cleaned[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
