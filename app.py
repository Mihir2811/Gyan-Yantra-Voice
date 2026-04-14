import os
import json
import base64
import asyncio
import tempfile
import threading
import time
from typing import Optional, Dict, AsyncGenerator

import httpx

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

try:
    from TTS.api import TTS as CoquiTTS
    COQUI_AVAILABLE = True
except ImportError:
    COQUI_AVAILABLE = False


# ── Constants ─────────────────────────────────────────────────────────────────

OLLAMA_HOST   = "http://127.0.0.1:11434"
CHAT_ENDPOINT = f"{OLLAMA_HOST}/api/chat"

MODEL = "llama3.2:1b"

# Strict token limit — keeps responses short and fast on CPU
MAX_TOKENS = 80

TTS_MODEL_NAME = "tts_models/en/vctk/vits"
TTS_SPEAKER    = "p273"

SYSTEM_PROMPT = (
    "You are Gyan Yantra, a fast voice assistant. "
    "Give SHORT conversational replies — 1 to 3 sentences maximum. "
    "Never use markdown, bullet points, lists, asterisks, or symbols. "
    "Speak naturally and directly. No filler phrases."
)


# ── Whisper STT ───────────────────────────────────────────────────────────────

_whisper_model = None
_whisper_lock  = threading.Lock()


def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                if not WHISPER_AVAILABLE:
                    raise RuntimeError("faster-whisper not installed.")
                _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


def transcribe_audio(audio_bytes: bytes, mime: str = "audio/webm") -> str:
    model = get_whisper()

    if "ogg" in mime:
        ext = ".ogg"
    elif "mp4" in mime or "m4a" in mime:
        ext = ".mp4"
    else:
        ext = ".webm"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, _ = model.transcribe(
            tmp_path,
            language="en",
            beam_size=3,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300}
        )
        return " ".join(s.text.strip() for s in segments).strip()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── Coqui TTS ─────────────────────────────────────────────────────────────────

_coqui_tts  = None
_coqui_lock = threading.Lock()


def get_coqui():
    global _coqui_tts
    if _coqui_tts is None:
        with _coqui_lock:
            if _coqui_tts is None:
                if not COQUI_AVAILABLE:
                    raise RuntimeError("TTS not installed.")
                _coqui_tts = CoquiTTS(TTS_MODEL_NAME, progress_bar=False)
    return _coqui_tts


def synthesize_speech(text: str) -> tuple[bytes, float]:
    """Returns (wav_bytes, tts_seconds)."""
    text = text.strip()
    if not text:
        return b"", 0.0

    tts = get_coqui()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    t0 = time.time()
    try:
        tts.tts_to_file(text=text, speaker=TTS_SPEAKER, file_path=tmp_path)
        elapsed = time.time() - t0
        with open(tmp_path, "rb") as f:
            return f.read(), round(elapsed, 2)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── Voice Pipeline ────────────────────────────────────────────────────────────

async def run_voice_pipeline(
    prompt: str,
    interrupt_event: asyncio.Event,
) -> AsyncGenerator[Dict, None]:
    """
    LLM stream (strict token cap) → single TTS call.
    Yields WebSocket protocol dicts with timing info.
    """

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    yield {"type": "thinking"}

    # 1. Stream LLM with strict max_tokens
    full_response = ""
    t_llm_start   = time.time()

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                CHAT_ENDPOINT,
                json={
                    "model":   MODEL,
                    "messages": messages,
                    "stream":  True,
                    "options": {
                        "num_predict": MAX_TOKENS,   # hard token cap
                        "temperature": 0.7,
                        "top_p":       0.9,
                        "repeat_penalty": 1.1,
                    }
                }
            ) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    if interrupt_event.is_set():
                        return
                    if not raw_line:
                        continue
                    try:
                        chunk = json.loads(raw_line)
                    except Exception:
                        continue
                    if "error" in chunk:
                        yield {"type": "error", "message": chunk["error"]}
                        return
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        full_response += token
                        yield {"type": "text_chunk", "content": token}
                    if chunk.get("done"):
                        break
    except Exception as e:
        yield {"type": "error", "message": f"LLM failed: {e}"}
        return

    llm_ms = round((time.time() - t_llm_start) * 1000)

    if not full_response.strip() or interrupt_event.is_set():
        yield {"type": "done"}
        return

    # 2. Single TTS call — full response at once
    try:
        wav_bytes, tts_sec = await asyncio.get_event_loop().run_in_executor(
            None, synthesize_speech, full_response.strip()
        )
    except Exception as e:
        yield {"type": "error", "message": f"TTS failed: {e}"}
        yield {"type": "done"}
        return

    if wav_bytes and not interrupt_event.is_set():
        yield {
            "type":    "audio_chunk",
            "data":    base64.b64encode(wav_bytes).decode("utf-8"),
            "text":    full_response.strip(),
            "timing":  {
                "llm_ms":  llm_ms,
                "tts_sec": tts_sec,
                "tokens":  len(full_response.split()),
            }
        }

    yield {"type": "done"}


# ── Health ────────────────────────────────────────────────────────────────────

def check_ollama() -> tuple[bool, Optional[str]]:
    try:
        httpx.get(OLLAMA_HOST, timeout=2)
        return True, None
    except httpx.ConnectError:
        return False, "Ollama is not running."
    except Exception as e:
        return False, str(e)
