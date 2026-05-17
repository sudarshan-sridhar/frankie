"""Async client for IBM watsonx.ai Granite models. Pure httpx + stdlib.

Primary reasoning backend for Frankie. Pairs with reasoning.router for
transparent fallback to Claude when watsonx is unavailable or empty.
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, TYPE_CHECKING

import cv2
import httpx

if TYPE_CHECKING:
    from numpy.typing import NDArray


class GraniteError(RuntimeError):
    """Raised on any non-recoverable watsonx.ai API failure."""


# IAM token is valid 3600s. Refresh when fewer than this many seconds remain.
_TOKEN_REFRESH_MARGIN_S = 300

_IAM_URL = "https://iam.cloud.ibm.com/identity/token"
_WX_BASE = "https://us-south.ml.cloud.ibm.com"
_WX_CHAT_PATH = "/ml/v1/text/chat"
# Chat API version. 2024-10-08 is the documented stable version for chat.
_WX_VERSION = "2024-10-08"

# Retry on these HTTP statuses with exponential backoff.
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BASE_BACKOFF_S = 0.5


class GraniteClient:
    """Async watsonx.ai chat client for Granite text + vision models."""

    def __init__(
        self,
        api_key: str,
        project_id: str,
        model_id: str = "ibm/granite-3-8b-instruct",
        vision_model_id: str = "ibm/granite-vision-3-2-2b",
        *,
        timeout_s: float = 60.0,
    ) -> None:
        if not api_key or not project_id:
            raise GraniteError("api_key and project_id are required")
        self._api_key = api_key
        self._project_id = project_id
        self._model_id = model_id
        self._vision_model_id = vision_model_id

        self._client = httpx.AsyncClient(timeout=timeout_s)
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def vision_model_id(self) -> str:
        return self._vision_model_id

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        """Send a chat request and return the assistant text."""
        body: dict[str, Any] = {
            "model_id": self._model_id,
            "project_id": self._project_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        data = await self._post_chat(body)
        return self._extract_text(data)

    async def describe_image(self, image_bgr: NDArray, prompt: str) -> str:
        """Vision call via Granite Vision. Encodes BGR ndarray to JPEG base64."""
        loop = asyncio.get_running_loop()
        b64 = await loop.run_in_executor(None, _encode_jpeg_b64, image_bgr)

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ]
        body: dict[str, Any] = {
            "model_id": self._vision_model_id,
            "project_id": self._project_id,
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0.2,
        }
        data = await self._post_chat(body)
        return self._extract_text(data)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{_WX_BASE}{_WX_CHAT_PATH}"
        params = {"version": _WX_VERSION}

        last_err: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            token = await self._get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            try:
                resp = await self._client.post(
                    url, params=params, headers=headers, json=body
                )
            except httpx.HTTPError as e:
                last_err = e
                await self._sleep_backoff(attempt)
                continue

            if resp.status_code == 401:
                # Force token refresh and retry.
                self._token = None
                self._token_expires_at = 0.0
                last_err = GraniteError(f"401 from watsonx: {resp.text[:300]}")
                await self._sleep_backoff(attempt)
                continue

            if resp.status_code in _RETRY_STATUSES:
                last_err = GraniteError(
                    f"{resp.status_code} from watsonx: {resp.text[:300]}"
                )
                await self._sleep_backoff(attempt, resp)
                continue

            if resp.status_code >= 400:
                raise GraniteError(
                    f"watsonx chat failed {resp.status_code}: {resp.text[:500]}"
                )

            try:
                return resp.json()
            except ValueError as e:
                raise GraniteError(f"watsonx returned non-JSON: {e}") from e

        raise GraniteError(
            f"watsonx chat failed after {_MAX_ATTEMPTS} attempts: {last_err}"
        )

    async def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - _TOKEN_REFRESH_MARGIN_S:
            return self._token

        async with self._token_lock:
            now = time.time()
            if self._token and now < self._token_expires_at - _TOKEN_REFRESH_MARGIN_S:
                return self._token
            await self._refresh_token()
            assert self._token is not None
            return self._token

    async def _refresh_token(self) -> None:
        data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": self._api_key,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        last_err: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                resp = await self._client.post(_IAM_URL, data=data, headers=headers)
            except httpx.HTTPError as e:
                last_err = e
                await self._sleep_backoff(attempt)
                continue

            if resp.status_code in _RETRY_STATUSES:
                last_err = GraniteError(f"IAM {resp.status_code}: {resp.text[:300]}")
                await self._sleep_backoff(attempt, resp)
                continue

            if resp.status_code >= 400:
                raise GraniteError(
                    f"IAM token request failed {resp.status_code}: {resp.text[:500]}"
                )

            payload = resp.json()
            token = payload.get("access_token")
            expires_in = int(payload.get("expires_in", 3600))
            if not token:
                raise GraniteError(f"IAM response missing access_token: {payload}")
            self._token = token
            self._token_expires_at = time.time() + expires_in
            return

        raise GraniteError(f"IAM refresh failed after {_MAX_ATTEMPTS}: {last_err}")

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        try:
            choices = data["choices"]
            msg = choices[0]["message"]
            content = msg["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise GraniteError(f"unexpected chat response shape: {data}") from e

        if isinstance(content, str):
            return _clean_chat_text(content)
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
            return _clean_chat_text("".join(parts))
        raise GraniteError(f"unexpected content type: {type(content)!r}")

    @staticmethod
    async def _sleep_backoff(attempt: int, resp: httpx.Response | None = None) -> None:
        delay: float
        if resp is not None:
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    delay = float(ra)
                except ValueError:
                    delay = _BASE_BACKOFF_S * (2 ** (attempt - 1))
            else:
                delay = _BASE_BACKOFF_S * (2 ** (attempt - 1))
        else:
            delay = _BASE_BACKOFF_S * (2 ** (attempt - 1))
        await asyncio.sleep(delay)


# Granite chat models occasionally bleed into a fake multi-turn dialog where
# the assistant continues with its own "user\n..." messages. Truncate at the
# first chat-role marker so callers only see the intended assistant reply.
_CHAT_BOUNDARY_MARKERS = (
    "\nuser\n",
    "\n\nuser\n",
    "\nassistant\n",
    "\n\nassistant\n",
    "<|user|>",
    "<|assistant|>",
    "<|end_of_text|>",
)


def _clean_chat_text(text: str) -> str:
    """Strip trailing fake-turn continuations Granite sometimes emits."""
    cleaned = text
    for marker in _CHAT_BOUNDARY_MARKERS:
        idx = cleaned.find(marker)
        if idx != -1:
            cleaned = cleaned[:idx]
    return cleaned.rstrip()


def _encode_jpeg_b64(image_bgr: NDArray) -> str:
    ok, buf = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise GraniteError("cv2.imencode failed to encode image as JPEG")
    return base64.b64encode(buf.tobytes()).decode("ascii")
