import json

import httpx
import pytest
from openai import AsyncOpenAI, RateLimitError
from pydantic import SecretStr

from nila.llm.base import LLMMessage, Prompt
from nila.llm.providers import OpenAIProvider


def response_body(text):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "model": "test-model",
        "status": "completed",
        "output": [{
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }],
    }


async def test_hosted_adapter_sends_budgets_and_parses_structured_plan(config):
    captured = []

    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        if "format" in body.get("text", {}):
            text = json.dumps({
                "title": "A plan",
                "steps": [{"tool": "dry_run", "arguments": {"description": "simulate"}}],
            })
        else:
            text = "A model response"
        return httpx.Response(200, json=response_body(text))

    config.openai_model = "test-model"
    config.openai_api_key = SecretStr("test-key-not-a-real-credential")
    provider = OpenAIProvider(config)
    await provider.client.close()
    provider.client = AsyncOpenAI(
        api_key="test-key-not-a-real-credential",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        prompt = Prompt([LLMMessage(role="user", content="hello")], {}, "hello")
        assert await provider.chat(prompt) == "A model response"
        plan = await provider.plan(prompt)
        assert plan.steps[0].tool == "dry_run"
        assert len(captured) == 2
        for body in captured:
            assert body["store"] is False
            assert body["model"] == "test-model"
            assert body["max_output_tokens"] == config.max_output_tokens
        assert captured[1]["text"]["format"]["type"] == "json_schema"
    finally:
        await provider.close()


async def test_rate_limit_is_not_retried(config):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    config.openai_model = "test-model"
    config.openai_api_key = SecretStr("test-key-not-a-real-credential")
    provider = OpenAIProvider(config)
    await provider.client.close()
    provider.client = AsyncOpenAI(
        api_key="test-key-not-a-real-credential",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(RateLimitError):
            await provider.chat(Prompt([LLMMessage(role="user", content="hello")], {}, "hello"))
        assert len(calls) == 1
    finally:
        await provider.close()
