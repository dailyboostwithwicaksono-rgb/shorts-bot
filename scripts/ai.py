"""Adapter AI: Gemini Flash-Lite (default) dengan fallback otomatis ke DeepSeek Flash."""
import json
import os

import requests

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")


def _gemini(prompt: str, images_b64: list[str]) -> dict:
    api_key = os.environ["GEMINI_API_KEY"]
    parts = [{"text": prompt}]
    for b64 in images_b64:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.85,
            "maxOutputTokens": 1500,
        },
    }
    r = requests.post(url, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()
    candidate = data["candidates"][0]
    text = "".join(p.get("text", "") for p in candidate["content"]["parts"])
    return json.loads(text)


def _deepseek(prompt: str, images_b64: list[str]) -> dict:
    api_key = os.environ["DEEPSEEK_API_KEY"]
    content = [{"type": "text", "text": prompt}]
    for b64 in images_b64:
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        )

    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Kamu editor video Shorts Bahasa Indonesia. Balas HANYA JSON valid.",
            },
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.85,
        "max_tokens": 1500,
    }
    r = requests.post(
        "https://api.deepseek.com/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def generate_plan(prompt: str, images_b64: list[str]) -> dict:
    """Coba provider utama, retry sekali, lalu fallback ke provider lain bila tersedia."""
    provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    if provider not in {"gemini", "deepseek"}:
        provider = "gemini"

    last_error = None
    order = [provider]
    if provider == "gemini" and os.getenv("DEEPSEEK_API_KEY"):
        order.append("deepseek")
    elif provider == "deepseek" and os.getenv("GEMINI_API_KEY"):
        order.append("gemini")

    for name in order:
        for attempt in range(2):
            try:
                extra = "\nPENTING: kembalikan JSON yang valid, tanpa markdown." if attempt else ""
                return (
                    _deepseek(prompt + extra, images_b64)
                    if name == "deepseek"
                    else _gemini(prompt + extra, images_b64)
                )
            except Exception as exc:  # noqa: BLE001 - sengaja fallback
                last_error = exc
    raise RuntimeError(f"Semua provider AI gagal: {last_error}")
