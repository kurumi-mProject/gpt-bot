import httpx
from config import AITUNNEL_KEY, AITUNNEL_URL

async def chat_completion(model: str, messages: list) -> str:
    headers = {"Authorization": f"Bearer {AITUNNEL_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "max_tokens": 2000}
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(f"{AITUNNEL_URL}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Транскрибация голосового сообщения через Whisper."""
    headers = {"Authorization": f"Bearer {AITUNNEL_KEY}"}
    files = {"file": (filename, audio_bytes, "audio/ogg"), "model": (None, "whisper-1")}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{AITUNNEL_URL}/audio/transcriptions", headers=headers, files=files)
        r.raise_for_status()
        return r.json().get("text", "")
