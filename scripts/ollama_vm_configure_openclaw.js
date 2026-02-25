#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

function toBool(value, defaultValue = false) {
  if (value === undefined || value === null || value === "") return defaultValue;
  return String(value).toLowerCase() === "true" || String(value) === "1";
}

function ensure(obj, ...keys) {
  let cur = obj;
  for (const key of keys) {
    cur[key] = cur[key] || {};
    cur = cur[key];
  }
  return cur;
}

const vmRoot = process.env.OLLAMA_VM_ROOT || "/vm";
const homeDir = process.env.HOME || vmRoot;
const openclawHome = process.env.OLLAMA_VM_OPENCLAW_HOME || path.join(homeDir, ".openclaw");
const workspaceDir = process.env.OPENCLAW_WORKSPACE_DIR || path.join(vmRoot, "workspace");
const configPath = process.env.OLLAMA_VM_OPENCLAW_CONFIG_PATH || path.join(openclawHome, "openclaw.json");

const gatewayPort = parseInt(process.env.OPENCLAW_GATEWAY_PORT || "18789", 10);
const gatewayBind = process.env.OPENCLAW_GATEWAY_BIND || "lan";
const gatewayToken = (process.env.OLLAMA_VM_OPENCLAW_GATEWAY_TOKEN || process.env.OPENCLAW_GATEWAY_TOKEN || "").trim();

const modelId = process.env.OLLAMA_VM_MODEL || process.env.OLLAMA_VM_OPENCLAW_MODEL || "gemma3:4b";
const ollamaBase = (process.env.OLLAMA_VM_BASE_URL || process.env.OLLAMA_VM_OLLAMA_BASE_URL || "http://127.0.0.1:11434").replace(/\/+$/, "");
const modelApi = (process.env.OLLAMA_VM_API || process.env.OLLAMA_VM_MODEL_API || "ollama").trim();
const modelProviderName = (process.env.OLLAMA_VM_PROVIDER || process.env.OLLAMA_VM_MODEL_PROVIDER || "ollama").trim();
const disableToolsExplicit = process.env.OLLAMA_VM_DISABLE_TOOLS;
const disableTools = disableToolsExplicit === undefined
  ? /^gemma/i.test(modelId)
  : toBool(disableToolsExplicit, false);
const reasoningEnabled = process.env.OLLAMA_VM_MODEL_REASONING === undefined
  ? !/^gemma/i.test(modelId)
  : toBool(process.env.OLLAMA_VM_MODEL_REASONING, false);
const skipBootstrap = process.env.OLLAMA_VM_SKIP_BOOTSTRAP === undefined
  ? modelProviderName === "lmstudio"
  : toBool(process.env.OLLAMA_VM_SKIP_BOOTSTRAP, false);

const allowedOriginsRaw = (process.env.OLLAMA_VM_OPENCLAW_ALLOWED_ORIGINS || "").trim();
const allowedOrigins = allowedOriginsRaw
  ? allowedOriginsRaw.split(",").map(s => s.trim()).filter(Boolean)
  : [];

fs.mkdirSync(path.dirname(configPath), { recursive: true });
fs.mkdirSync(workspaceDir, { recursive: true });

let config = {};
if (fs.existsSync(configPath)) {
  try {
    config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch {
    config = {};
  }
}

ensure(config, "models", "providers");
config.models.providers[modelProviderName] = {
  baseUrl: (modelApi === "openai-completions" && !ollamaBase.endsWith("/v1")) ? `${ollamaBase}/v1` : ollamaBase,
  apiKey: "ollama-local",
  api: modelApi,
  models: [
    {
      id: modelId,
      name: modelId,
      reasoning: reasoningEnabled,
      input: ["text"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 40960,
    },
  ],
};

ensure(config, "agents", "defaults", "model");
config.agents.defaults.model.primary = `${modelProviderName}/${modelId}`;
config.agents.defaults.workspace = workspaceDir;
delete config.agents.defaults.thinking;
config.agents.defaults.skipBootstrap = skipBootstrap;

ensure(config, "gateway");
config.gateway.port = gatewayPort;
config.gateway.bind = gatewayBind;
config.gateway.mode = "local";
ensure(config, "gateway", "auth");
config.gateway.auth.mode = "token";
config.gateway.auth.token = gatewayToken || "ollama";

ensure(config, "gateway", "controlUi");
config.gateway.controlUi.allowInsecureAuth = true;
if (allowedOrigins.length > 0) {
  config.gateway.controlUi.allowedOrigins = allowedOrigins;
  config.gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback = false;
} else if (gatewayBind !== "loopback") {
  // Required for non-loopback when explicit origins are not supplied.
  config.gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback = true;
}

if (config.tools && config.tools.browser) {
  // Older/newer OpenClaw schemas may reject tools.browser in JSON config.
  // Browser integration is better supplied via env vars at runtime.
  delete config.tools.browser;
}

if (disableTools) {
  // Gemma models on Ollama often reject OpenAI-style tool calls.
  // Deny all tools so OpenClaw does not send tool definitions.
  ensure(config, "tools");
  config.tools.deny = ["*"];
  delete config.tools.allow;
  delete config.tools.profile;
  delete config.tools.alsoAllow;
  delete config.tools.byProvider;
}

const tgToken = (process.env.TELEGRAM_BOT_TOKEN || "").trim();
if (tgToken) {
  ensure(config, "channels");
  const tg = (config.channels.telegram = config.channels.telegram || {});
  tg.enabled = true;
  tg.botToken = tgToken;
  tg.dmPolicy = process.env.TELEGRAM_DM_POLICY || "allowlist";
  tg.groupPolicy = process.env.TELEGRAM_GROUP_POLICY || "allowlist";
  tg.replyToMode = process.env.TELEGRAM_REPLY_TO_MODE || "all";
  tg.chunkMode = process.env.TELEGRAM_CHUNK_MODE || "newline";
  tg.textChunkLimit = parseInt(process.env.TELEGRAM_TEXT_CHUNK_LIMIT || "3500", 10);
  // Use block streaming by default to avoid leaking intermediate model/control tokens in chat channels.
  tg.streaming = process.env.TELEGRAM_STREAM_MODE || "block";
  tg.linkPreview = toBool(process.env.TELEGRAM_LINK_PREVIEW, false);
  tg.mediaMaxMb = parseInt(process.env.TELEGRAM_MEDIA_MAX_MB || "10", 10);
  tg.reactionNotifications = process.env.TELEGRAM_REACTION_NOTIFICATIONS || "own";
  tg.reactionLevel = process.env.TELEGRAM_REACTION_LEVEL || "minimal";
  tg.webhookUrl = process.env.TELEGRAM_WEBHOOK_URL || "";
  tg.webhookSecret = process.env.TELEGRAM_WEBHOOK_SECRET || "";
  tg.webhookPath = process.env.TELEGRAM_WEBHOOK_PATH || "/telegram-webhook";
  ensure(tg, "capabilities");
  tg.capabilities.inlineButtons = process.env.TELEGRAM_INLINE_BUTTONS || "allowlist";
  ensure(tg, "actions");
  tg.actions.reactions = toBool(process.env.TELEGRAM_ACTIONS_REACTIONS, true);
  tg.actions.sticker = toBool(process.env.TELEGRAM_ACTIONS_STICKER, false);
  // Remove legacy keys that newer OpenClaw rejects.
  delete tg.messagePrefix;
  delete tg.streamMode;

  if ((process.env.TELEGRAM_ALLOW_FROM || "").trim()) {
    tg.allowFrom = process.env.TELEGRAM_ALLOW_FROM.split(",").map(s => {
      const v = s.trim();
      const n = Number(v);
      return Number.isInteger(n) ? n : v;
    });
  }
  if ((process.env.TELEGRAM_GROUP_ALLOW_FROM || "").trim()) {
    tg.groupAllowFrom = process.env.TELEGRAM_GROUP_ALLOW_FROM.split(",").map(s => {
      const v = s.trim();
      const n = Number(v);
      return Number.isInteger(n) ? n : v;
    });
  }
}

config.meta = {
  ...(config.meta || {}),
  lastTouchedVersion: "ollama-vm-local",
  lastTouchedAt: new Date().toISOString(),
};

fs.writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`);
console.log(`[ollama-vm-config] wrote ${configPath}`);
