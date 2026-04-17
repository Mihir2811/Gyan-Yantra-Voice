# Gyan Yantra
**Voice-Powered Conversational Assistant**

Gyan Yantra is a local-first, real-time voice chat application powered by open-source AI models. It provides low-latency speech-to-text (STT), large language model (LLM) inference, and text-to-speech (TTS) capabilities, all optimized for consumer CPU hardware.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-brightgreen?logo=fastapi)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Ollama-llama3.2%3A1b-blue?logo=ollama)](https://ollama.com)
[![faster-whisper](https://img.shields.io/badge/faster--whisper-base-orange)](https://github.com/SYSTRAN/faster-whisper)
[![Coqui TTS](https://img.shields.io/badge/Coqui%20TTS-vits-red)](https://github.com/coqui-ai/TTS)

## Overview

Gyan Yantra enables natural voice conversations with an AI assistant named \"Gyan Yantra\" (Sanskrit for \"Knowledge Machine\"). Users speak via microphone (hold spacebar or mic button), audio is transcribed, processed by a local LLM for concise responses, and played back via TTS.

Key design principles:
- **Local Execution**: No cloud dependencies; runs entirely on localhost.
- **Performance**: Strict 80-token LLM limit, CPU-optimized models for <1s end-to-end latency.
- **Interruptible**: Supports mid-response interruption for fluid dialogue.
- **Minimalist UI**: Clean, themeable interface with real-time status, waveform visualization, and conversation history.

## Features

- **Voice Pipeline**: WebRTC recording → faster-whisper STT → Ollama/llama3.2:1b LLM → Coqui TTS playback.
- **Streaming Responses**: LLM tokens stream in real-time; single TTS synthesis for full reply.
- **Persona Control**: Configurable system prompt enforces short, natural replies (1-3 sentences, no markdown).
- **UI/UX**:
  - Spacebar or hold-to-talk mic button.
  - Live waveform, status indicators (listening/thinking/speaking), timing badges (LLM ms, TTS s, tokens).
  - Dark/light themes, transcript history with user/assistant bubbles.
- **WebSocket Backend**: Bidirectional real-time communication via FastAPI.
- **Health Checks**: `/health` endpoint verifies Ollama availability.
- **Cross-Platform**: Browser-based frontend; Python backend runs on Windows/Linux/macOS.

## Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌──────────────────┐
│   Browser UI    │◄──►│ FastAPI/WS   │───▶│   app.py Logic   │
│ (index.html/JS) │    │ (main.py)    │    │ (STT/LLM/TTS)    │
└─────────────────┘    └──────────────┘    └──────────────────┘
                                                    │
                                        ┌──────────▼──────────┐
                                        │   Local Services    │
                                ┌───────▼──────────┬─────────▼───────┐
                                │ Ollama (11434)   │ faster-whisper  │
                                │  llama3.2:1b     │     (STT)       │
                                └──────────────────┼─────────────────┘
                                                  │ Coqui TTS
                                                  │  (en/vctk/vits)
```

## Quick Start

### Prerequisites
1. **Ollama**: Install from [ollama.com](https://ollama.com) and run:
   ```
   ollama serve
   ollama pull llama3.2:1b
   ```
   Verify: `curl http://127.0.0.1:11434`

2. **Python 3.10+**

### Installation
```bash
git clone <repo>
cd Chat-Pro
pip install -r requirements_voice.txt
```

### Run
```bash
uvicorn main:fastapi_app --host 127.0.0.1 --port 8000 --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Grant microphone permissions.

## Usage

1. **Start Conversation**: Hold **Spacebar** or the central mic button.
2. **Speak Naturally**: Release to transcribe and send (typically 3-8s audio).
3. **Listen**: AI responds via speakers/headphones.
4. **Interrupt**: Hold space/mic during response to cancel.
5. **History**: Transcript persists; timings shown post-response.

Keyboard shortcuts:
- **Space**: Hold to speak.
- **🌙/☀️**: Toggle theme.

Mobile: Touch-hold mic button.

## Customization

Edit `app.py`:
- **LLM Model**: Change `MODEL = \"qwen2.5:1.5b\"` (pull via Ollama first).
- **Max Tokens**: Adjust `MAX_TOKENS = 120`.
- **Persona**: Modify `SYSTEM_PROMPT`.
- **TTS Voice**: `TTS_SPEAKER = \"p225\"` (see Coqui docs).
- **Whisper**: `WhisperModel(\"tiny\")` for speed.

Reinstall dependencies if changing models.

## Dependencies

See [requirements_voice.txt](requirements_voice.txt):
```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
faster-whisper>=1.0.1
TTS>=0.22.0
...
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| \"Ollama is not running\" | Run `ollama serve`; check `/health`. |
| No audio input | Verify browser mic permissions; test in chrome://settings/content/microphone. |
| TTS/STT errors | `pip install -r requirements_voice.txt --upgrade`; CPU fallback uses int8. |
| High latency | Use smaller LLM (llama3.2:1b); close other apps. |
| WebSocket fails | Check firewall; ensure port 8000 free. |

## Performance Notes

- **CPU Targets**: i5/Ryzen 5+ recommended.
- **Expected Latency**:
  | Component | Time |
  |-----------|------|
  | STT (5s audio) | 300-800ms |
  | LLM (80 tokens) | 400-1200ms |
  | TTS (20 words) | 800-1500ms |
- Metrics logged in UI (e.g., \"42 tokens · LLM 682ms · TTS 1.2s\").

## License

MIT License. See [LICENSE](LICENSE) (add if needed).

## Contributing

1. Fork and PR.
2. Follow PEP 8; add tests.
3. Update docs for new features.

---

Built with ❤️ for accessible AI. Questions? Open an issue.
