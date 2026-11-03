import asyncio
import base64
import json
import time
from collections import deque
from uuid import uuid4

from websockets.asyncio.client import connect


class LiveProtocolError(RuntimeError):
    pass


class LiveSession:
    """GPT-Live client delegation, not the Realtime tool-call protocol.

    Audio and delegation run independently. Transcripts live only in a bounded
    in-memory window. The provider event contains metadata, never task text.
    """

    def __init__(self, settings, instructions, *, codec="pcm", connector=connect, observer=None):
        self.settings, self.instructions, self.codec = settings, instructions, codec
        self.connector = connector
        self.started = asyncio.Event()
        self.closed = asyncio.Event()
        self.socket = None
        self.send_lock = asyncio.Lock()
        self.transcripts = deque(maxlen=40)
        self.revision = 0
        self.delegations = set()
        self.backend_tasks: set[asyncio.Task] = set()
        self.usage = None
        self.session_id = None
        self.reported_model = None
        self.backend_error = None
        self.playback_epoch = 0
        self.observer = observer
        self.turn_metadata = None
        self.input_audio_observed = False
        self.output_audio_observed = False

    def observe(self, kind, phase="observed", **values):
        if self.observer:
            self.observer(kind, phase, external_session_id=self.session_id, **values)

    def flush_turn(self):
        if self.turn_metadata:
            self.observe("voice.turn", "updated", data=self.turn_metadata)
            self.turn_metadata = None

    def observe_transcript(self, kind, event):
        role = "restaurant" if kind.startswith("session.input_") else "assistant"
        fresh = not self.turn_metadata or self.turn_metadata["role"] != role
        if fresh:
            self.flush_turn()
            self.turn_metadata = {
                "turn_id": str(uuid4()),
                "role": role,
                "provisional": True,
                "characters": 0,
                "provider_event_type": kind,
            }
        self.turn_metadata["characters"] += len(event["delta"])
        for source, target in [("start_ms", "provider_start_ms"), ("end_ms", "provider_end_ms")]:
            if event.get(source) is not None:
                self.turn_metadata[target] = event[source]
        if fresh:
            self.observe("voice.turn", "observed", data=self.turn_metadata)

    def session_config(self, greeting):
        return {
            "model": self.settings.voice_model,
            "instructions": self.instructions,
            "store": False,
            "delegation": {"type": "client"},
            "audio": {
                "format": {"type": "audio/pcmu", "rate": 8000}
                if self.codec == "pcmu"
                else {"type": "audio/pcm", "rate": 24000},
                "output": {"voice": self.settings.voice_name},
            },
            "input": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": greeting}],
                }
            ],
        }

    async def send(self, event):
        async with self.send_lock:
            await self.socket.send(json.dumps(event))
        if event["type"] != "session.input_audio.append":
            self.observe(
                "voice.command",
                data={"provider_event_type": event["type"]},
                delegation_id=event.get("delegation_id"),
            )

    async def append(self, content, delegation_id=None, *, kind="commentary"):
        # Stay well under the documented 500-token append ceiling.
        await self.send(
            {
                "type": f"session.{kind}.append",
                "event_id": str(uuid4()),
                "delegation_id": delegation_id,
                "content": content[:700],
            }
        )

    async def request_close(self):
        if self.started.is_set() and not self.closed.is_set():
            await self.send({"type": "session.close", "event_id": str(uuid4())})

    async def run(
        self, input_audio, output_audio, delegate, *, greeting, on_started=None, on_clear=None, control=None
    ):
        if not self.settings.openai_api_key:
            raise LiveProtocolError("OpenAI credentials are not configured")
        # Exact Live endpoint: no Realtime model query, beta header or response.cancel events.
        async with self.connector(
            "wss://api.openai.com/v1/live/sessions",
            additional_headers={"Authorization": "Bearer " + self.settings.openai_api_key.get_secret_value()},
            max_queue=16,
            max_size=2**20,
            open_timeout=10,
            close_timeout=3,
        ) as socket:
            self.socket = socket
            audio_queue = asyncio.Queue(maxsize=10)
            tasks = []

            async def audio_sender():
                await self.started.wait()
                async for raw in input_audio:
                    if self.closed.is_set():
                        return
                    if (
                        not isinstance(raw, bytes)
                        or not raw
                        or len(raw) > 9600
                        or (self.codec == "pcm" and len(raw) % 2)
                    ):
                        raise LiveProtocolError("Invalid audio frame")
                    await self.send(
                        {"type": "session.input_audio.append", "audio": base64.b64encode(raw).decode()}
                    )
                    if not self.input_audio_observed:
                        self.observe(
                            "voice.audio",
                            "first_input",
                            data={"provider_event_type": "session.input_audio.append"},
                        )
                        self.input_audio_observed = True

            async def audio_player():
                size = 160 if self.codec == "pcmu" else 960  # 20 ms mono frames
                while True:
                    raw = await audio_queue.get()
                    epoch = self.playback_epoch
                    for offset in range(0, len(raw), size):
                        if epoch != self.playback_epoch:
                            break
                        await output_audio(raw[offset : offset + size])
                        await asyncio.sleep(0.02)

            async def backend_work(delegation_id, revision, text):
                result = await delegate(text, delegation_id, revision)
                if revision != self.revision:
                    await self.append(
                        "La persona ha corregido información. Confirma los datos actuales antes de aceptar.",
                        delegation_id,
                        kind="thinking",
                    )
                    return
                await self.append(result, delegation_id)

            async def receive():
                async for raw in socket:
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind == "session.started":
                        if self.started.is_set():
                            raise LiveProtocolError("Duplicate session startup")
                        self.session_id = event["session"]["id"]
                        self.reported_model = event["session"].get("model")
                        self.started.set()
                        self.observe(
                            "voice.provider",
                            reported_model=self.reported_model,
                            data={"provider_event_type": kind},
                        )
                        if on_started:
                            await on_started(self.session_id)
                        await self.append(greeting)
                    elif kind == "session.output_audio.delta":
                        if not self.started.is_set():
                            raise LiveProtocolError("Audio before session startup")
                        try:
                            data = base64.b64decode(event["delta"], validate=True)
                        except ValueError:
                            raise LiveProtocolError("Invalid provider audio") from None
                        if self.codec == "pcm" and len(data) % 2:
                            raise LiveProtocolError("Incomplete provider PCM sample")
                        if not self.output_audio_observed:
                            self.observe("voice.audio", "first_output", data={"provider_event_type": kind})
                            self.output_audio_observed = True
                        await audio_queue.put(data)
                    elif kind in {"session.input_transcript.delta", "session.output_transcript.delta"}:
                        if not isinstance(event.get("delta"), str):
                            raise LiveProtocolError("Invalid transcript delta")
                        text = event["delta"][:1000]
                        self.observe_transcript(kind, event)
                        role = "restaurant" if kind.startswith("session.input_") else "assistant"
                        if self.transcripts and self.transcripts[-1]["role"] == role:
                            self.transcripts[-1]["text"] = (self.transcripts[-1]["text"] + text)[-6000:]
                            self.transcripts[-1]["end_ms"] = event.get("end_ms")
                        else:
                            self.transcripts.append(
                                {
                                    "role": role,
                                    "text": text,
                                    "provisional": True,
                                    "start_ms": event.get("start_ms"),
                                    "end_ms": event.get("end_ms"),
                                }
                            )
                        if kind == "session.input_transcript.delta":
                            self.revision += 1
                            if len(text.strip()) > 12 and on_clear:
                                self.playback_epoch += 1
                                # Local playback interruption only; GPT-Live handles conversational turn-taking.
                                while not audio_queue.empty():
                                    audio_queue.get_nowait()
                                await on_clear()
                    elif kind == "session.delegation.created":
                        delegation = event.get("delegation", {})
                        identity = delegation.get("id")
                        if delegation.get("target") != "client" or not isinstance(identity, str):
                            raise LiveProtocolError("Unexpected delegation target")
                        if identity in self.delegations:
                            continue
                        self.delegations.add(identity)
                        self.observe(
                            "voice.delegation",
                            "received",
                            delegation_id=identity,
                            data={"provider_event_type": kind, "revision": self.revision},
                        )
                        if len(self.delegations) > self.settings.voice_max_delegations:
                            raise LiveProtocolError("Delegation limit exceeded")
                        text = "\n".join(f"{t['role']}: {t['text']}" for t in self.transcripts)[-6000:]
                        task = asyncio.create_task(backend_work(identity, self.revision, text))
                        self.backend_tasks.add(task)

                        def completed(done):
                            self.backend_tasks.discard(done)
                            if not done.cancelled() and done.exception() is not None:
                                self.backend_error = LiveProtocolError("Delegated backend task failed")

                        task.add_done_callback(completed)
                    elif kind == "session.closed":
                        self.usage = event.get("usage")
                        self.flush_turn()
                        self.observe("voice.provider", data={"provider_event_type": kind})
                        self.closed.set()
                        return
                    elif kind == "error":
                        self.observe("voice.provider", "failed", data={"provider_event_type": kind})
                        raise LiveProtocolError("GPT-Live rejected a session command")
                raise LiveProtocolError("Live connection ended without session.closed")

            async def controller():
                await asyncio.wait_for(self.started.wait(), timeout=10)
                started = time.monotonic()
                while not self.closed.is_set():
                    if self.backend_error:
                        raise self.backend_error
                    if time.monotonic() - started >= self.settings.voice_max_seconds:
                        await self.request_close()
                        await asyncio.wait_for(self.closed.wait(), timeout=5)
                        return
                    if control and await control(self):
                        await self.request_close()
                        await asyncio.wait_for(self.closed.wait(), timeout=5)
                        return
                    await asyncio.sleep(0.05)

            try:
                await self.send(
                    {
                        "type": "session.start",
                        "event_id": str(uuid4()),
                        "session": self.session_config(greeting),
                    }
                )
                tasks = [asyncio.create_task(f()) for f in (receive, audio_sender, audio_player, controller)]
                # A normal audio source ending is a request to finalize, never an automatic reconnect.
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                if not self.closed.is_set():
                    await self.request_close()
                    await asyncio.wait_for(self.closed.wait(), timeout=5)
            finally:
                for task in [*tasks, *self.backend_tasks]:
                    task.cancel()
                await asyncio.gather(*tasks, *self.backend_tasks, return_exceptions=True)
                self.transcripts.clear()
                self.flush_turn()
                self.socket = None
        return self.usage
