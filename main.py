import json
import base64
import asyncio
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

import app as backend

fastapi_app   = FastAPI(title="Gyan Yantra Voice")
TEMPLATES_DIR = Path(__file__).parent / "templates"

active: Dict[str, asyncio.Event] = {}


@fastapi_app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse((TEMPLATES_DIR / "index.html").read_text(encoding="utf-8"))


@fastapi_app.get("/health")
async def health():
    ok, err = backend.check_ollama()
    return {"status": "ok"} if ok else {"status": "error", "message": err}


@fastapi_app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    interrupt = asyncio.Event()
    active[id(websocket)] = interrupt
    pipeline_task = None

    async def send(data: dict):
        try:
            await websocket.send_text(json.dumps(data))
        except Exception:
            pass

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            t = msg.get("type")

            if t == "interrupt":
                interrupt.set()
                if pipeline_task and not pipeline_task.done():
                    pipeline_task.cancel()
                    try:
                        await pipeline_task
                    except Exception:
                        pass
                interrupt = asyncio.Event()
                active[id(websocket)] = interrupt
                pipeline_task = None
                await send({"type": "interrupted"})

            elif t == "audio":
                # Cancel any current pipeline
                interrupt.set()
                if pipeline_task and not pipeline_task.done():
                    pipeline_task.cancel()
                    try:
                        await pipeline_task
                    except Exception:
                        pass
                interrupt = asyncio.Event()
                active[id(websocket)] = interrupt

                try:
                    audio_bytes = base64.b64decode(msg.get("data", ""))
                except Exception:
                    await send({"type": "error", "message": "Bad audio data."})
                    continue

                await send({"type": "transcribing"})
                mime = msg.get("mime", "audio/webm")

                try:
                    transcript = await asyncio.get_event_loop().run_in_executor(
                        None, backend.transcribe_audio, audio_bytes, mime
                    )
                except Exception as e:
                    await send({"type": "error", "message": f"STT failed: {e}"})
                    continue

                if not transcript.strip():
                    await send({"type": "error", "message": "Could not understand. Try again."})
                    continue

                await send({"type": "transcription", "text": transcript})

                cur_interrupt = interrupt

                async def run(prompt, ev):
                    async for evt in backend.run_voice_pipeline(prompt, ev):
                        await send(evt)

                pipeline_task = asyncio.create_task(run(transcript, cur_interrupt))

            elif t == "ping":
                await send({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        interrupt.set()
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        active.pop(id(websocket), None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:fastapi_app", host="127.0.0.1", port=8000, reload=False)
