"""Клиент нейросети. Бесплатный путь: Google Gemini (ключ без карты) и/или Groq / OpenRouter.

Если ни одна нейросеть не ответила, API собирает скрипт из шаблона — пользователь всегда получает текст."""

from __future__ import annotations

import asyncio
import re

import aiohttp

from .generator import SYSTEM


class AIError(Exception):
    pass


MAX_TEXT = 4000  # столько же можно сохранить в «Мои скрипты»
GEMINI_FALLBACKS = ("gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-latest")


async def gemini(
    api_key: str, model: str, prompt: str, *, session: aiohttp.ClientSession | None = None,
    max_tokens: int = 1500,
) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        # Модели 3.x думают перед ответом и тратят на это часть токенов — даём запас.
        "generationConfig": {"maxOutputTokens": max(max_tokens, 8192)},
    }
    owns = session is None
    session = session or aiohttp.ClientSession()
    try:
        async with session.post(
            url, json=body, headers={"x-goog-api-key": api_key},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            data = await response.json(content_type=None)
            if response.status != 200:
                message = ""
                if isinstance(data, dict):
                    message = str((data.get("error") or {}).get("message") or "")
                raise AIError(f"Gemini HTTP {response.status}: {message}"[:300])
    except asyncio.TimeoutError as exc:
        raise AIError("Gemini не ответил вовремя.") from exc
    except aiohttp.ClientError as exc:
        raise AIError("Не удалось связаться с Gemini.") from exc
    except ValueError as exc:
        raise AIError("Gemini вернул некорректный ответ.") from exc
    finally:
        if owns:
            await session.close()
    try:
        candidate = data["candidates"][0]
        parts = candidate["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("Gemini не вернул текст (возможно, сработал фильтр).") from exc
    if candidate.get("finishReason") not in (None, "STOP"):
        raise AIError(f"Gemini оборвал ответ ({candidate.get('finishReason')}).")
    if len(text) < 20:
        raise AIError("Gemini вернул слишком короткий ответ.")
    return text[:MAX_TEXT]


async def openai_compatible(
    api_key: str, base_url: str, model: str, prompt: str, *,
    session: aiohttp.ClientSession | None = None, max_tokens: int = 1500,
) -> str:
    """DeepSeek, Groq, OpenRouter, OpenAI — у всех один формат /chat/completions."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": max_tokens,
    }
    owns = session is None
    session = session or aiohttp.ClientSession()
    try:
        async with session.post(
            f"{base_url}/chat/completions", json=body,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=aiohttp.ClientTimeout(total=40),
        ) as response:
            data = await response.json(content_type=None)
            if response.status != 200:
                message = ""
                if isinstance(data, dict):
                    err = data.get("error")
                    message = str(err.get("message") if isinstance(err, dict) else err or "")
                raise AIError(f"AI HTTP {response.status}: {message}"[:300])
    except asyncio.TimeoutError as exc:
        raise AIError("Нейросеть не ответила вовремя.") from exc
    except aiohttp.ClientError as exc:
        raise AIError("Не удалось связаться с нейросетью.") from exc
    except ValueError as exc:
        raise AIError("Нейросеть вернула некорректный ответ.") from exc
    finally:
        if owns:
            await session.close()
    try:
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("Нейросеть не вернула текст.") from exc
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    if len(text) < 20:
        raise AIError("Нейросеть вернула слишком короткий ответ.")
    return text[:MAX_TEXT]


async def complete(prompt: str, *, max_tokens: int = 1500) -> str:
    """Спрашивает подключённые нейросети по очереди: сначала AI_API_KEY (DeepSeek/Groq/…),
    потом Gemini. Если ни одна не ответила — AIError (вызов соберёт шаблон)."""
    from .config import AI_API_KEY, AI_BASE_URL, AI_MODEL, GEMINI_API_KEY, GEMINI_MODEL

    errors = []
    if AI_API_KEY:
        try:
            return await openai_compatible(AI_API_KEY, AI_BASE_URL, AI_MODEL, prompt, max_tokens=max_tokens)
        except AIError as exc:
            errors.append(str(exc))
    if GEMINI_API_KEY:
        # Если модель сняли с работы или у неё кончилась бесплатная квота, Google отвечает
        # по-разному (400/401/403/404/429/5xx) — пробуем следующую модель.
        for model in dict.fromkeys([GEMINI_MODEL, *GEMINI_FALLBACKS]):
            try:
                return await gemini(GEMINI_API_KEY, model, prompt, max_tokens=max_tokens)
            except AIError as exc:
                errors.append(f"{model}: {exc}")
                if "HTTP" not in str(exc):
                    break  # сеть или таймаут — другие модели тоже не ответят
    raise AIError("; ".join(errors) or "Нейросеть не подключена.")
