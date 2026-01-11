import logging
import os
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    inference,
)
from livekit.plugins import noise_cancellation, silero

logger = logging.getLogger("agent")

load_dotenv(".env.local")
load_dotenv(".env")

livekit_url = os.getenv("LIVEKIT_URL")
livekit_api_key = os.getenv("LIVEKIT_API_KEY")
livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
livekit_agent_name = os.getenv("LIVEKIT_AGENT_NAME", "xiaozhi")

system_prompt = os.getenv("SYSTEM_PROMPT", """You are Dana, the friend of the child.
You assist the child with their questions by providing clear, concise, and accurate information.
Your responses should be natural and conversational, suitable for voice output.
Keep responses brief and to the point since this is a voice interface.""")

logger.info(f"LiveKit Agent Worker starting with name: {livekit_agent_name}")


class VoiceAssistant(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)
        logger.info("Voice assistant initialized")

    async def on_enter(self) -> None:
        await self.session.say("Hi! How can I help you today?")


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }
    
    logger.info(f"Joining room: {ctx.room.name}")

    session = AgentSession(
        stt=inference.STT(model="deepgram/nova-3"),
        llm=inference.LLM(model="openai/gpt-4o-mini"),
        tts=inference.TTS(
            model="cartesia/sonic-3",
            voice="f31cc6a7-c1e8-4764-980c-60a361443dd1",
        ),
        vad=silero.VAD.load(
            min_silence_duration=0.5,
            min_speech_duration=0.1,
            padding_duration=0.2,
            activation_threshold=0.35,
        ),
    )

    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=VoiceAssistant(instructions=system_prompt),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()


async def request_fnc(req):
    if req.room.name.startswith("v2v-"):
        await req.accept()
    else:
        await req.reject()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        agent_name=livekit_agent_name,
        request_fnc=request_fnc,
    ))
