import os
import pytest
from unittest.mock import patch

from app.core.llm import get_llm, get_llm_info, extract_json

def test_heuristic_when_no_key(monkeypatch):
    # Ensure no keys
    for key in ["OPENAI_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "OLLAMA_URL", "LLM_PROVIDER"]:
        monkeypatch.delenv(key, raising=False)
    # Also patch settings
    with patch("app.core.llm.settings") as mock_settings:
        mock_settings.openai_api_key = None
        mock_settings.groq_api_key = None
        mock_settings.google_api_key = None
        mock_settings.anthropic_api_key = None
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.llm_provider = "auto"
        # Reimport logic: get_llm checks os.getenv and settings
        # Since we cleared env, should return None or Ollama (if OLLAMA_URL set)
        # But we set OLLAMA_URL to localhost, so it will return Ollama provider
        # To test heuristic, we need to ensure OLLAMA_URL not considered without key
        monkeypatch.delenv("OLLAMA_URL", raising=False)
        # Patch OLLAMA_URL to empty
        with patch.dict(os.environ, {}, clear=False):
            # Force no provider
            with patch("app.core.llm._detect_provider", return_value=None):
                llm = get_llm()
                assert llm is None

def test_detect_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    llm = get_llm()
    assert llm is not None
    assert llm.provider == "openai"
    assert "gpt" in llm.model or "mini" in llm.model

def test_detect_groq(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-groq")
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    # Also clear settings to avoid auto picking openai from settings
    import app.config
    monkeypatch.setattr(app.config.settings, "openai_api_key", None)
    monkeypatch.setattr(app.config.settings, "groq_api_key", "gsk-test-groq")
    llm = get_llm()
    assert llm is not None
    assert llm.provider == "groq"

def test_detect_gemini(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-gemini")
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    import app.config
    monkeypatch.setattr(app.config.settings, "openai_api_key", None)
    monkeypatch.setattr(app.config.settings, "groq_api_key", None)
    monkeypatch.setattr(app.config.settings, "google_api_key", "AIza-test-gemini")
    llm = get_llm()
    assert llm is not None
    assert llm.provider == "gemini"

def test_detect_claude(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    import app.config
    monkeypatch.setattr(app.config.settings, "openai_api_key", None)
    monkeypatch.setattr(app.config.settings, "groq_api_key", None)
    monkeypatch.setattr(app.config.settings, "google_api_key", None)
    monkeypatch.setattr(app.config.settings, "anthropic_api_key", "sk-ant-test")
    llm = get_llm()
    assert llm is not None
    assert llm.provider == "claude"

def test_detect_ollama_explicit(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    llm = get_llm()
    assert llm is not None
    assert llm.provider == "ollama"

def test_force_provider_groq(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-groq")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    llm = get_llm()
    assert llm.provider == "groq"

def test_extract_json_plain():
    assert extract_json('{"a": 1, "b": 2}') == {"a": 1, "b": 2}

def test_extract_json_markdown():
    text = '```json\n{"code": "result = df.head()", "explanation": "test"}\n```'
    assert extract_json(text) == {"code": "result = df.head()", "explanation": "test"}

def test_extract_json_wrapped():
    text = 'Here is JSON: {"intent": "visualization", "chart_type": "bar"} and some text'
    assert extract_json(text)["intent"] == "visualization"

def test_llm_info():
    info = get_llm_info()
    assert "provider" in info
    assert "model" in info
    assert "configured" in info
