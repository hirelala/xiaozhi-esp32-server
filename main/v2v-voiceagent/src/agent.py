import logging
import os
import re
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
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")
load_dotenv(".env")

livekit_url = os.getenv("LIVEKIT_URL")
livekit_api_key = os.getenv("LIVEKIT_API_KEY")
livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
livekit_agent_name = os.getenv("LIVEKIT_AGENT_NAME", "xiaozhi")


VOICE_MAP = {
    "zh": os.getenv("TTS_VOICE_ZH", "7a5d4663-88ae-47b7-808e-8f9b9ee4127b"),
    "en": os.getenv("TTS_VOICE_EN", "5ee9feff-1265-424a-9d7f-8e4d431a12c7"),
    "ja": os.getenv("TTS_VOICE_JA", "2b568345-1d48-4047-b25f-7baccf842eb0"),
    "ko": os.getenv("TTS_VOICE_KO", "29e5f8b4-b953-4160-848f-40fae182235b"),
    "es": os.getenv("TTS_VOICE_ES", "846d6cb0-2301-48b6-9571-6d4134a95a7f"),
    "fr": os.getenv("TTS_VOICE_FR", "a8a1eb38-5f15-4c1d-8722-7ac0f329f8d3"),
    "de": os.getenv("TTS_VOICE_DE", "fb26447f-308b-471e-8b00-8e9f04284eb5"),
}


def detect_language(text: str) -> str:
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"
    if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
        return "ja"
    if re.search(r'[\uac00-\ud7af]', text):
        return "ko"
    return "en"

system_prompt = os.getenv("SYSTEM_PROMPT", """You are Xiaozhi (小智), a helpful and friendly voice AI assistant.
You assist users with their questions by providing clear, concise, and accurate information.

IMPORTANT LANGUAGE RULES:
- ALWAYS respond in the SAME language the user speaks to you.
- If the user speaks Chinese, respond in Chinese.
- If the user speaks English, respond in English.
- If the user speaks Japanese, respond in Japanese.
- Match the user's language automatically without asking.

Your responses should be natural and conversational, suitable for voice output.
Keep responses brief and to the point since this is a voice interface.
Avoid using markdown formatting, bullet points, or special characters that don't work well in speech.""")

logger.info(f"LiveKit Agent Worker starting with name: {livekit_agent_name}")


class VoiceAssistant(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)
        self.current_language = "en"
        logger.info("Voice assistant initialized")

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Greet the user briefly in their language and offer your assistance."
        )
    
    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        user_text = new_message.text_content if hasattr(new_message, 'text_content') else str(new_message)
        detected_lang = detect_language(user_text)
        
        if detected_lang != self.current_language:
            self.current_language = detected_lang
            new_tts = get_tts_for_language(detected_lang)
            self.session.update_tts(new_tts)
            logger.info(f"Language switched to: {detected_lang}, TTS: {new_tts}")


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


def get_tts_for_language(lang: str = "en") -> str:
    return inference.TTS(model="cartesia/sonic-3", voice=VOICE_MAP[lang])


async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }
    
    logger.info(f"Joining room: {ctx.room.name}")

    session = AgentSession(
        stt=inference.STT(model="deepgram/nova-3", language="multi"),
        llm=inference.LLM(model="openai/gpt-4.1-mini"),
        tts=get_tts_for_language(),
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
