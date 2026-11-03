"""Microphone/speaker diagnostic. No frontend and no telephone calls.

python scripts/voice_sandbox.py --booking-id ID --allow-api-costs --consent-audio-processing
"""

import argparse
import asyncio
import json
import signal
import sys
import threading
from collections import deque

from websockets.asyncio.client import connect

from app.core.config import get_settings


async def run(args):
    import sounddevice as sd

    settings = get_settings()
    if not args.allow_api_costs or not args.consent_audio_processing:
        raise SystemExit("Both --allow-api-costs and --consent-audio-processing are required")
    frames = asyncio.Queue(maxsize=25)
    speakers = deque()
    playback = bytearray()
    lock = threading.Lock()
    stop = asyncio.Event()
    ready = asyncio.Event()
    loop = asyncio.get_running_loop()

    def enqueue(raw):
        if frames.full():
            stop.set()
        else:
            frames.put_nowait(raw)

    def capture(indata, frame_count, time_info, status):
        if status:
            loop.call_soon_threadsafe(stop.set)
            return
        loop.call_soon_threadsafe(enqueue, bytes(indata))

    def play(outdata, frame_count, time_info, status):
        needed = len(outdata)
        with lock:
            while speakers and len(playback) < needed:
                playback.extend(speakers.popleft())
            chunk = bytes(playback[:needed])
            del playback[:needed]
        outdata[:] = chunk + bytes(needed - len(chunk))

    def request_stop(*_):
        loop.call_soon_threadsafe(stop.set)

    previous = signal.signal(signal.SIGINT, request_stop)
    uri = f"ws://{settings.host}:{settings.port}/api/voice/sandbox/ws?booking_id={args.booking_id}"
    try:
        async with connect(uri, max_size=2**20) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "token": settings.local_api_token.get_secret_value(),
                        "allow_api_costs": True,
                        "audio_processing_consent": True,
                    }
                )
            )

            async def receive():
                async for data in websocket:
                    if isinstance(data, bytes):
                        with lock:
                            if sum(len(p) for p in speakers) > 48000:
                                stop.set()  # bounded latency: stop rather than silently drop old audio
                            speakers.append(data)
                        continue
                    event = json.loads(data)
                    if event["type"] == "session.ready":
                        ready.set()
                        print("Voz conectada. Usa auriculares; Ctrl+C para finalizar.", file=sys.stderr)
                    elif event["type"] == "audio.clear":
                        with lock:
                            speakers.clear()
                            playback.clear()
                    elif event["type"] in {"error", "session.closed"}:
                        print(json.dumps(event), file=sys.stderr)
                        stop.set()
                        return

            async def send():
                while not stop.is_set():
                    try:
                        await websocket.send(await asyncio.wait_for(frames.get(), timeout=0.1))
                    except TimeoutError:
                        continue

            receiver = asyncio.create_task(receive())
            await asyncio.wait_for(ready.wait(), timeout=15)
            sender = asyncio.create_task(send())
            try:
                with (
                    sd.RawInputStream(
                        samplerate=24000, channels=1, dtype="int16", blocksize=480, callback=capture
                    ),
                    sd.RawOutputStream(
                        samplerate=24000, channels=1, dtype="int16", blocksize=480, callback=play
                    ),
                ):
                    await stop.wait()
                await websocket.send(json.dumps({"type": "close"}))
                await asyncio.wait_for(receiver, timeout=7)
            finally:
                sender.cancel()
                receiver.cancel()
                await asyncio.gather(sender, receiver, return_exceptions=True)
    finally:
        signal.signal(signal.SIGINT, previous)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prueba de audio real con GPT-Live; puede generar costes de API"
    )
    parser.add_argument("--booking-id", required=True)
    parser.add_argument("--allow-api-costs", action="store_true")
    parser.add_argument("--consent-audio-processing", action="store_true")
    asyncio.run(run(parser.parse_args()))
