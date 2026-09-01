"""Tests du fallback IA séquentiel : Gemini -> DeepSeek -> Mistral -> OpenAI."""
import asyncio
import pytest
import core


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_gemini_ok_no_fallback(monkeypatch):
    calls = []

    async def g(s, p, t):
        calls.append("gemini")
        return "gemini-answer"

    async def oai(client, model, s, p, t):
        calls.append(model)
        return "should-not-run"

    monkeypatch.setattr(core, "_gemini_text", g)
    monkeypatch.setattr(core, "_oai_text", oai)
    monkeypatch.setattr(core, "_deepseek_client", object())
    monkeypatch.setattr(core, "_mistral_client", None)
    monkeypatch.setattr(core, "_openai_client", None)

    out = _run(core.gemini_generate("sys", "prompt"))
    assert out == "gemini-answer"
    assert calls == ["gemini"]


def test_gemini_quota_falls_back_to_deepseek(monkeypatch):
    calls = []

    async def g(s, p, t):
        calls.append("gemini")
        raise Exception("429 RESOURCE_EXHAUSTED: quota exceeded")

    async def oai(client, model, s, p, t):
        calls.append(model)
        return "deepseek-answer"

    monkeypatch.setattr(core, "_gemini_text", g)
    monkeypatch.setattr(core, "_oai_text", oai)
    monkeypatch.setattr(core, "_deepseek_client", object())
    monkeypatch.setattr(core, "_mistral_client", None)
    monkeypatch.setattr(core, "_openai_client", None)
    monkeypatch.setattr(core, "DEEPSEEK_MODEL", "deepseek-chat")

    out = _run(core.gemini_generate("sys", "prompt"))
    assert out == "deepseek-answer"
    assert calls == ["gemini", "deepseek-chat"]


def test_chain_to_mistral_when_deepseek_unavailable(monkeypatch):
    calls = []

    async def g(s, p, t):
        raise Exception("503 unavailable")

    async def oai(client, model, s, p, t):
        calls.append(model)
        if model == "deepseek-chat":
            raise Exception("429 rate limit")
        if model == "mistral-large-latest":
            return "mistral-answer"
        return "openai-answer"

    monkeypatch.setattr(core, "_gemini_text", g)
    monkeypatch.setattr(core, "_oai_text", oai)
    monkeypatch.setattr(core, "_deepseek_client", object())
    monkeypatch.setattr(core, "_mistral_client", object())
    monkeypatch.setattr(core, "_openai_client", object())
    monkeypatch.setattr(core, "DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setattr(core, "MISTRAL_MODEL", "mistral-large-latest")

    out = _run(core.gemini_generate("sys", "prompt"))
    assert out == "mistral-answer"
    assert calls == ["deepseek-chat", "mistral-large-latest"]


def test_all_fail_raises(monkeypatch):
    async def g(s, p, t):
        raise Exception("429 quota")

    async def oai(client, model, s, p, t):
        raise Exception("503 unavailable")

    monkeypatch.setattr(core, "_gemini_text", g)
    monkeypatch.setattr(core, "_oai_text", oai)
    monkeypatch.setattr(core, "_deepseek_client", object())
    monkeypatch.setattr(core, "_mistral_client", object())
    monkeypatch.setattr(core, "_openai_client", object())

    with pytest.raises(RuntimeError):
        _run(core.gemini_generate("sys", "prompt"))


def test_non_transient_error_stops_immediately(monkeypatch):
    calls = []

    async def g(s, p, t):
        calls.append("gemini")
        raise Exception("400 invalid request: bad prompt")

    async def oai(client, model, s, p, t):
        calls.append(model)
        return "should-not-run"

    monkeypatch.setattr(core, "_gemini_text", g)
    monkeypatch.setattr(core, "_oai_text", oai)
    monkeypatch.setattr(core, "_deepseek_client", object())
    monkeypatch.setattr(core, "_mistral_client", None)
    monkeypatch.setattr(core, "_openai_client", None)

    with pytest.raises(Exception):
        _run(core.gemini_generate("sys", "prompt"))
    assert calls == ["gemini"]
