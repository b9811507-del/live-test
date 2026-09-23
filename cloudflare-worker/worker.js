/**
 * Cloudflare Worker — v12 SIMPLE (FREE forever)
 * - GET /t, GET /  status from GitHub state.json
 * - POST /ph/<ADMIN_KEY>  Telegram PAID bot webhook (instant)
 * - POST /rzp-webhook  Razorpay webhook
 * - scheduled every 2 min: dispatch slot-chain.yml (MAIN) — prevents gap, ensures IARI 14:30 / AFO 18:00 on time
 *
 * v12 SIMPLE flow: announce exact time → timer 15s countdown (separate msg) → polls 25s gap 0.5s → LB → top3 → file → tomorrow → paid LAST
 * LATE_MAX 5 min hard (max 3-5 min late)
 */

const GITHUB_RAW = "https://raw.githubusercontent.com/b9811507-del/live-test/main/state.json";
const ADMIN_KEY_FALLBACK = "4574ea9aab7e913d4ea9ff1270d89eda";
const SECRET_FALLBACK = "odCqUofKvydqYgfJkFzGTwYwTAAm4ZCP";
const RZP_WEBHOOK_SECRET_FALLBACK = "rzp_whsec_agriquiz_2026_11cf";

const BATCHES = [
  { key: "iari", emoji: "📘", title: "IARI BOOK MCQ BATCH", price: "₹99", chat: "-1003922097468", perks: "Complete IARI book (1074 pages) chapter-wise MCQs · daily 5-page test series · answer keys · unlimited attempts" },
  { key: "malwa", emoji: "📚", title: "MALWA BOOK VOL 1+2+HORTICULTURE", price: "₹151", chat: "-1003761821341", perks: "Malwa Vol-1, Vol-2 and Horticulture books' full MCQ practice · daily 20-question tests · PDF notes" },
  { key: "nemraj", emoji: "🌾", title: "NEMRAJ SUNDA BOOK BATCH", price: "₹99", chat: "-1003853396327", perks: "Nemraj Sunda book MCQs · topic-wise practice · full-length mock papers" },
  { key: "rksharma", emoji: "📗", title: "RK SHARMA BOOK BATCH", price: "₹99", chat: "-1003880198347", perks: "R.K. Sharma book MCQs · subject-wise practice · revision notes" },
  { key: "afo", emoji: "🌆", title: "AFO SELECTION BATCH", price: "₹251", chat: "-1003687531473", perks: "AFO mains full-length tests (new pattern) · previous-year papers · selection-focused practice" },
  { key: "cane", emoji: "🎋", title: "SUGARCANE PREMIUM BATCH", price: "₹151", chat: "-1003707610763", perks: "Sugarcane premium classes · daily tests · revision notes" },
  { key: "pashu", emoji: "🐄", title: "PASHUDHAN ADHIKARI BATCH", price: "₹151", chat: "-1003947957354", perks: "Pashudhan Adhikari syllabus classes · daily MCQ tests · structured notes" },
];

function batchByKey(k) { return BATCHES.find(b => b.key === k); }
function priceAmount(price) { const digits = (price || "").replace(/\D/g, ""); return digits ? parseInt(digits) : 0; }

async function tg(token, method, body) {
  const url = `https://api.telegram.org/bot${token}/${method}`;
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await res.json().catch(() => ({}));
  if (!j.ok) console.log(`tg ${method} fail: ${j.description?.slice(0,200)}`);
  return j.ok ? j.result : null;
}

async function rzpCreateLink(env, batchKey, title, amount, uid, name) {
  const keyId = env.RAZORPAY_KEY_ID; const keySec = env.RAZORPAY_KEY_SECRET;
  if (!keyId || !keySec) { console.log("RZP keys missing"); return null; }
  const auth = btoa(`${keyId}:${keySec}`);
  const body = {
    amount: Math.round(amount * 100), currency: "INR", accept_partial: false,
    description: title.slice(0, 255),
    customer: { name: (name || "Student").slice(0, 60) },
    notify: { sms: false, email: false }, reminder_enable: false,
    notes: { batch: batchKey, uid: String(uid), system: "agri-quiz-v12-simple" },
    expire_by: Math.floor(Date.now() / 1000) + 24 * 3600,
    callback_url: `https://t.me/AgriquizWorld_bot?start=paid_${batchKey}`, callback_method: "get"
  };
  console.log(`RZP creating link for ${batchKey}/${uid} amount ${amount}`);
  const res = await fetch("https://api.razorpay.com/v1/payment_links", { method: "POST", headers: { "Authorization": `Basic ${auth}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await res.json().catch(() => ({}));
  if (j.id) console.log(`RZP link created ${j.id} ${j.short_url}`); else console.log(`RZP link fail ${JSON.stringify(j).slice(0,300)}`);
  return j.id ? j : null;
}

async function createInviteAndSend(env, batchKey, uid) {
  const b = batchByKey(batchKey); const token = env.PAID_BOT_TOKEN;
  if (!b || !token) return null;
  const invite = await tg(token, "createChatInviteLink", { chat_id: b.chat, member_limit: 1, creates_join_request: false, name: `${batchKey}-${String(uid).slice(-6)}` });
  const link = invite?.invite_link;
  if (!link) { console.log(`Invite link fail for ${batchKey} chat ${b.chat}`); return null; }
  const text = `✅ <b>Payment verified!</b> — ${b.title}\n\n🎉 Aapka payment confirm ho gaya!\n\n👉 Join link (one-time, 1 user only):\n${link}\n\n⏰ Ye link sirf ek baar kaam karega, jaldi join kar lo!\n\n<b>Ek payment = ek link</b> ✅`;
  await tg(token, "sendMessage", { chat_id: String(uid), text, parse_mode: "HTML", disable_web_page_preview: true });
  return link;
}

async function sendMessage(env, uid, text, keyboard=null) {
  const token = env.PAID_BOT_TOKEN; if (!token) return null;
  return tg(token, "sendMessage", { chat_id: String(uid), text, parse_mode: "HTML", disable_web_page_preview: true, reply_markup: keyboard });
}

async function sendCatalog(env, uid, greeting=true) {
  const token = env.PAID_BOT_TOKEN; if (!token) return;
  const intro = greeting
    ? `👋 <b>AGRI QUIZ WORLD — Paid Batches</b>\n\nHar batch me: ♾️ <b>Unlimited attempts</b> · ⏳ <b>Lifetime validity</b> · pay once, yours for life.\nNeeche apne batch ke button — <b>Pay & Join</b> — dabaiye; turant aapka personal Razorpay link khulega, payment verify hote hi <b>one-time join link</b> yahin aayega.`
    : `Pick your batch — tap <b>Pay & Join</b> below it:`;
  await sendMessage(env, uid, intro);
  for (const b of BATCHES) {
    const amt = priceAmount(b.price);
    const body = `${b.emoji} <b>${b.title}</b>\n\nFee: <b>${b.price}</b>\n♾️ Unlimited attempts · ⏳ Lifetime validity · instant join after payment\n\n${b.perks}`;
    const cb = amt ? `rzp:${b.key}` : `batch:${b.key}`;
    const kb = { inline_keyboard: [[{ text: `💳 Pay & Join — ${b.price}`, callback_data: cb }]] };
    await sendMessage(env, uid, body, kb);
  }
  await sendMessage(env, uid, `❓ Koi sawal ho to yahin reply kariye — team ek message door hai. Apne batches dekhne ke liye: /mybatches`);
}

async function sendBatchDetail(env, uid, key) {
  const b = batchByKey(key);
  if (!b) return sendMessage(env, uid, `This batch is not open right now — tap a batch from /start to see what's available.`);
  const body = `${b.emoji} <b>${b.title}</b>\n\nFee: <b>${b.price}</b> · ♾️ <b>Unlimited attempts</b> · ⏳ <b>Lifetime validity</b>\n\n${b.perks}\n\n👉 Tap <b>Pay & Join</b> — you get a personal Razorpay link instantly; the moment payment is verified your one-time join link arrives in this chat.`;
  const amt = priceAmount(b.price);
  const rows = [];
  if (amt) rows.push([{ text: `💳 Pay & Join — ${b.price}`, callback_data: `rzp:${key}` }]);
  else rows.push([{ text: `ℹ️ View details`, callback_data: `batch:${key}` }]);
  return sendMessage(env, uid, body, { inline_keyboard: rows });
}

async function sendMyBatches(env, uid) {
  try {
    const raw = await fetch(GITHUB_RAW + "?t=" + Date.now()).then(r => r.text());
    const st = JSON.parse(raw);
    const users = (st.paid?.users) || {};
    const urec = users[String(uid)] || {};
    const batches = urec.batches || {};
    const links = st.paid?.links || {};
    const openLinks = Object.entries(links).filter(([lid, r]) => String(r.uid) === String(uid) && !["paid","expired","cancelled"].includes(r.status));
    if (Object.keys(batches).length === 0 && openLinks.length === 0) {
      return sendMessage(env, uid, `📭 Aapke paas abhi koi paid batch nahi hai.\n\n/start dabakar batches dekho.`);
    }
    let txt = "";
    if (openLinks.length > 0) {
      const [lid, r] = openLinks[openLinks.length-1];
      txt += `⏳ Pending payment for <b>${r.title}</b> — ${r.short_url || ""}\n\n`;
    }
    if (Object.keys(batches).length > 0) {
      txt += `<b>Aapke batches:</b>\n`;
      const kbRows = [];
      for (const [k, rec] of Object.entries(batches)) {
        const b = batchByKey(k) || { title: k.toUpperCase() };
        txt += `• <b>${b.title}</b> — ${String(rec.at||"").slice(0,10)}\n`;
        kbRows.push([{ text: `🔁 Re-join ${b.title.slice(0,30)}`, callback_data: `reissue:${k}` }]);
      }
      return sendMessage(env, uid, txt, { inline_keyboard: kbRows });
    } else return sendMessage(env, uid, txt || "No batches found");
  } catch (e) {
    console.log("mybatches err", e.message);
    return sendMessage(env, uid, `⚠️ /mybatches check me dikkat, thodi der baad try karo.`);
  }
}

async function handlePaidMessage(env, msg) {
  const chat = msg.chat || {};
  if (chat.type !== "private") return;
  const uid = String(chat.id);
  const text = (msg.text || "").trim();
  const low = text.toLowerCase();
  const fromName = (msg.from?.first_name || "").slice(0,32);
  if (msg.successful_payment) {
    const payload = msg.successful_payment.invoice_payload || "";
    const parts = payload.split(":");
    const key = parts.length > 2 && parts[0] === "batch" ? parts[1] : null;
    if (key) await createInviteAndSend(env, key, uid);
    return;
  }
  if (low.startsWith("/start")) {
    const payload = text.slice(6).trim().toLowerCase();
    console.log(`/start payload: ${payload} from ${uid}`);
    if (payload.startsWith("paid_")) {
      const key = payload.replace("paid_", "").split(/[^a-z]/)[0];
      await sendBatchDetail(env, uid, key);
      try {
        const repo = env.GITHUB_REPO || "b9811507-del/live-test"; const ghToken = env.GITHUB_TOKEN;
        if (ghToken) await fetch(`https://api.github.com/repos/${repo}/actions/workflows/slot-chain.yml/dispatches`, { method: "POST", headers: { "Authorization": `Bearer ${ghToken}`, "Accept": "application/vnd.github+json", "Content-Type": "application/json" }, body: JSON.stringify({ ref: "main" }) });
      } catch {}
      return;
    }
    if (payload.startsWith("buy_")) { const key = payload.replace("buy_", "").split(/[^a-z]/)[0]; return sendBatchDetail(env, uid, key); }
    if (BATCHES.some(b => b.key === payload)) return sendBatchDetail(env, uid, payload);
    if (payload === "catalog" || payload === "" || payload === "start") return sendCatalog(env, uid, true);
    return sendCatalog(env, uid, true);
  }
  if (low.startsWith("/mybatches") || low.startsWith("/my") || low === "mybatches") return sendMyBatches(env, uid);
  if (low.startsWith("/help")) return sendMessage(env, uid, `🆘 <b>Help — Paid Batches</b>\n\n/start — saare batches dekho\n/mybatches — aapke kharide hue batches\n\nKisi batch ka <b>Pay & Join</b> dabao → personal Razorpay link milega → pay karte hi join link yahin aa jayega (instant).\n\nSawal ho to yahin likh do.`);
  return sendCatalog(env, uid, false);
}

async function handlePaidCallback(env, cb) {
  const token = env.PAID_BOT_TOKEN; if (!token) return;
  const data = cb.data || ""; const uid = cb.from?.id; const fromName = (cb.from?.first_name || "").slice(0,32); const msg = cb.message || {}; const isPrivate = (msg.chat || {}).type === "private";
  await tg(token, "answerCallbackQuery", { callback_query_id: cb.id, text: "" }).catch(()=>{});
  let batchKey = null;
  if (data.startsWith("batch:")) batchKey = data.split(":")[1];
  else if (data.startsWith("rzp:")) batchKey = data.split(":")[1];
  else if (data.startsWith("invoice:")) batchKey = data.split(":")[1];
  else if (data.startsWith("reissue:")) batchKey = data.split(":")[1];
  else if (data === "catalog") { await sendCatalog(env, uid, false); return; }
  if (!batchKey) return;
  const b = batchByKey(batchKey); if (!b) return;
  if (data.startsWith("reissue:")) {
    try {
      const raw = await fetch(GITHUB_RAW + "?t=" + Date.now()).then(r => r.text());
      const st = JSON.parse(raw);
      const urec = (st.paid?.users?.[String(uid)]?.batches?.[batchKey]);
      if (urec) await createInviteAndSend(env, batchKey, uid);
      else await sendMessage(env, uid, `ℹ️ Aapke paas <b>${b.title}</b> ka access nahi mila. Pehle pay karo.`, { inline_keyboard: [[{ text: `💳 Pay ${b.price} now`, callback_data: `rzp:${batchKey}` }]] });
    } catch (e) { console.log("reissue err", e.message); }
    return;
  }
  if (data.startsWith("batch:")) {
    if (isPrivate) await sendBatchDetail(env, uid, batchKey);
    else await tg(token, "answerCallbackQuery", { callback_query_id: cb.id, url: `https://t.me/AgriquizWorld_bot?start=buy_${batchKey}` }).catch(()=>{});
    return;
  }
  if (data.startsWith("rzp:") || data.startsWith("invoice:")) {
    if (!isPrivate) { await tg(token, "answerCallbackQuery", { callback_query_id: cb.id, url: `https://t.me/AgriquizWorld_bot?start=buy_${batchKey}` }).catch(()=>{}); return; }
    const amt = priceAmount(b.price);
    if (amt <= 0) { await sendMessage(env, uid, `⚠️ ${b.title} ka price set nahi hai, admin se contact karo.`); return; }
    const link = await rzpCreateLink(env, batchKey, b.title, amt, uid, fromName);
    if (link && link.short_url) {
      const text = `💳 <b>${b.title}</b> — ${b.price}\n\n${b.emoji} ${b.title}\n\n👉 <b>Pay & Join</b> ke liye neeche link dabao. Payment verify hote hi join link yahin aayega (instant).\n\n<b>Ek payment = ek link</b> (hard rule)\n\n⏳ Link 24 ghante ke liye valid hai.`;
      await sendMessage(env, uid, text, { inline_keyboard: [[{ text: `💳 Pay ${b.price} now`, url: link.short_url }]] });
    } else await sendMessage(env, uid, `⚠️ Payment link banane me dikkat, dobara try karo. Batch: ${b.title}\n\nAgar baar-baar fail ho to /help me message karo.`);
    return;
  }
}

async function handlePaidUpdate(env, update) {
  try {
    if (update.message) await handlePaidMessage(env, update.message);
    else if (update.callback_query) await handlePaidCallback(env, update.callback_query);
    else if (update.chat_join_request) console.log("join_request", update.chat_join_request.chat?.id, update.chat_join_request.from?.id);
  } catch (e) { console.log("handlePaidUpdate err", e.message, e.stack?.slice(0,300)); }
}

async function verifyRzpSignature(secret, payload, signature) {
  try {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const sigBuf = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
    const expected = Array.from(new Uint8Array(sigBuf)).map(b => b.toString(16).padStart(2, "0")).join("");
    return expected === signature;
  } catch { return false; }
}

async function handleRzpWebhook(env, request) {
  const secret = env.RZP_WEBHOOK_SECRET || RZP_WEBHOOK_SECRET_FALLBACK;
  const signature = request.headers.get("X-Razorpay-Signature") || "";
  const rawBody = await request.text();
  if (secret && signature) {
    const ok = await verifyRzpSignature(secret, rawBody, signature);
    if (!ok) { console.log("RZP webhook bad signature"); return new Response("bad signature\n", { status: 401 }); }
  }
  let event; try { event = JSON.parse(rawBody); } catch { return new Response("bad json\n", { status: 400 }); }
  const ev = event.event || ""; console.log("RZP webhook event", ev);
  if (ev === "payment_link.paid" || ev === "payment_link.partially_paid") {
    const pl = event.payload?.payment_link?.entity || event.payload?.entity || {};
    const linkId = pl.id || ""; const notes = pl.notes || {}; const batchKey = notes.batch || ""; const uid = notes.uid || ""; const status = pl.status || "";
    console.log(`RZP paid: ${linkId} batch=${batchKey} uid=${uid} status=${status}`);
    if (batchKey && uid && status === "paid") {
      const joinLink = await createInviteAndSend(env, batchKey, uid);
      console.log(`RZP instant join link issued for ${batchKey}/${uid}: ${joinLink ? "ok" : "fail"}`);
      try {
        const repo = env.GITHUB_REPO || "b9811507-del/live-test"; const ghToken = env.GITHUB_TOKEN;
        if (ghToken) await fetch(`https://api.github.com/repos/${repo}/actions/workflows/slot-chain.yml/dispatches`, { method: "POST", headers: { "Authorization": `Bearer ${ghToken}`, "Accept": "application/vnd.github+json", "Content-Type": "application/json" }, body: JSON.stringify({ ref: "main" }) });
      } catch {}
    }
  }
  return new Response("ok\n");
}

async function handleRequest(request, env, ctx) {
  const url = new URL(request.url);
  const path = url.pathname;

  if (request.method === "GET" && (path === "/t" || path === "/tiny")) {
    try {
      const raw = await fetch(GITHUB_RAW + "?t=" + Date.now()).then(r => r.text());
      const st = JSON.parse(raw);
      const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
      const now = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
      const slots = [{ label: "malwa", h: 11, m: 0 }, { label: "iari", h: 14, m: 30 }, { label: "afo", h: 18, m: 0 }];
      let next = ""; let minM = 9999;
      for (const s of slots) {
        let t = new Date(now); t.setHours(s.h, s.m, 0, 0);
        if (t < now) t.setDate(t.getDate() + 1);
        const diff = Math.floor((t - now) / 60000);
        if (diff < minM) { minM = diff; next = `${s.label}+${diff}m`; }
      }
      // v12 simple status
      const line = `ok cf-worker-v12-simple next=${next} today=${today} days=${Object.keys(st.days||{}).length} poll=25s gap=0.5s timer=15s late_max=5m paid_LAST=on chain=60s cron=5m+2m precheck=25m v12\n`;
      return new Response(line, { headers: { "Content-Type": "text/plain" } });
    } catch (e) {
      return new Response(`ok cf-worker err=${e.message.slice(0,60)}\n`, { headers: { "Content-Type": "text/plain" } });
    }
  }

  if (request.method === "GET" && (path === "/" || path === "/status")) {
    try {
      const raw = await fetch(GITHUB_RAW + "?t=" + Date.now()).then(r => r.text());
      const st = JSON.parse(raw);
      const out = {
        worker: "cloudflare-free-v12-simple",
        now_ist: new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }),
        flow: "announce exact → timer 15s countdown (separate msg) → polls 25s gap 0.5s → LB → top3 → file → tomorrow → paid LAST",
        timing: { poll_seconds: 25, gap_seconds: 0.5, countdown_seconds: 15, late_max_min: 5, defer_secs: 0, announce_lead: 0 },
        days: Object.keys(st.days || {}).slice(-3),
        chain: "slot-chain every 60s + cron 5m + Worker dispatch every 2m, re-arm 180 min pre-slot",
        webhooks: {
          telegram_paid: "https://live-test-free.upsssc360.workers.dev/ph/" + (env.ADMIN_KEY || ADMIN_KEY_FALLBACK),
          razorpay: "https://live-test-free.upsssc360.workers.dev/rzp-webhook"
        },
        speed: "Telegram 0-1s (waitUntil), Razorpay instant",
        batches: BATCHES.map(b=>b.key),
        paid_last: "mandatory after every test (user order v12)"
      };
      return new Response(JSON.stringify(out, null, 2), { headers: { "Content-Type": "application/json" } });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), { headers: { "Content-Type": "application/json" } });
    }
  }

  if (request.method === "POST" && path.startsWith("/ph/")) {
    const key = path.split("/ph/")[1]?.split("/")[0];
    const expectedKey = env.ADMIN_KEY || ADMIN_KEY_FALLBACK;
    if (key !== expectedKey) return new Response("denied\n", { status: 403 });
    const expectedSecret = env.PAID_WEBHOOK_SECRET || SECRET_FALLBACK;
    const gotSecret = request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
    if (expectedSecret && gotSecret && gotSecret !== expectedSecret) return new Response("bad secret\n", { status: 401 });
    let update;
    try { update = await request.json(); if (!update || typeof update.update_id === "undefined") throw new Error("bad shape"); } catch { return new Response("bad update\n", { status: 400 }); }
    if (ctx && ctx.waitUntil) ctx.waitUntil(handlePaidUpdate(env, update));
    else handlePaidUpdate(env, update).catch(() => {});
    return new Response("ok\n");
  }

  if (request.method === "GET" && (path === "/verify" || path === "/health")) {
    const checks = [];
    checks.push({ name: "worker", ok: true, msg: "alive v12-simple" });
    checks.push({ name: "flow", ok: true, msg: "announce→timer 15s separate→polls 25s 0.5s→LB→paid LAST" });
    checks.push({ name: "late_max", ok: true, msg: "5 min hard (user order max 3-5 min)" });
    for (const b of BATCHES) {
      const hasChat = !!b.chat; const hasPrice = !!b.price;
      checks.push({ name: `batch:${b.key}`, ok: hasChat && hasPrice, msg: `chat=${b.chat.slice(0,6)}... price=${b.price} ${hasChat && hasPrice ? "OK" : "MISSING"}` });
    }
    checks.push({ name: "env:PAID_BOT_TOKEN", ok: !!env.PAID_BOT_TOKEN, msg: env.PAID_BOT_TOKEN ? "set" : "missing" });
    checks.push({ name: "env:RAZORPAY", ok: !!(env.RAZORPAY_KEY_ID && env.RAZORPAY_KEY_SECRET), msg: env.RAZORPAY_KEY_ID ? "keys set" : "missing" });
    checks.push({ name: "env:GITHUB_TOKEN", ok: !!env.GITHUB_TOKEN, msg: env.GITHUB_TOKEN ? "set" : "missing" });
    checks.push({ name: "env:ADMIN_KEY", ok: !!env.ADMIN_KEY, msg: "set" });
    const allOk = checks.every(c => c.ok);
    return new Response(JSON.stringify({ ok: allOk, checks, now_ist: new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }), next: "malwa 11:00, iari 14:30, afo 18:00", worker: "v12-simple precheck 25m chain 60s paid LAST" }, null, 2), { headers: { "Content-Type": "application/json" } });
  }

  if (request.method === "POST" && (path === "/rzp-webhook" || path === "/rzp" || path === "/razorpay")) {
    return handleRzpWebhook(env, request);
  }

  return new Response("not found\n", { status: 404 });
}

export default {
  async fetch(request, env, ctx) { return handleRequest(request, env, ctx); },
  async scheduled(event, env, ctx) {
    console.log("cron tick v12-simple", new Date().toISOString(), "dispatching slot-chain.yml");
    try {
      const repo = env.GITHUB_REPO || "b9811507-del/live-test";
      const token = env.GITHUB_TOKEN;
      if (token) {
        // v12 SIMPLE: only dispatch slot-chain.yml (main dispatcher) — not keepwarm-agent
        const res = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/slot-chain.yml/dispatches`, {
          method: "POST",
          headers: { "Authorization": `Bearer ${token}`, "Accept": "application/vnd.github+json", "Content-Type": "application/json" },
          body: JSON.stringify({ ref: "main" })
        });
        console.log("dispatch slot-chain status", res.status);
      } else console.log("no GITHUB_TOKEN in env");
    } catch (e) { console.log("scheduled err", e.message); }
  }
}
