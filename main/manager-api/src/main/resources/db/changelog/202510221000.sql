-- 添加 Voice2Voice (LiveKit) 配置支持
-- 本文件用于添加 Voice2Voice 模型类型和 AI Agent 的 Voice2Voice 模式支持

-- 1. 在 ai_agent 表中添加 voice2voice 相关字段
ALTER TABLE `ai_agent` ADD COLUMN `enable_voice2voice` TINYINT(1) DEFAULT 0 COMMENT '是否启用Voice2Voice模式(0否 1是)' AFTER `intent_model_id`;
ALTER TABLE `ai_agent` ADD COLUMN `v2v_model_id` VARCHAR(32) DEFAULT NULL COMMENT 'Voice2Voice模型标识' AFTER `enable_voice2voice`;

-- 2. 在 ai_agent_template 表中添加相应字段以支持模板
ALTER TABLE `ai_agent_template` ADD COLUMN `enable_voice2voice` TINYINT(1) DEFAULT 0 COMMENT '是否启用Voice2Voice模式(0否 1是)' AFTER `intent_model_id`;
ALTER TABLE `ai_agent_template` ADD COLUMN `v2v_model_id` VARCHAR(32) DEFAULT NULL COMMENT 'Voice2Voice模型标识' AFTER `enable_voice2voice`;

-- 3. 插入 V2V 模型供应器
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_V2V_LiveKit', 'V2V', 'livekit', 'LiveKit Voice2Voice', '[{"key":"api_key","label":"LiveKit API Key","type":"string"},{"key":"api_secret","label":"LiveKit API Secret","type":"string"},{"key":"url","label":"LiveKit URL","type":"string"},{"key":"openai_api_key","label":"OpenAI API Key (Optional)","type":"string"},{"key":"openai_model","label":"OpenAI Model","type":"string","default":"gpt-4o-realtime-preview-2024-12-17"}]', 1, 1, NOW(), 1, NOW());

-- 4. 插入默认的 LiveKit Voice2Voice 配置
INSERT INTO `ai_model_config` VALUES (
    'V2V_LiveKit', 
    'V2V', 
    'LiveKit', 
    'LiveKit Voice2Voice', 
    1, 
    1, 
    '{"type": "livekit", "api_key": "", "api_secret": "", "url": "", "openai_api_key": "", "openai_model": "gpt-4o-realtime-preview-2024-12-17"}', 
    'https://docs.livekit.io/agents/overview/', 
    'LiveKit Agents with OpenAI Realtime API for voice-to-voice conversation', 
    1, 
    NULL, 
    NULL, 
    NULL, 
    NULL
);

COMMIT;

