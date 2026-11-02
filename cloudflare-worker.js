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

        if (update.callback_query) {
          await handleCallback(update.callback_query, env);
        } else if (update.message) {
          await handleMessage(update.message, env, update);
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

/* ---------------- TELEGRAM MEDIA QUEUE ---------------- */

async function queueTelegramUpdate(update, env) {
  const updateId = Number(update?.update_id);
  if (!Number.isSafeInteger(updateId) || updateId < 0) {
    throw new Error("Invalid Telegram update_id.");
  }

  const path = `.github/telegram-inbox/${updateId}.json`;
  const apiPath = repoPath(`/contents/${path}`);

  // Telegram may retry a webhook after a network timeout. Treat an already
  // queued update as success instead of creating duplicate image commits.
  try {
    const existing = await gh(env, apiPath + `?ref=${BRANCH}`);
    if (existing?.sha) return path;
  } catch (error) {
    if (!String(error.message).includes("GitHub API 404")) throw error;
  }

  const encoded = bytesToBase64(new TextEncoder().encode(JSON.stringify(update)));
  try {
    await gh(env, apiPath, {
      method: "PUT",
      body: JSON.stringify({
        message: `Queue Telegram media update ${updateId}`,
        content: encoded,
        branch: BRANCH
      })
    });
  } catch (error) {
    // Resolve a possible duplicate race by checking whether the same update
    // was committed by another webhook retry.
    if (String(error.message).includes("GitHub API 422")) {
      const existing = await gh(env, apiPath + `?ref=${BRANCH}`);
      if (existing?.sha) return path;
    }
    throw error;
  }

  return path;
}

/* ---------------- MESSAGE HANDLER ---------------- */

async function handleMessage(message, env, update) {
  const chatId = message.chat.id;
  const userId = message.from?.id;

  if (!isAuthorized(userId, env)) return;

  const document = message.document || {};
  const documentName = String(document.file_name || "").toLowerCase();
  const documentMime = String(document.mime_type || "").toLowerCase();
  const isZip = documentName.endsWith(".zip") ||
    ["application/zip", "application/x-zip-compressed"].includes(documentMime);
  const documentExtension = documentName.includes(".")
    ? documentName.split(".").pop()
    : "";
  const isImageDocument = documentMime.startsWith("image/") &&
    ["jpg", "jpeg", "png", "webp"].includes(documentExtension);
  const isPhoto = Array.isArray(message.photo) && message.photo.length > 0;

  if (isPhoto || isZip || isImageDocument) {
    try {
      if (!update || !Number.isSafeInteger(Number(update.update_id))) {
        throw new Error("Telegram update ID is missing; the upload cannot be queued safely.");
      }
      await queueTelegramUpdate(update, env);
      await sendTelegramMessage(
        chatId,
        isZip
          ? "📦 ZIP received and queued. I’ll validate its 48 images and prepare the episode."
          : "🖼 Image received and queued. I’ll add it to the selected episode.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
    } catch (error) {
      console.error("Could not queue Telegram media update:", error);
      await sendTelegramMessage(
        chatId,
        "I couldn't safely queue that upload. Please retry in a moment or use the browser ZIP upload link.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
    }
    return;
  }

  if (message.document) {
    await sendTelegramMessage(
      chatId,
      "Unsupported document. Send a JPG, PNG, WebP image, or a ZIP containing exactly 48 images.",
      env,
      { reply_markup: mainMenuKeyboard() }
    );
    return;
  }

  const text = (message.text || "").trim();
  if (!text) return;

  // Episode selection is handled by the same durable receiver queue as media
  // so selection changes and uploads are processed in their original order.
  if (/^\/episode(?:@\w+)?(?:\s|$)/i.test(text)) {
    try {
      if (!update || !Number.isSafeInteger(Number(update.update_id))) {
        throw new Error("Telegram update ID is missing.");
      }
      await queueTelegramUpdate(update, env);
      await sendTelegramMessage(
        chatId,
        "Episode selection received. I’ll apply it before processing your queued uploads.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
    } catch (error) {
      console.error("Could not queue episode selection:", error);
      await sendTelegramMessage(chatId, "I couldn't queue that episode selection. Please retry.", env);
    }
    return;
  }

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
  );
}

/* ---------------- UPLOAD PAGE ---------------- */

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function uploadHtml(title, message, form = "") {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
*{box-sizing:border-box}
body{
  margin:0;padding:30px 16px;min-height:100vh;
  display:flex;justify-content:center;align-items:center;
  background:#101827;color:#f8fafc;font-family:Arial,sans-serif
}
.card{
  width:100%;max-width:480px;padding:28px;
  border-radius:18px;background:#1e293b;
  box-shadow:0 12px 40px #0005
}
h1{font-size:25px;margin:0 0 14px}
p{line-height:1.6;color:#cbd5e1}
input[type=file]{
  display:block;width:100%;margin:22px 0;padding:12px;
  border:1px solid #475569;border-radius:9px;
  background:#0f172a;color:white
}
button{
  width:100%;padding:14px;border:0;border-radius:9px;
  background:#38bdf8;color:#082f49;font-size:16px;
  font-weight:bold;cursor:pointer
}
.small{font-size:13px;color:#94a3b8}
</style>
</head>
<body>
<div class="card">
<h1>${escapeHtml(title)}</h1>
<p>${escapeHtml(message)}</p>
${form}
</div>
</body>
</html>`;
}

async function showUploadPage(url, env) {
  try {
    const episodePath = await verifyUploadToken(url, env);
    const action = escapeHtml(url.pathname + url.search);

    const form = `
<form method="POST" action="${action}" enctype="multipart/form-data">
<input type="file" name="zipfile" accept=".zip,application/zip" required>
<p class="small">ZIP only. Maximum size 25 MB. Exactly 48 images.</p>
<button type="submit">Upload ZIP</button>
</form>`;

    return html(
      uploadHtml(
        "Stickman Lab Episode Upload",
        `Selected episode: ${episodePath}`,
        form
      )
    );
  } catch (error) {
    return html(
      uploadHtml("Upload link unavailable", error.message),
      400
    );
  }
}

/* ---------------- ZIP UPLOAD HANDLER ---------------- */

async function handleBrowserUpload(request, env) {
  const url = new URL(request.url);

  let episodePath;

  try {
    episodePath = await verifyUploadToken(url, env);
  } catch (error) {
    return html(
      uploadHtml("Upload link unavailable", error.message),
      400
    );
  }

  const contentLength = Number(
    request.headers.get("content-length") || 0
  );

  if (contentLength > MAX_ZIP_SIZE + 1024 * 1024) {
    return html(
      uploadHtml("File too large", "The upload exceeds the 25 MB limit."),
      413
    );
  }

  try {
    const formData = await request.formData();
    const file = formData.get("zipfile");

    if (!file || typeof file.arrayBuffer !== "function") {
      throw new Error("Please select a ZIP file.");
    }

    if (file.size < 1 || file.size > MAX_ZIP_SIZE) {
      throw new Error("ZIP size must be between 1 byte and 25 MB.");
    }

    if (!file.name.toLowerCase().endsWith(".zip")) {
      throw new Error("Only .zip files are accepted.");
    }

    const bytes = new Uint8Array(await file.arrayBuffer());

    if (!isZipFile(bytes)) {
      throw new Error("The uploaded file is not a valid ZIP archive.");
    }

    const stagedPath = await stageZipInGitHub(env, bytes);

    await dispatchZipImporter(env, episodePath, stagedPath);

    return html(
      uploadHtml(
        "ZIP uploaded successfully",
        "Your ZIP has been staged in GitHub. The importer workflow has started. It will check for exactly 48 supported images. Use Status in Telegram to check progress."
      )
    );
  } catch (error) {
    console.error("Browser upload error:", error);

    return html(
      uploadHtml("Upload failed", error.message || "Upload failed."),
      400
    );
  }
}

function isZipFile(bytes) {
  if (!bytes || bytes.length < 4) return false;

  return (
    bytes[0] === 0x50 &&
    bytes[1] === 0x4b &&
    (
      (bytes[2] === 0x03 && bytes[3] === 0x04) ||
      (bytes[2] === 0x05 && bytes[3] === 0x06) ||
      (bytes[2] === 0x07 && bytes[3] === 0x08)
    )
  );
}

function bytesToBase64(bytes) {
  const chunkSize = 0x8000;
  let binary = "";

  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(
      i,
      Math.min(i + chunkSize, bytes.length)
    );

    binary += String.fromCharCode(...chunk);
  }

  return btoa(binary);
}

/* ---------------- STAGE ZIP IN GITHUB ---------------- */

async function stageZipInGitHub(env, bytes) {
  const uuid = crypto.randomUUID();
  const path = `${UPLOAD_ROOT}/${uuid}.zip`;

  await gh(
    env,
    repoPath(`/contents/${path}`),
    {
      method: "PUT",
      body: JSON.stringify({
        message: `Stage browser episode ZIP ${uuid}`,
        content: bytesToBase64(bytes),
        branch: BRANCH
      })
    }
  );

  return path;
}

/* ---------------- DISPATCH ZIP IMPORTER ---------------- */

async function dispatchZipImporter(env, episodePath, zipPath) {
  await gh(
    env,
    workflowPath(IMPORT_WORKFLOW_FILE) + "/dispatches",
    {
      method: "POST",
      body: JSON.stringify({
        ref: BRANCH,
        inputs: {
          episode_path: episodePath,
          zip_path: zipPath
        }
      })
    }
  );
}

/* ---------------- GENERATE WORKFLOW CHOOSER ---------------- */

async function generate(chatId, env) {
  await sendTelegramMessage(
    chatId,
    "🎬 GENERATE\n\nChoose which workflow to start:",
    env,
    {
      reply_markup: {
        inline_keyboard: [
          [
            {
              text: "🎨 AI Video Planner",
              callback_data: "generate:ai_video"
            }
          ],
          [
            {
              text: "🧠 Gemini Planner",
              callback_data: "generate:gemini"
            }
          ],
          [
            {
              text: "🔬 FreeVisual Science",
              callback_data: "generate:freevisual"
            }
          ]
        ]
      }
    }
  );
}

/* ---------------- DISPATCH SELECTED WORKFLOW ---------------- */

async function dispatchSelectedWorkflow(chatId, workflow, env) {
  try {
    const workflowInfo = await gh(
      env,
      workflowPath(workflow.file)
    );

    if (workflowInfo.state !== "active") {
      throw new Error(
        `The GitHub workflow is not active: ${workflow.file}`
      );
    }

    await gh(
      env,
      workflowPath(workflow.file) + "/dispatches",
      {
        method: "POST",
        body: JSON.stringify({
          ref: "main"
        })
      }
    );

    await sendTelegramMessage(
      chatId,
      [
        `✅ ${workflow.label} started successfully.`,
        "",
        `Repository: ${OWNER}/${REPO}`,
        "Branch: main",
        `Workflow: ${workflow.file}`,
        "",
        "Use Status or Runs to check progress."
      ].join("\n"),
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  } catch (error) {
    console.error(
      `Workflow dispatch failed (${workflow.file}):`,
      error
    );

    await sendTelegramMessage(
      chatId,
      `❌ Could not start ${workflow.label}:\n${error.message}`,
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  }
}

/* ---------------- WORKFLOW DEFINITIONS & RUNS ---------------- */

const TRACKED_WORKFLOWS = [
  {
    label: "Gemini Planner",
    file: WORKFLOW_FILE
  },
  {
    label: "AI Video Planner",
    file: AI_VIDEO_WORKFLOW_FILE
  },
  {
    label: "FreeVisual Science",
    file: RENDER_WORKFLOW_FILE
  },
  {
    label: "ZIP Importer",
    file: IMPORT_WORKFLOW_FILE
  }
];

async function workflowRuns(env, workflowFile, limit = 10) {
  const result = await gh(
    env,
    repoPath(
      `/actions/workflows/${encodeURIComponent(workflowFile)}/runs?per_page=${limit}`
    )
  );

  return result.workflow_runs || [];
}

async function allRecentRuns(env, limit = 5) {
  const results = await Promise.all(
    TRACKED_WORKFLOWS.map(async workflow => {
      try {
        const runs = await workflowRuns(env, workflow.file, limit);

        return runs.map(run => ({
          ...run,
          workflow_label: workflow.label,
          workflow_file: workflow.file
        }));
      } catch (error) {
        return [{
          workflow_label: workflow.label,
          workflow_file: workflow.file,
          unavailable: true,
          error: error.message
        }];
      }
    })
  );

  return results
    .flat()
    .filter(run => !run.unavailable)
    .sort((a, b) =>
      new Date(b.created_at) - new Date(a.created_at)
    )
    .slice(0, limit);
}

function runStatus(run) {
  if (run.unavailable) return "Unavailable";

  if (run.status === "queued") return "Queued";
  if (run.status === "in_progress") return "Running";
  if (run.status === "waiting") return "Waiting";
  if (run.status === "completed") {
    return run.conclusion === "success"
      ? "Success"
      : run.conclusion === "cancelled"
        ? "Cancelled"
        : run.conclusion === "skipped"
          ? "Skipped"
          : "Failed";
  }

  return run.status || "Unknown";
}

function formatDate(value) {
  if (!value) return "Unknown";

  return new Date(value).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    dateStyle: "medium",
    timeStyle: "short"
  });
}

function shortRun(run) {
  return [
    `• ${run.workflow_label}`,
    `  ${runStatus(run)}`,
    `  Run #${run.id}`,
    `  ${formatDate(run.created_at)}`
  ].join("\n");
}

/* ---------------- RUNS COMMAND ---------------- */

async function showRuns(chatId, env) {
  try {
    const runs = await allRecentRuns(env, 12);

    if (!runs.length) {
      await sendTelegramMessage(
        chatId,
        "No recent workflow runs were found.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
      return;
    }

    const message = [
      "📋 RECENT WORKFLOW RUNS",
      "",
      ...runs.map(shortRun),
      "",
      "Open GitHub Actions:",
      `https://github.com/${OWNER}/${REPO}/actions`
    ].join("\n");

    await sendTelegramMessage(
      chatId,
      message.slice(0, 3900),
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not retrieve workflow runs:\n${error.message}`,
      env
    );
  }
}

/* ---------------- STATUS COMMAND ---------------- */

async function showStatus(chatId, env) {
  try {
    const runs = await allRecentRuns(env, 20);

    if (!runs.length) {
      await sendTelegramMessage(
        chatId,
        "No workflow runs are available yet.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
      return;
    }

    const latestByWorkflow = new Map();

    for (const run of runs) {
      if (!latestByWorkflow.has(run.workflow_file)) {
        latestByWorkflow.set(run.workflow_file, run);
      }
    }

    const lines = [
      "📊 STICKMAN LAB STATUS",
      "",
      ...TRACKED_WORKFLOWS.map(workflow => {
        const run = latestByWorkflow.get(workflow.file);

        return run
          ? `${workflow.label}\n${runStatus(run)} · #${run.id}\n${formatDate(run.created_at)}`
          : `${workflow.label}\nNo recent run`;
      }),
      "",
      `GitHub: https://github.com/${OWNER}/${REPO}/actions`
    ];

    await sendTelegramMessage(
      chatId,
      lines.join("\n\n").slice(0, 3900),
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Status check failed:\n${error.message}`,
      env
    );
  }
}

/* ---------------- RETRY COMMAND ---------------- */

async function retryLatestFailed(chatId, env) {
  try {
    const runs = await allRecentRuns(env, 30);

    const failed = runs.find(run =>
      run.status === "completed" &&
      run.conclusion === "failure"
    );

    if (!failed) {
      await sendTelegramMessage(
        chatId,
        "No failed workflow run was found to retry.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
      return;
    }

    await gh(
      env,
      repoPath(`/actions/runs/${failed.id}/rerun`),
      { method: "POST" }
    );

    await sendTelegramMessage(
      chatId,
      [
        "🔁 RETRY STARTED",
        "",
        `${failed.workflow_label}`,
        `Run #${failed.id}`,
        "",
        "GitHub has accepted the rerun request."
      ].join("\n"),
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Retry failed:\n${error.message}`,
      env
    );
  }
}

/* ---------------- CANCEL COMMAND ---------------- */

async function cancelActiveRun(chatId, env) {
  try {
    const runs = await allRecentRuns(env, 30);

    const active = runs.find(run =>
      ["queued", "in_progress"].includes(run.status)
    );

    if (!active) {
      await sendTelegramMessage(
        chatId,
        "There are no queued or running workflows to cancel.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
      return;
    }

    await gh(
      env,
      repoPath(`/actions/runs/${active.id}/cancel`),
      { method: "POST" }
    );

    await sendTelegramMessage(
      chatId,
      [
        "🛑 CANCELLATION REQUESTED",
        "",
        `${active.workflow_label}`,
        `Run #${active.id}`,
        "",
        "GitHub has received the cancellation request."
      ].join("\n"),
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Cancel request failed:\n${error.message}`,
      env
    );
  }
}

/* ---------------- PROMPTS COMMAND ---------------- */

async function showPrompts(chatId, env) {
  try {
    const episode = await latestEpisode(env);

    if (!episode) {
      await sendTelegramMessage(
        chatId,
        "No episode folders were found.",
        env
      );
      return;
    }

    const candidates = [
      `${episode.path}/prompts.json`,
      `${episode.path}/image-prompts.json`,
      `${episode.path}/scene-prompts.json`,
      `${episode.path}/episode.json`
    ];

    let content = "";
    let selectedFile = "";

    for (const path of candidates) {
      try {
        content = await fileText(env, path);
        if (content) {
          selectedFile = path;
          break;
        }
      } catch (error) {
        // Try the next known prompt filename.
      }
    }

    if (!content) {
      await sendTelegramMessage(
        chatId,
        [
          "No prompt file was found for the latest episode.",
          "",
          episode.path,
          "",
          "Expected one of:",
          "prompts.json",
          "image-prompts.json",
          "scene-prompts.json",
          "episode.json"
        ].join("\n"),
        env
      );
      return;
    }

    const maxLength = 3500;
    const display = content.length > maxLength
      ? content.slice(0, maxLength) + "\n\n[Output truncated]"
      : content;

    await sendTelegramMessage(
      chatId,
      [
        "📝 EPISODE PROMPTS",
        "",
        episode.path,
        `File: ${selectedFile}`,
        "",
        display
      ].join("\n").slice(0, 3900),
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not retrieve prompts:\n${error.message}`,
      env
    );
  }
}

/* ---------------- HEALTH CHECK ---------------- */

async function health(env) {
  const checks = [];

  checks.push({
    name: "Telegram token",
    ok: Boolean(env.TELEGRAM_BOT_TOKEN)
  });

  checks.push({
    name: "GitHub token",
    ok: Boolean(env.GITHUB_TOKEN)
  });

  checks.push({
    name: "Upload signing secret",
    ok: Boolean(env.UPLOAD_LINK_SECRET)
  });

  try {
    await gh(env, repoPath(""));
    checks.push({
      name: "GitHub repository",
      ok: true
    });
  } catch (error) {
    checks.push({
      name: "GitHub repository",
      ok: false,
      detail: error.message
    });
  }

  for (const workflow of TRACKED_WORKFLOWS) {
    try {
      const result = await gh(
        env,
        workflowPath(workflow.file)
      );

      checks.push({
        name: workflow.label,
        ok: result.state === "active",
        detail: result.state
      });
    } catch (error) {
      checks.push({
        name: workflow.label,
        ok: false,
        detail: error.message
      });
    }
  }

  const healthy = checks.every(check => check.ok);

  return {
    healthy,
    checks
  };
}

async function showHealth(chatId, env) {
  const result = await health(env);

  const message = [
    "🩺 STICKMAN LAB HEALTH",
    "",
    ...result.checks.map(check =>
      `${check.ok ? "✅" : "❌"} ${check.name}` +
      (check.detail ? ` — ${check.detail}` : "")
    ),
    "",
    result.healthy
      ? "All configured checks passed."
      : "One or more checks need attention."
  ].join("\n");

  await sendTelegramMessage(
    chatId,
    message.slice(0, 3900),
    env,
    { reply_markup: mainMenuKeyboard() }
  );
}

/* ---------------- HELP ---------------- */

function helpText() {
  return [
    "🧪 STICKMAN LAB CONTROL CENTRE",
    "",
    "Use the menu buttons to control your science video pipeline.",
    "",
    "MAIN MENU",
    "📅 Daily Episodes — Browse and select an episode",
    "🎬 Generate — Start a planner workflow",
    "💡 Topic — Set an exact topic or automatic mode",
    "📤 Upload Images — Create an episode ZIP upload link",
    "📊 Status — Check workflow progress",
    "📝 Prompts — View latest episode prompts",
    "📋 Runs — View recent GitHub Actions runs",
    "🩺 Health — Check bot, repository and workflows",
    "",
    "ADVANCED COMMANDS",
    "/runs — Recent workflow runs",
    "/history — Alias for /runs",
    "/retry — Retry the latest failed run",
    "/cancel — Cancel a queued or running workflow",
    "/prompts — Retrieve latest episode prompts",
    "/upload — Select episode for ZIP upload",
    "/help — Show this menu",
    "",
    "All manual workflow dispatches use the main branch."
  ].join("\n");
}

/* ---------------- GITHUB INFORMATION COMMANDS ---------------- */

async function showGitHubInfo(chatId, env) {
  try {
    const repo = await gh(env, repoPath(""));

    const message = [
      "🐙 GITHUB REPOSITORY",
      "",
      `${OWNER}/${REPO}`,
      `Default branch: ${repo.default_branch || BRANCH}`,
      `Visibility: ${repo.private ? "Private" : "Public"}`,
      "",
      `Repository: https://github.com/${OWNER}/${REPO}`,
      `Actions: https://github.com/${OWNER}/${REPO}/actions`
    ].join("\n");

    await sendTelegramMessage(
      chatId,
      message,
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `GitHub information unavailable:\n${error.message}`,
      env
    );
  }
}

async function showBranches(chatId, env) {
  try {
    const branches = await gh(
      env,
      repoPath("/branches?per_page=30")
    );

    const message = [
      "🌿 REPOSITORY BRANCHES",
      "",
      ...branches.map(branch =>
        `${branch.name === BRANCH ? "⭐ " : "• "}${branch.name}`
      )
    ].join("\n");

    await sendTelegramMessage(
      chatId,
      message.slice(0, 3900),
      env
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not retrieve branches:\n${error.message}`,
      env
    );
  }
}

async function showCommits(chatId, env) {
  try {
    const commits = await gh(
      env,
      repoPath(`/commits?sha=${BRANCH}&per_page=8`)
    );

    const message = [
      "🧾 RECENT COMMITS",
      "",
      ...commits.map(commit => {
        const title =
          commit.commit?.message?.split("\n")[0] || "No message";

        return [
          `• ${title}`,
          `  ${commit.sha.slice(0, 8)}`,
          `  ${formatDate(commit.commit?.author?.date)}`
        ].join("\n");
      })
    ].join("\n");

    await sendTelegramMessage(
      chatId,
      message.slice(0, 3900),
      env
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not retrieve commits:\n${error.message}`,
      env
    );
  }
}

/* ---------------- WORKFLOW INFORMATION ---------------- */

async function showWorkflow(chatId, env) {
  const lines = ["⚙️ CONFIGURED WORKFLOWS", ""];

  for (const workflow of TRACKED_WORKFLOWS) {
    try {
      const result = await gh(
        env,
        workflowPath(workflow.file)
      );

      lines.push(
        `${workflow.label}\n${workflow.file}\nState: ${result.state}`
      );
    } catch (error) {
      lines.push(
        `${workflow.label}\n${workflow.file}\nUnavailable: ${error.message}`
      );
    }

    lines.push("");
  }

  await sendTelegramMessage(
    chatId,
    lines.join("\n").slice(0, 3900),
    env,
    { reply_markup: mainMenuKeyboard() }
  );
}

/* ---------------- LAST SUCCESS / FAILURE ---------------- */

async function showLastResult(chatId, env, desiredConclusion) {
  try {
    const runs = await allRecentRuns(env, 50);

    const match = runs.find(run =>
      run.status === "completed" &&
      run.conclusion === desiredConclusion
    );

    if (!match) {
      await sendTelegramMessage(
        chatId,
        `No completed workflow with conclusion "${desiredConclusion}" was found.`,
        env
      );
      return;
    }

    await sendTelegramMessage(
      chatId,
      [
        desiredConclusion === "success"
          ? "✅ LAST SUCCESSFUL RUN"
          : "❌ LAST FAILED RUN",
        "",
        match.workflow_label,
        `Run #${match.id}`,
        `Created: ${formatDate(match.created_at)}`,
        `Finished: ${formatDate(match.updated_at)}`,
        "",
        match.html_url || ""
      ].join("\n"),
      env
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not retrieve workflow result:\n${error.message}`,
      env
    );
  }
}

/* ---------------- SYNC STATUS ---------------- */

async function showSyncStatus(chatId, env) {
  try {
    const repo = await gh(env, repoPath(""));

    const message = [
      "🔄 REPOSITORY SYNC STATUS",
      "",
      `Repository: ${OWNER}/${REPO}`,
      `Default branch: ${repo.default_branch || BRANCH}`,
      `Last updated: ${formatDate(repo.updated_at)}`,
      `Pushed at: ${formatDate(repo.pushed_at)}`,
      "",
      `Latest commit: https://github.com/${OWNER}/${REPO}/commits/${BRANCH}`
    ].join("\n");

    await sendTelegramMessage(
      chatId,
      message,
      env
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not retrieve sync status:\n${error.message}`,
      env
    );
  }
}

/* ---------------- LATEST EPISODE COMMANDS ---------------- */

async function showLatestEpisode(chatId, env) {
  try {
    const episode = await latestEpisode(env);

    if (!episode) {
      await sendTelegramMessage(
        chatId,
        "No episodes were found.",
        env
      );
      return;
    }

    await sendTelegramMessage(
      chatId,
      [
        "📅 LATEST EPISODE",
        "",
        episode.date,
        episode.name,
        episode.path,
        "",
        "Use Daily Episodes to browse and select another episode."
      ].join("\n"),
      env,
      { reply_markup: mainMenuKeyboard() }
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not retrieve the latest episode:\n${error.message}`,
      env
    );
  }
}

async function showEpisodeFiles(chatId, env) {
  try {
    const episode = await latestEpisode(env);

    if (!episode) {
      await sendTelegramMessage(chatId, "No episodes found.", env);
      return;
    }

    const files = await gh(
      env,
      repoPath(`/contents/${episode.path}?ref=${BRANCH}`)
    );

    const message = [
      "📂 LATEST EPISODE FILES",
      "",
      episode.path,
      "",
      ...files.map(file =>
        `${file.type === "dir" ? "📁" : "📄"} ${file.name}`
      )
    ].join("\n");

    await sendTelegramMessage(
      chatId,
      message.slice(0, 3900),
      env
    );
  } catch (error) {
    await sendTelegramMessage(
      chatId,
      `Could not list episode files:\n${error.message}`,
      env
    );
  }
}

/* ---------------- COMMAND ROUTER ---------------- */

async function handleCommand(chatId, text, env) {
  const command = text.trim().split(/\s+/)[0].toLowerCase();

  switch (command) {
    case "/start":
    case "/menu":
    case "/help":
      await sendTelegramMessage(
        chatId,
        helpText(),
        env,
        { reply_markup: mainMenuKeyboard() }
      );
      return;

    case "/generate":
    case "/generate_now":
      await generate(chatId, env);
      return;

    case "/episodes":
      await sendEpisodeKeyboard(chatId, env);
      return;

    case "/upload":
    case "/upload_images":
      await sendUploadEpisodeKeyboard(chatId, env);
      return;

    case "/status":
      await showStatus(chatId, env);
      return;

    case "/latest":
    case "/episode_latest":
      await showLatestEpisode(chatId, env);
      return;

    case "/history":
    case "/runs":
      await showRuns(chatId, env);
      return;

    case "/retry":
      await retryLatestFailed(chatId, env);
      return;

    case "/cancel":
      await cancelActiveRun(chatId, env);
      return;

    case "/prompts":
      await showPrompts(chatId, env);
      return;

    case "/episode_files":
      await showEpisodeFiles(chatId, env);
      return;

    case "/github":
      await showGitHubInfo(chatId, env);
      return;

    case "/branches":
      await showBranches(chatId, env);
      return;

    case "/commits":
      await showCommits(chatId, env);
      return;

    case "/workflow":
      await showWorkflow(chatId, env);
      return;

    case "/health":
      await showHealth(chatId, env);
      return;

    case "/last_success":
      await showLastResult(chatId, env, "success");
      return;

    case "/last_failure":
      await showLastResult(chatId, env, "failure");
      return;

    case "/sync_status":
    case "/sync_history":
      await showSyncStatus(chatId, env);
      return;

    default:
      await sendTelegramMessage(
        chatId,
        "I didn't recognise that command. Use /help to open the control centre.",
        env,
        { reply_markup: mainMenuKeyboard() }
      );
  }
}