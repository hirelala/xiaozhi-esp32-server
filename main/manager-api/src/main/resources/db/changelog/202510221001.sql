-- liquibase formatted sql

-- changeset gary:202510221001
-- comment: Add ElevenLabs Agents V2V Provider

-- 1. 插入 ElevenLabs V2V 模型供应器
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_V2V_ElevenLabs', 'V2V', 'elevenlabs', 'ElevenLabs Agents', '[{"key":"api_key","label":"ElevenLabs API Key","type":"string"},{"key":"agent_id","label":"Agent ID","type":"string"},{"key":"signed_url","label":"Signed URL (Optional)","type":"string"},{"key":"audio_format","label":"Audio Format","type":"string","default":"pcm_16000"}]', 2, 1, NOW(), 1, NOW());

-- 2. 插入默认的 ElevenLabs Agents 配置
INSERT INTO `ai_model_config` VALUES (
    'V2V_ElevenLabs', 
    'V2V', 
    'ElevenLabs', 
    'ElevenLabs Agents', 
    0, 
    1, 
    '{"type": "elevenlabs", "api_key": "", "agent_id": "", "signed_url": "", "audio_format": "pcm_16000"}', 
    'https://elevenlabs.io/docs/agents-platform/overview', 
    'ElevenLabs Agents Platform with built-in ASR, LLM, TTS, and turn-taking', 
    2, 
    NULL, 
    NULL, 
    NULL, 
    NULL
);

COMMIT;


