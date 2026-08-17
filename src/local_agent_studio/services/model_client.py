from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from ..entities import ModelProfile
from ..security import SecretBox


class UpstreamModelError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Model base URL must be an http(s) URL without embedded credentials")
    return base_url.strip().rstrip("/")


class ModelClient:
    def __init__(self, secret_box: SecretBox):
        self.secret_box = secret_box

    def _headers(self, profile: ModelProfile) -> dict[str, str]:
        key = self.secret_box.unprotect(profile.api_key_secret)
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    async def complete(self, profile: ModelProfile, messages: list[dict[str, str]]) -> str:
        url = validate_base_url(profile.base_url) + "/chat/completions"
        payload = {
            "model": profile.model_name,
            "messages": messages,
            "temperature": profile.temperature,
            "max_tokens": profile.max_tokens,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(
                timeout=profile.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.post(url, headers=self._headers(profile), json=payload)
            response.raise_for_status()
            data = response.json()
            content: Any = data.get("choices", [{}])[0].get("message", {}).get("content")
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            if not isinstance(content, str) or not content.strip():
                raise UpstreamModelError("empty_response")
            return content.strip()
        except httpx.TimeoutException as exc:
            raise UpstreamModelError("upstream_timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise UpstreamModelError(f"upstream_http_{exc.response.status_code}") from exc
        except (httpx.HTTPError, ImportError, ValueError, KeyError, TypeError) as exc:
            raise UpstreamModelError("upstream_invalid_response") from exc

    async def embed(self, profile: ModelProfile, inputs: list[str]) -> list[list[float]]:
        url = validate_base_url(profile.base_url) + "/embeddings"
        payload = {"model": profile.model_name, "input": inputs}
        try:
            async with httpx.AsyncClient(
                timeout=profile.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.post(url, headers=self._headers(profile), json=payload)
            response.raise_for_status()
            rows = sorted(response.json().get("data", []), key=lambda item: item.get("index", 0))
            vectors = [row.get("embedding") for row in rows]
            if len(vectors) != len(inputs) or not all(
                isinstance(vector, list) and vector for vector in vectors
            ):
                raise UpstreamModelError("invalid_embedding_response")
            return [[float(value) for value in vector] for vector in vectors]
        except httpx.TimeoutException as exc:
            raise UpstreamModelError("embedding_timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise UpstreamModelError(f"embedding_http_{exc.response.status_code}") from exc
        except (httpx.HTTPError, ImportError, ValueError, TypeError) as exc:
            raise UpstreamModelError("invalid_embedding_response") from exc

    async def test(self, profile: ModelProfile) -> str:
        if profile.capability == "embedding":
            vectors = await self.embed(profile, ["连接测试"])
            return f"Embedding OK · {len(vectors[0])} dimensions"
        reply = await self.complete(
            profile,
            [
                {"role": "system", "content": "Return exactly OK."},
                {"role": "user", "content": "connection test"},
            ],
        )
        return f"Chat OK · {reply[:60]}"
