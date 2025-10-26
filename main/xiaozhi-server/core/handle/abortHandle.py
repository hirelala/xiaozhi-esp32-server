import json
import asyncio

TAG = __name__


async def handleAbortMessage(conn):
    conn.logger.bind(tag=TAG).info("Abort message received")
    
    conn.client_abort = True
    
    if conn.enable_voice2voice and hasattr(conn, 'v2v') and conn.v2v:
        conn.logger.bind(tag=TAG).info("V2V mode: Handling interrupt")
        
        if hasattr(conn, 'elevenlabs_audio_buffer'):
            conn.elevenlabs_audio_buffer.clear()
            conn.logger.bind(tag=TAG).debug("Cleared ElevenLabs audio buffer")
        
        if hasattr(conn, 'v2v_agent_audio_buffer'):
            conn.v2v_agent_audio_buffer.clear()
            conn.logger.bind(tag=TAG).debug("Cleared V2V agent audio buffer")
        
        conn.elevenlabs_audio_started = False
        conn.elevenlabs_agent_speaking = False
    else:
        conn.clear_queues()
    
    await conn.websocket.send(
        json.dumps({"type": "tts", "state": "stop", "session_id": conn.session_id})
    )
    conn.clearSpeakStatus()
    
    await asyncio.sleep(0.1)
    conn.client_abort = False
    
    conn.logger.bind(tag=TAG).info("Abort message received-end")
