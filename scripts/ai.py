"""Adapter AI: OpenRouter free tier (default) -> Gemini -> DeepSeek.

Catatan: pipeline sengaja mengirim TEKS SAJA. Parameter images_b64 diterima
untuk kompatibilitas, tetapi tidak pernah dipakai.
"""
import json
import os

import requests

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL", "inclusionai/ling-3.2-flash:free"
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")

KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}
FALLBACK_ORDER = ["openrouter", "gemini", "deepseek"]


def _parse_json(text: str) -> dict:
    """Parse JSON, dengan toleransi terhadap markdown code block."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```" in text:
        block = text.split("```", 2)
        if len(block) >= 3:
            candidate = block[1]
            if candidate.lstrip().startswith("json"):
                candidate = candidate.lstrip()[4:]
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("Respons AI bukan JSON valid")


def _openrouter(prompt: str, images_b64: list[str]) -> dict:
    api_key = os.environ["OPENROUTER_API_KEY"]
    body = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Kamu editor video Shorts Bahasa Indonesia. Balas HANYA JSON valid, tanpa markdown.",
            },
            {"role": "user", "content": [{"type": "text", "text": prompt}]},
        ],
        "temperature": 0.85,
        "max_tokens": 1500,
    }
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        json=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": os.getenv(
                "OPENROUTER_SITE_URL",
                "https://github.com/dailyboostwithwicaksono-rgb/shorts-bot",
            ),
            "X-Title": "shorts-bot",
        },
        timeout=120,
    )
    r.raise_for_status()
    return _parse_json(r.json()["choices"][0]["message"]["content"])


def _gemini(prompt: str, images_b64: list[str]) -> dict:
    api_key = os.environ["GEMINI_API_KEY"]
    parts = [{"text": prompt}]

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
    return _parse_json(text)


def _deepseek(prompt: str, images_b64: list[str]) -> dict:
    api_key = os.environ["DEEPSEEK_API_KEY"]
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Kamu editor video Shorts Bahasa Indonesia. Balas HANYA JSON valid.",
            },
            {"role": "user", "content": [{"type": "text", "text": prompt}]},
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
    return _parse_json(r.json()["choices"][0]["message"]["content"])


CALLERS = {
    "openrouter": _openrouter,
    "gemini": _gemini,
    "deepseek": _deepseek,
}


def generate_plan(prompt: str, images_b64: list[str]) -> dict:
    """Coba provider utama, retry sekali, lalu fallback ke provider lain."""
    provider = os.getenv("AI_PROVIDER", "openrouter").strip().lower()
    if provider not in CALLERS:
        provider = "openrouter"

    order = [provider]
    for name in FALLBACK_ORDER:
        if name != provider and os.getenv(KEY_ENV[name]):
            order.append(name)

    usable = [name for name in order if os.getenv(KEY_ENV[name])]
    if not usable:
        raise RuntimeError(
            "Tidak ada API key AI. Isi salah satu Repository Secret: "
            + ", ".join(KEY_ENV.values())
        )

    last_error = None
    for name in usable:
        for attempt in range(2):
            try:
                extra = (
                    "\nPENTING: kembalikan JSON yang valid, tanpa markdown."
                    if attempt
                    else ""
                )
                return CALLERS[name](prompt + extra, images_b64)
            except Exception as exc:  # noqa: BLE001 - sengaja fallback
                last_error = exc

    raise RuntimeError(f"Semua provider AI gagal: {last_error}")
