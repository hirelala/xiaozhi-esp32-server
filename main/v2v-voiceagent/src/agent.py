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
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")
load_dotenv(".env")

livekit_url = os.getenv("LIVEKIT_URL")
livekit_api_key = os.getenv("LIVEKIT_API_KEY")
livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
livekit_agent_name = os.getenv("LIVEKIT_AGENT_NAME", "xiaozhi-agent")

stt_model = os.getenv("STT_MODEL", "deepgram/nova-3")
llm_model = os.getenv("LLM_MODEL", "openai/gpt-4.1-mini")
tts_model = os.getenv("TTS_MODEL", "cartesia/sonic-2")
tts_voice = os.getenv("TTS_VOICE", "79a125e8-cd45-4c13-8a67-188112f4dd22")
language = os.getenv("LANGUAGE", "en")

system_prompt = os.getenv("SYSTEM_PROMPT", """You are Xiaozhi, a helpful and friendly voice AI assistant.
You assist users with their questions by providing clear, concise, and accurate information.
Your responses should be natural and conversational, suitable for voice output.
Keep responses brief and to the point since this is a voice interface.
Avoid using markdown formatting, bullet points, or special characters that don't work well in speech.""")

logger.info(f"LiveKit Agent Worker starting with name: {livekit_agent_name}")


class VoiceAssistant(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)
        logger.info("Voice assistant initialized")

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Greet the user briefly and offer your assistance."
        )


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }
    
    logger.info(f"Joining room: {ctx.room.name}")

    session = AgentSession(
        stt=stt_model,
        llm=llm_model,
        tts=f"{tts_model}:{tts_voice}",
        turn_detection=MultilingualModel(),
        vad=silero.VAD.load(
            min_silence_duration=1.0,
            min_speech_duration=0.15,
            padding_duration=0.3,
            activation_threshold=0.4,
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


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        agent_name=livekit_agent_name,
        request_fnc=lambda ctx: ctx.room.name.startswith("v2v-"),
    ))
