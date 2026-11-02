const OWNER = "manojkumar166-png";
const REPO = "stickman-lab";
const BRANCH = "main";

const WORKFLOW_FILE = "science-channel-daily-planner.yml";
const AI_VIDEO_WORKFLOW_FILE = "ai-video-test.yml";
const IMPORT_WORKFLOW_FILE = "telegram-zip-import.yml";
const RENDER_WORKFLOW_FILE = "free-science-visuals.yml";

const EPISODE_ROOT = "science-channel/daily-episodes";
const UPLOAD_ROOT = "science-channel/telegram-uploads";
const TOPIC_CONTROL_FILE = "science-channel/history/topic-control.json";

const MAX_ZIP_SIZE = 25 * 1024 * 1024;
const UPLOAD_LINK_HOURS = 24;

const DEFAULT_WORKER_URL =
  "https://frosty-disk-7c9e.pallipattumanoj.workers.dev";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    try {
      if (url.pathname === "/health" && request.method === "GET") {
        return json(await health(env));
      }

      if (url.pathname === "/setup" && request.method === "GET") {
        return json(await registerWebhook(env));
      }

      if (url.pathname === "/upload" && request.method === "GET") {
        return await showUploadPage(url, env);
      }

      if (url.pathname === "/upload" && request.method === "POST") {
        return await handleBrowserUpload(request, env);
      }

      if (url.pathname === "/" && request.method === "GET") {
        return new Response("Stickman Lab control centre is running.", {
          headers: { "content-type": "text/plain; charset=utf-8" }
        });
      }

      if (url.pathname === "/" && request.method === "POST") {
        if (
          env.TELEGRAM_WEBHOOK_SECRET &&
          request.headers.get("X-Telegram-Bot-Api-Secret-Token") !==
            env.TELEGRAM_WEBHOOK_SECRET
        ) {
          return new Response("Unauthorized", { status: 401 });
        }

        const update = await request.json();

        if (update.message && shouldForwardToImageReceiver(update.message, env)) {
          await forwardTelegramUpdate(update, env);
          return new Response("OK");
        }

        if (update.callback_query) {
          await handleCallback(update.callback_query, env);
        } else if (update.message) {
          await handleMessage(update.message, env);
        }

        return new Response("OK");
      }

      return new Response("Not found", { status: 404 });
    } catch (error) {
      console.error("Worker error:", error);

      return new Response(
        "Something went wrong. Check the Cloudflare Worker logs.",
        { status: 500 }
      );
    }
  }
};

/* ---------------- BASIC HELPERS ---------------- */

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" }
  });
}

function html(content, status = 200) {
  return new Response(content, {
    status,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function requireEnv(env, name) {
  if (!env[name]) {
    throw new Error(`Missing Worker setting: ${name}`);
  }

  return env[name];
}

function isAuthorized(userId, env) {
  return String(userId) === String(env.TELEGRAM_ALLOWED_USER_ID || "");
}

/* ---------------- MAIN MENU ---------------- */

function mainMenuKeyboard() {
  return {
    keyboard: [
      [
        { text: "📅 Daily Episodes" },
        { text: "🎬 Generate" }
      ],
      [
        { text: "💡 Topic" },
        { text: "📤 Upload Images" }
      ],
      [
        { text: "📊 Status" },
        { text: "🖼 Prompts" }
      ],
      [
        { text: "📋 Runs" },
        { text: "❤️ Health" }
      ]
    ],
    resize_keyboard: true,
    is_persistent: true
  };
}

async function sendMainMenu(chatId, env) {
  return sendTelegramMessage(
    chatId,
    "STICKMAN LAB CONTROL CENTRE\n\nChoose an option:",
    env,
    { reply_markup: mainMenuKeyboard() }
  );
}

/* ---------------- TELEGRAM API ---------------- */

async function telegramApi(method, body, env) {
  const token = requireEnv(env, "TELEGRAM_BOT_TOKEN");

  const response = await fetch(
    `https://api.telegram.org/bot${token}/${method}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body)
    }
  );

  const result = await response.json();

  if (!response.ok || !result.ok) {
    throw new Error(`Telegram API error: ${JSON.stringify(result)}`);
  }

  return result.result;
}

async function sendTelegramMessage(chatId, text, env, extra = {}) {
  return telegramApi(
    "sendMessage",
    {
      chat_id: chatId,
      text,
      disable_web_page_preview: true,
      ...extra
    },
    env
  );
}

async function answerCallback(callbackId, text, env) {
  return telegramApi(
    "answerCallbackQuery",
    {
      callback_query_id: callbackId,
      text
    },
    env
  );
}

/* ---------------- WEBHOOK ---------------- */

async function registerWebhook(env) {
  const token = requireEnv(env, "TELEGRAM_BOT_TOKEN");
  const secret = requireEnv(env, "TELEGRAM_WEBHOOK_SECRET");

  const workerUrl = env.PUBLIC_WORKER_URL || DEFAULT_WORKER_URL;
  const webhookUrl = `${workerUrl.replace(/\/$/, "")}/`;

  const response = await fetch(
    `https://api.telegram.org/bot${token}/setWebhook`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        url: webhookUrl,
        secret_token: secret,
        allowed_updates: ["message", "callback_query"]
      })
    }
  );

  return {
    webhook_url: webhookUrl,
    telegram_response: await response.json()
  };
}

/* ---------------- GITHUB ACTIONS TELEGRAM RELAY ---------------- */

// Image files and /episode selection messages are handed to the existing
// Science Channel receiver workflow. All other messages stay in this Worker.
function shouldForwardToImageReceiver(message, env) {
  if (!isAuthorized(message.from?.id, env)) return false;

  const text = (message.text || "").trim();
  const isEpisodeSelection = /^\/episode(?:@\w+)?(?:\s|$)/i.test(text);
  const isPhoto = Array.isArray(message.photo) && message.photo.length > 0;
  const document = message.document || {};
  const filename = (document.file_name || "").toLowerCase();
  const mime = (document.mime_type || "").toLowerCase();
  const isSupportedDocument =
    filename.endsWith(".zip") ||
    mime === "application/zip" ||
    mime === "application/x-zip-compressed" ||
    (mime.startsWith("image/") &&
      (["image/jpeg", "image/png", "image/webp"].includes(mime) ||
       /\.(jpg|jpeg|png|webp)$/i.test(filename)));

  return isEpisodeSelection || isPhoto || isSupportedDocument;
}

async function forwardTelegramUpdate(update, env) {
  const token = requireEnv(env, "GITHUB_TOKEN");
  const response = await fetch(
    "https://api.github.com/repos/" + OWNER + "/" + REPO + "/dispatches",
    {
      method: "POST",
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "content-type": "application/json",
        "user-agent": "StickmanLab-Control-Bot"
      },
      body: JSON.stringify({
        event_type: "telegram_image_upload",
        client_payload: { update }
      })
    }
  );

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Could not hand Telegram upload to GitHub Actions (${response.status}): ${detail.slice(0, 500)}`);
  }
}

/* ---------------- MESSAGE HANDLER ---------------- */

async function handleMessage(message, env) {
  const chatId = message.chat.id;
  const userId = message.from?.id;

  if (!isAuthorized(userId, env)) return;

  if (message.document) {
    await sendTelegramMessage(
      chatId,
      "Please use the browser ZIP upload link. Select an episode using Daily Episodes or Upload Images.",
      env,
      { reply_markup: mainMenuKeyboard() }
    );
    return;
  }

  const text = (message.text || "").trim();
  if (!text) return;

  const command = text.split(/\s+/)[0].split("@")[0].toLowerCase();

  const menuActions = {
    "📅 Daily Episodes": () => sendEpisodeKeyboard(chatId, env),
    "🎬 Generate": () => generate(chatId, env),
    "💡 Topic": () => showTopicKeyboard(chatId, env),
    "📤 Upload Images": () => sendUploadEpisodeKeyboard(chatId, env),
    "📊 Status": () => showStatus(chatId, env),
    "🖼 Prompts": () => showPrompts(chatId, env),
    "📋 Runs": () => showRuns(chatId, env),
    "❤️ Health": async () => {
      const result = await health(env);

      await sendTelegramMessage(
        chatId,
        JSON.stringify(result, null, 2),
        env,
        { reply_markup: mainMenuKeyboard() }
      );
    }
  };

  if (menuActions[text]) {
    await menuActions[text]();
    return;
  }

  if (command === "/topic") {
    const topic = text.replace(/^\/topic(@\w+)?/i, "").trim();

    if (!topic) {
      await showTopicKeyboard(chatId, env);
      return;
    }

    if (topic.length > 500) {
      await sendTelegramMessage(
        chatId,
        "Topic is too long. Keep it under 500 characters.",
        env
      );
      return;
    }

    try {
      await setNextTopic(topic, env);

      await sendTelegramMessage(
        chatId,
        `✅ Exact topic saved for the next Gemini planner run:\n\n${topic}`,
        env,
        { reply_markup: mainMenuKeyboard() }
      );
    } catch (error) {
      await sendTelegramMessage(
        chatId,
        `Could not save topic: ${error.message}`,
        env
      );
    }

    return;
  }

  if (command === "/episodes") {
    await sendEpisodeKeyboard(chatId, env);
    return;
  }

  await handleCommand(chatId, text, env);
}

/* ---------------- CALLBACK HANDLER ---------------- */

async function handleCallback(callback, env) {
  if (!isAuthorized(callback.from?.id, env)) {
    await answerCallback(callback.id, "Not authorized.", env);
    return;
  }

  const data = callback.data || "";
  const chatId = callback.message?.chat?.id;

  if (data === "episodes:dates") {
    await answerCallback(callback.id, "Loading dates...", env);
    await sendEpisodeKeyboard(chatId, env);
    return;
  }

  if (data.startsWith("day:")) {
    await handleDaySelection(callback, env);
    return;
  }

  if (data.startsWith("daily_ep:")) {
    await handleDailyEpisodeSelection(callback, env);
    return;
  }

  if (data.startsWith("upload_ep:")) {
    await handleUploadEpisodeSelection(callback, env);
    return;
  }

  if (data === "topic:auto") {
    try {
      await setAutomaticTopic(env);

      await answerCallback(
        callback.id,
        "Automatic topic enabled.",
        env
      );

      await sendTelegramMessage(
        chatId,
        "✅ Automatic topic selection enabled.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
    } catch (error) {
      await answerCallback(
        callback.id,
        "Could not update topic.",
        env
      );

      await sendTelegramMessage(
        chatId,
        `Topic update failed: ${error.message}`,
        env
      );
    }

    return;
  }

  if (data === "topic:exact") {
    await answerCallback(
      callback.id,
      "Send your exact topic.",
      env
    );

    await sendTelegramMessage(
      chatId,
      "✏️ Send your exact topic in this format:\n\n/topic Your exact science topic",
      env
    );

    return;
  }

  if (data.startsWith("generate:")) {
    const choice = data.slice("generate:".length);

    const workflows = {
      ai_video: {
        file: AI_VIDEO_WORKFLOW_FILE,
        label: "AI Video Planner"
      },
      gemini: {
        file: WORKFLOW_FILE,
        label: "Gemini Planner"
      },
      freevisual: {
        file: RENDER_WORKFLOW_FILE,
        label: "FreeVisual Science"
      }
    };

    const selected = workflows[choice];

    if (!selected) {
      await answerCallback(callback.id, "Unknown workflow.", env);
      return;
    }

    await answerCallback(
      callback.id,
      `Starting ${selected.label}...`,
      env
    );

    await dispatchSelectedWorkflow(chatId, selected, env);
    return;
  }

  await answerCallback(callback.id, "Unknown selection.", env);
}

/* ---------------- GITHUB API ---------------- */

async function gh(env, path, options = {}) {
  const token = requireEnv(env, "GITHUB_TOKEN");

  const response = await fetch(
    `https://api.github.com${path}`,
    {
      ...options,
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "content-type": "application/json",
        "user-agent": "StickmanLab-Control-Bot",
        ...(options.headers || {})
      }
    }
  );

  const bodyText = await response.text();
  let data = {};

  try {
    data = bodyText ? JSON.parse(bodyText) : {};
  } catch {
    data = { message: bodyText };
  }

  if (!response.ok) {
    throw new Error(
      `GitHub API ${response.status}: ${data.message || bodyText}`
    );
  }

  return data;
}

function repoPath(path) {
  return `/repos/${OWNER}/${REPO}${path}`;
}

function workflowPath(file) {
  return repoPath(
    `/actions/workflows/${encodeURIComponent(file)}`
  );
}

/* ---------------- EPISODE DISCOVERY ---------------- */

async function listEpisodeDates(env) {
  const result = await gh(
    env,
    repoPath(`/contents/${EPISODE_ROOT}?ref=${BRANCH}`)
  );

  if (!Array.isArray(result)) return [];

  return result
    .filter(x => x.type === "dir" && /^\d{4}-\d{2}-\d{2}$/.test(x.name))
    .map(x => ({ name: x.name, path: x.path }))
    .sort((a, b) => b.name.localeCompare(a.name));
}

async function listEpisodesForDate(env, datePath) {
  if (!/^science-channel\/daily-episodes\/\d{4}-\d{2}-\d{2}$/.test(datePath)) {
    throw new Error("Invalid episode date folder.");
  }

  const result = await gh(
    env,
    repoPath(`/contents/${datePath}?ref=${BRANCH}`)
  );

  if (!Array.isArray(result)) return [];

  return result
    .filter(x =>
      x.type === "dir" &&
      /^episode-\d{3}(?:-|$)/i.test(x.name)
    )
    .map(x => ({ name: x.name, path: x.path }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

async function episodeDirectories(env) {
  const dates = await listEpisodeDates(env);
  const all = [];

  for (const date of dates) {
    const episodes = await listEpisodesForDate(env, date.path);

    for (const episode of episodes) {
      all.push({
        ...episode,
        date: date.name
      });
    }
  }

  return all.sort((a, b) =>
    b.date.localeCompare(a.date) ||
    a.name.localeCompare(b.name)
  );
}

async function getFile(env, path) {
  return gh(
    env,
    repoPath(`/contents/${path}?ref=${BRANCH}`)
  );
}

async function fileText(env, path) {
  const file = await getFile(env, path);

  if (!file.content) return "";

  return atob(file.content.replace(/\n/g, ""));
}

async function latestEpisode(env) {
  const episodes = await episodeDirectories(env);
  return episodes[0] || null;
}

/* ---------------- EPISODE SELECTION ---------------- */

async function sendEpisodeKeyboard(chatId, env) {
  try {
    const dates = await listEpisodeDates(env);

    if (!dates.length) {
      await sendTelegramMessage(
        chatId,
        "No date folders found in daily-episodes.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
      return;
    }

    const keyboard = dates.slice(0, 30).map((date, index) => [{
      text: `📅 ${date.name}`,
      callback_data: `day:${index}`
    }]);

    await sendTelegramMessage(
      chatId,
      "📅 DAILY EPISODES\n\nSelect a date:",
      env,
      {
        reply_markup: {
          inline_keyboard: keyboard
        }
      }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not load daily episodes: ${error.message}`,
      env
    );
  }
}

async function handleDaySelection(callback, env) {
  const index = Number(callback.data.split(":")[1]);
  const chatId = callback.message.chat.id;

  try {
    const dates = await listEpisodeDates(env);
    const date = dates.slice(0, 30)[index];

    if (!date) {
      await answerCallback(callback.id, "Date not found.", env);
      return;
    }

    const episodes = await listEpisodesForDate(env, date.path);

    if (!episodes.length) {
      await answerCallback(callback.id, "No episodes in this date.", env);
      return;
    }

    const keyboard = episodes.map((episode, i) => [{
      text: `🎬 ${episode.name}`.slice(0, 60),
      callback_data: `daily_ep:${index}:${i}`
    }]);

    keyboard.push([{
      text: "⬅️ Back to dates",
      callback_data: "episodes:dates"
    }]);

    await answerCallback(callback.id, "Date selected.", env);

    await sendTelegramMessage(
      chatId,
      `📅 ${date.name}\n\nSelect an episode:`,
      env,
      {
        reply_markup: {
          inline_keyboard: keyboard
        }
      }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not load episodes: ${error.message}`,
      env
    );
  }
}

async function handleDailyEpisodeSelection(callback, env) {
  const parts = callback.data.split(":");
  const dateIndex = Number(parts[1]);
  const episodeIndex = Number(parts[2]);
  const chatId = callback.message.chat.id;

  try {
    const dates = await listEpisodeDates(env);
    const date = dates.slice(0, 30)[dateIndex];

    if (!date) throw new Error("Date folder not found.");

    const episodes = await listEpisodesForDate(env, date.path);
    const episode = episodes[episodeIndex];

    if (!episode) throw new Error("Episode folder not found.");

    const files = await gh(
      env,
      repoPath(`/contents/${episode.path}?ref=${BRANCH}`)
    );

    const fileLines = Array.isArray(files)
      ? files.map(file =>
          `${file.type === "dir" ? "📁" : "📄"} ${file.name}`
        )
      : [];

    await answerCallback(callback.id, "Episode opened.", env);

    await sendTelegramMessage(
      chatId,
      [
        "🎬 EPISODE DETAILS",
        "",
        `Date: ${date.name}`,
        `Episode: ${episode.name}`,
        "",
        "📂 CONTENTS",
        ...fileLines,
        "",
        `GitHub: https://github.com/${OWNER}/${REPO}/tree/${BRANCH}/${episode.path}`
      ].join("\n").slice(0, 3900),
      env,
      {
        reply_markup: {
          inline_keyboard: [
            [{
              text: "⬅️ Back to episodes",
              callback_data: `day:${dateIndex}`
            }],
            [{
              text: "📅 All dates",
              callback_data: "episodes:dates"
            }]
          ]
        }
      }
    );
  } catch (error) {
    await answerCallback(callback.id, "Could not open episode.", env);
    await sendTelegramMessage(
      chatId,
      error.message,
      env
    );
  }
}

async function sendUploadEpisodeKeyboard(chatId, env) {
  try {
    const episodes = await episodeDirectories(env);

    if (!episodes.length) {
      await sendTelegramMessage(
        chatId,
        "No episode folders found under daily-episodes.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
      return;
    }

    const keyboard = episodes.slice(0, 30).map((episode, index) => [{
      text: `${episode.date} | ${episode.name}`.slice(0, 60),
      callback_data: `upload_ep:${index}`
    }]);

    await sendTelegramMessage(
      chatId,
      "📤 UPLOAD IMAGES\n\nSelect the episode for your ZIP upload:",
      env,
      {
        reply_markup: {
          inline_keyboard: keyboard
        }
      }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not load upload episodes: ${error.message}`,
      env
    );
  }
}

async function handleUploadEpisodeSelection(callback, env) {
  const index = Number(callback.data.split(":")[1]);
  const chatId = callback.message.chat.id;

  try {
    const episodes = await episodeDirectories(env);
    const episode = episodes.slice(0, 30)[index];

    if (!episode) throw new Error("Episode not found.");

    const uploadUrl = await createUploadUrl(episode.path, env);

    await answerCallback(callback.id, "Episode selected.", env);

    await sendTelegramMessage(
      chatId,
      [
        "📤 EPISODE SELECTED",
        "",
        `Date: ${episode.date}`,
        `Episode: ${episode.name}`,
        "",
        "🌐 BROWSER ZIP UPLOAD",
        uploadUrl,
        "",
        "ZIP requirements:",
        "• ZIP file only",
        "• Maximum size: 25 MB",
        "• Exactly 48 supported images",
        "",
        "The importer will validate the ZIP after upload."
      ].join("\n"),
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  } catch (error) {
    await answerCallback(callback.id, "Could not select episode.", env);

    await sendTelegramMessage(
      chatId,
      `Upload link could not be created: ${error.message}`,
      env
    );
  }
}

/* ---------------- TOPIC CONTROL ---------------- */

async function showTopicKeyboard(chatId, env) {
  await sendTelegramMessage(
    chatId,
    "💡 TOPIC SETTINGS\n\nChoose how the next Gemini planner run selects its topic:",
    env,
    {
      reply_markup: {
        inline_keyboard: [
          [
            {
              text: "✏️ Choose exact topic",
              callback_data: "topic:exact"
            }
          ],
          [
            {
              text: "🤖 Automatic topic",
              callback_data: "topic:auto"
            }
          ]
        ]
      }
    }
  );
}

async function readTopicControl(env) {
  try {
    const file = await getFile(env, TOPIC_CONTROL_FILE);

    if (!file.content) {
      return { mode: "auto", next_topic: null };
    }

    return JSON.parse(
      atob(file.content.replace(/\n/g, ""))
    );
  } catch (error) {
    if (String(error.message).includes("404")) {
      return { mode: "auto", next_topic: null };
    }

    throw error;
  }
}

async function writeTopicControl(env, value, message) {
  let sha;

  try {
    const existing = await getFile(env, TOPIC_CONTROL_FILE);
    sha = existing.sha;
  } catch (error) {
    if (!String(error.message).includes("404")) throw error;
  }

  const body = {
    message,
    content: btoa(
      unescape(encodeURIComponent(JSON.stringify(value, null, 2) + "\n"))
    ),
    branch: BRANCH
  };

  if (sha) body.sha = sha;

  await gh(
    env,
    repoPath(`/contents/${TOPIC_CONTROL_FILE}`),
    {
      method: "PUT",
      body: JSON.stringify(body)
    }
  );
}

async function setNextTopic(topic, env) {
  await writeTopicControl(
    env,
    {
      mode: "manual",
      next_topic: topic
    },
    "Set next Stickman Lab planner topic"
  );
}

async function setAutomaticTopic(env) {
  await writeTopicControl(
    env,
    {
      mode: "auto",
      next_topic: null
    },
    "Enable automatic Stickman Lab planner topic"
  );
}

/* ---------------- SIGNED UPLOAD LINKS ---------------- */

async function createUploadUrl(episodePath, env) {
  const secret = requireEnv(env, "UPLOAD_LINK_SECRET");

  if (!isValidEpisodePath(episodePath)) {
    throw new Error("Invalid episode path.");
  }

  const expires =
    Math.floor(Date.now() / 1000) +
    UPLOAD_LINK_HOURS * 60 * 60;

  const signature = await signUploadToken(
    `${episodePath}:${expires}`,
    secret
  );

  const base = env.PUBLIC_WORKER_URL || DEFAULT_WORKER_URL;
  const url = new URL("/upload", base);

  url.searchParams.set("episode", episodePath);
  url.searchParams.set("expires", String(expires));
  url.searchParams.set("signature", signature);

  return url.toString();
}

async function signUploadToken(value, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    {
      name: "HMAC",
      hash: "SHA-256"
    },
    false,
    ["sign"]
  );

  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(value)
  );

  return Array.from(new Uint8Array(signature))
    .map(byte => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function verifyUploadToken(url, env) {
  const episodePath = url.searchParams.get("episode") || "";
  const expires = url.searchParams.get("expires") || "";
  const suppliedSignature =
    url.searchParams.get("signature") || "";

  if (!isValidEpisodePath(episodePath)) {
    throw new Error("Invalid episode path.");
  }

  if (!/^\d{10}$/.test(expires)) {
    throw new Error("Invalid or missing expiry.");
  }

  if (Number(expires) < Math.floor(Date.now() / 1000)) {
    throw new Error("This upload link has expired.");
  }

  const secret = requireEnv(env, "UPLOAD_LINK_SECRET");

  const expectedSignature = await signUploadToken(
    `${episodePath}:${expires}`,
    secret
  );

  if (!constantTimeEqual(suppliedSignature, expectedSignature)) {
    throw new Error("Invalid upload link.");
  }

  return episodePath;
}

function constantTimeEqual(a, b) {
  if (a.length !== b.length) return false;

  let result = 0;

  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }

  return result === 0;
}

function isValidEpisodePath(path) {
  return /^science-channel\/daily-episodes\/\d{4}-\d{2}-\d{2}\/episode-\d{3}(?:-|$)/.test(
    path