"""
Multi-provider LLM abstraction for InsightAgent.
Supports: OpenAI, Groq (OpenAI-compatible), Gemini (Google), Claude (Anthropic), Ollama (local), plus heuristic fallback.

Design:
- Unified async `chat(system, user, json_mode=False, temperature=0.2, max_tokens=400) -> str`
- Factory `get_llm()` picks provider based on LLM_PROVIDER env or auto-detects first available key.
- All providers use httpx or SDK if available, but fallback to httpx so no heavy deps required.
- If no provider configured, returns None and caller should use heuristic fallback.

Env:
- LLM_PROVIDER: openai | groq | gemini | claude | ollama | auto (default auto)
- LLM_MODEL: model name override per provider, or global
- OPENAI_API_KEY, OPENAI_MODEL
- GROQ_API_KEY, GROQ_MODEL
- GOOGLE_API_KEY (or GEMINI_API_KEY), GEMINI_MODEL
- ANTHROPIC_API_KEY, ANTHROPIC_MODEL (or CLAUDE_MODEL)
- OLLAMA_URL (default http://localhost:11434), OLLAMA_MODEL

Usage:
    from app.core.llm import get_llm
    llm = get_llm()
    if llm:
        content = await llm.chat(system_prompt, user_prompt, json_mode=True)
"""

import os
import json
import re
from typing import Optional, Dict, Any

from app.config import settings

# Optional imports — gracefully handle missing SDKs
try:
    from openai import AsyncOpenAI  # type: ignore

    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

try:
    import httpx  # type: ignore

    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

# Provider model defaults
PROVIDER_DEFAULTS = {
    "openai": "gpt-4o-mini",
    "groq": "llama-3.1-8b-instant",  # Groq fast model
    "gemini": "gemini-1.5-flash",
    "claude": "claude-3-5-sonnet-20240620",
    "ollama": "llama3.1:8b",
}


def _is_dummy_key(key: Optional[str]) -> bool:
    if not key:
        return True
    k = key.strip()
    if k in ["sk-...", "sk-...dummy", "gsk_...", "AIza...", "sk-ant-...", ""]:
        return True
    # Check for placeholder patterns
    if k.endswith("...") or k == "sk-..." or "your" in k.lower():
        return True
    return False


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = (
        os.getenv(
            name, getattr(settings, name.lower(), None) if hasattr(settings, name.lower()) else None
        )
        or default
    )
    if _is_dummy_key(val):
        return None
    return val


class LLMProvider:
    """Base class"""

    def __init__(self, model: str):
        self.model = model
        self.provider = "base"

    async def chat(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.provider}:{self.model}>"


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None):
        super().__init__(model)
        self.provider = "openai" if not base_url or "groq" not in base_url else "groq"
        self.api_key = api_key
        self.base_url = base_url

    async def chat(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        if _HAS_OPENAI:
            kwargs: Dict[str, Any] = {}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            client = AsyncOpenAI(api_key=self.api_key, **kwargs)
            req = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                req["response_format"] = {"type": "json_object"}
            resp = await client.chat.completions.create(**req)
            return resp.choices[0].message.content or ""
        # httpx fallback
        if not _HAS_HTTPX:
            raise RuntimeError("httpx not installed for OpenAI fallback")
        url = (self.base_url or "https://api.openai.com/v1") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]


class GroqProvider(OpenAIProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(api_key, model, base_url="https://api.groq.com/openai/v1")
        self.provider = "groq"


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(model)
        self.provider = "gemini"
        self.api_key = api_key

    async def chat(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        # Try SDK if available
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model, system_instruction=system)
            gen_config: Dict[str, Any] = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            if json_mode:
                gen_config["response_mime_type"] = "application/json"
            resp = await model.generate_content_async(user, generation_config=gen_config)
            # resp.text or resp.candidates
            if hasattr(resp, "text") and resp.text:
                return resp.text
            if hasattr(resp, "candidates") and resp.candidates:
                parts = resp.candidates[0].content.parts
                return "".join(p.text for p in parts if hasattr(p, "text"))
            return str(resp)
        except ImportError:
            pass
        except Exception as e:
            # SDK failed, try http
            print(f"Gemini SDK failed, trying http: {e}")

        if not _HAS_HTTPX:
            raise RuntimeError("httpx not installed for Gemini")
        # HTTP fallback: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        # Combine system+user for Gemini (system not well supported in v1beta)
        prompt = f"System: {system}\n\nUser: {user}"
        if json_mode:
            prompt += "\n\nReturn ONLY valid JSON, no markdown."
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            # Extract text
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return json.dumps(data)


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(model)
        self.provider = "claude"
        self.api_key = api_key

    async def chat(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        try:
            import anthropic  # type: ignore

            # Try async
            try:
                from anthropic import AsyncAnthropic  # type: ignore

                client = AsyncAnthropic(api_key=self.api_key)
                kwargs: Dict[str, Any] = {
                    "model": self.model,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                resp = await client.messages.create(**kwargs)
                text = "".join(block.text for block in resp.content if hasattr(block, "text"))
                return text
            except ImportError:
                # Sync fallback
                client = anthropic.Anthropic(api_key=self.api_key)
                resp = client.messages.create(
                    model=self.model,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return "".join(block.text for block in resp.content if hasattr(block, "text"))
        except ImportError:
            pass
        except Exception as e:
            print(f"Claude SDK failed, trying http: {e}")

        if not _HAS_HTTPX:
            raise RuntimeError("httpx not installed for Claude")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        # For json_mode, instruct in system
        sys_prompt = system
        if json_mode:
            sys_prompt += "\nReturn ONLY valid JSON, no markdown, no extra text."
        payload = {
            "model": self.model,
            "system": sys_prompt,
            "messages": [{"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            try:
                return "".join(block["text"] for block in data["content"] if "text" in block)
            except (KeyError, TypeError):
                return json.dumps(data)


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str):
        super().__init__(model)
        self.provider = "ollama"
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        if not _HAS_HTTPX:
            raise RuntimeError("httpx not installed for Ollama")
        # Ollama chat API: POST /api/chat
        url = f"{self.base_url}/api/chat"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if json_mode:
            # Instruct to return JSON
            messages[1]["content"] += "\n\nReturn ONLY valid JSON."
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        # Ollama also supports format: json
        if json_mode:
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            # data like {"message": {"content": "..."}, "done": true}
            return (
                data.get("message", {}).get("content", "")
                or data.get("response", "")
                or json.dumps(data)
            )


def _detect_provider() -> Optional[LLMProvider]:
    """Auto-detect first available provider from env."""
    # Use _get_env which filters dummy keys; for ollama only consider explicit env var, not default
    openai_key = _get_env("OPENAI_API_KEY") or _get_env("openai_api_key")
    groq_key = _get_env("GROQ_API_KEY") or _get_env("groq_api_key")
    gemini_key = (
        _get_env("GOOGLE_API_KEY") or _get_env("GEMINI_API_KEY") or _get_env("google_api_key")
    )
    claude_key = (
        _get_env("ANTHROPIC_API_KEY") or _get_env("CLAUDE_API_KEY") or _get_env("anthropic_api_key")
    )
    # Only consider Ollama if explicitly set via env var (not default)
    ollama_url_explicit = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_MODEL")
    ollama_url = _get_env("OLLAMA_URL") if ollama_url_explicit else None

    # Also check generic LLM_PROVIDER
    provider_env = (
        os.getenv("LLM_PROVIDER") or getattr(settings, "llm_provider", "auto") or "auto"
    ).lower()

    # If explicit provider set, use it (even if key missing, will error and fallback)
    # heuristic explicitly disables LLM — return None for fallback_coder
    if provider_env == "heuristic":
        return None
    if provider_env != "auto":
        if provider_env == "openai" and openai_key:
            model = (
                os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or PROVIDER_DEFAULTS["openai"]
            )
            return OpenAIProvider(openai_key, model)
        if provider_env == "groq" and groq_key:
            model = os.getenv("GROQ_MODEL") or os.getenv("LLM_MODEL") or PROVIDER_DEFAULTS["groq"]
            return GroqProvider(groq_key, model)
        if provider_env in ("gemini", "google") and gemini_key:
            model = (
                os.getenv("GEMINI_MODEL")
                or os.getenv("GOOGLE_MODEL")
                or os.getenv("LLM_MODEL")
                or PROVIDER_DEFAULTS["gemini"]
            )
            return GeminiProvider(gemini_key, model)
        if provider_env in ("claude", "anthropic") and claude_key:
            model = (
                os.getenv("CLAUDE_MODEL")
                or os.getenv("ANTHROPIC_MODEL")
                or os.getenv("LLM_MODEL")
                or PROVIDER_DEFAULTS["claude"]
            )
            return ClaudeProvider(claude_key, model)
        if provider_env == "ollama":
            url = ollama_url or "http://localhost:11434"
            model = (
                os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or PROVIDER_DEFAULTS["ollama"]
            )
            return OllamaProvider(url, model)
        # If explicit but no key, fall through to auto

    # Auto mode: pick first available
    if openai_key:
        model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or PROVIDER_DEFAULTS["openai"]
        return OpenAIProvider(openai_key, model)
    if groq_key:
        model = os.getenv("GROQ_MODEL") or os.getenv("LLM_MODEL") or PROVIDER_DEFAULTS["groq"]
        return GroqProvider(groq_key, model)
    if gemini_key:
        model = os.getenv("GEMINI_MODEL") or os.getenv("LLM_MODEL") or PROVIDER_DEFAULTS["gemini"]
        return GeminiProvider(gemini_key, model)
    if claude_key:
        model = os.getenv("CLAUDE_MODEL") or os.getenv("LLM_MODEL") or PROVIDER_DEFAULTS["claude"]
        return ClaudeProvider(claude_key, model)
    if ollama_url or os.getenv("OLLAMA_MODEL"):
        url = ollama_url or "http://localhost:11434"
        model = os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or PROVIDER_DEFAULTS["ollama"]
        # Check if ollama is reachable? Don't check now, just return provider; will fail gracefully and fallback
        return OllamaProvider(url, model)

    # Explicit ollama provider
    if (
        os.getenv("LLM_PROVIDER") == "ollama"
        or getattr(settings, "llm_provider", "auto") == "ollama"
    ):
        url = ollama_url or os.getenv("OLLAMA_URL") or "http://localhost:11434"
        model = os.getenv("OLLAMA_MODEL") or getattr(
            settings, "ollama_model", PROVIDER_DEFAULTS["ollama"]
        )
        return OllamaProvider(url, model)

    return None


def get_llm() -> Optional[LLMProvider]:
    """Factory — returns provider or None if no key configured."""
    try:
        return _detect_provider()
    except Exception as e:
        print(f"LLM detection failed: {e}")
        return None


def get_llm_info() -> Dict[str, Any]:
    """For /health and UI: which provider is active."""
    llm = get_llm()
    if not llm:
        return {
            "provider": "heuristic",
            "model": "fallback",
            "configured": False,
            "available_providers": _available_providers_list(),
        }
    return {
        "provider": llm.provider,
        "model": llm.model,
        "configured": True,
        "available_providers": _available_providers_list(),
    }


def _available_providers_list():
    providers = []
    if _get_env("OPENAI_API_KEY") or _get_env("openai_api_key"):
        providers.append("openai")
    if _get_env("GROQ_API_KEY") or _get_env("groq_api_key"):
        providers.append("groq")
    if _get_env("GOOGLE_API_KEY") or _get_env("GEMINI_API_KEY") or _get_env("google_api_key"):
        providers.append("gemini")
    if _get_env("ANTHROPIC_API_KEY") or _get_env("CLAUDE_API_KEY") or _get_env("anthropic_api_key"):
        providers.append("claude")
    if _get_env("OLLAMA_URL") or os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_MODEL"):
        # Only count ollama if explicitly set
        if os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_MODEL"):
            providers.append("ollama")
    if not providers:
        providers.append("heuristic (no key)")
    return providers


# Helper for JSON extraction (in case LLM wraps JSON in markdown)
def extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM output that may contain markdown fences."""
    text = text.strip()
    # Remove ```json ... ``` fences
    if "```" in text:
        # Find first { and last }
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        else:
            # Fallback: extract between first { and last }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                text = text[start : end + 1]
    # If still not JSON, try to find JSON object
    if not text.strip().startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
    return json.loads(text)
