import json
import httpx
from typing import AsyncGenerator, Optional


class AIClient:
    def __init__(self, config: dict):
        self.config = config["ai"]

    async def generate(self, system_prompt: str, user_message: str, timeout: float = 1800.0) -> str:
        provider = self.config.get("provider", "ollama")
        if provider == "ollama":
            return await self._ollama(system_prompt, user_message, timeout)
        elif provider == "anthropic":
            return await self._anthropic(system_prompt, user_message)
        elif provider == "openai":
            return await self._openai(system_prompt, user_message)
        else:
            raise ValueError(f"Unknown AI provider: {provider}")

    async def _ollama(self, system_prompt: str, user_message: str, timeout: float = 600.0) -> str:
        base_url = self.config.get("ollama_url", "http://localhost:11434").rstrip("/")
        model = self.config.get("model", "qwen2.5:7b")
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()

    async def stream(self, system_prompt: str, user_message: str, timeout: float = 1800.0) -> AsyncGenerator[str, None]:
        provider = self.config.get("provider", "ollama")
        if provider == "ollama":
            async for chunk in self._ollama_stream(system_prompt, user_message, timeout):
                yield chunk
        else:
            # Cloud providers: no streaming support yet, yield full response at once
            result = await self.generate(system_prompt, user_message, timeout)
            yield result

    async def _ollama_stream(self, system_prompt: str, user_message: str, timeout: float) -> AsyncGenerator[str, None]:
        base_url = self.config.get("ollama_url", "http://localhost:11434").rstrip("/")
        model = self.config.get("model", "qwen2.5:7b")
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break

    async def _anthropic(self, system_prompt: str, user_message: str) -> str:
        api_key = self.config.get("cloud_api_key", "")
        model = self.config.get("cloud_model", "claude-sonnet-4-6")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_message}],
                },
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"].strip()

    async def _openai(self, system_prompt: str, user_message: str) -> str:
        api_key = self.config.get("cloud_api_key", "")
        model = self.config.get("cloud_model", "gpt-4o")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    async def test_connection(self) -> dict:
        provider = self.config.get("provider", "ollama")
        try:
            if provider == "ollama":
                base_url = self.config.get("ollama_url", "http://localhost:11434").rstrip("/")
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(f"{base_url}/api/tags")
                    resp.raise_for_status()
                    models = [m["name"] for m in resp.json().get("models", [])]
                    return {"ok": True, "models": models}
            else:
                result = await self.generate("Reply with just 'ok'.", "Say ok.")
                return {"ok": True, "response": result[:50]}
        except Exception as e:
            return {"ok": False, "error": str(e)}
