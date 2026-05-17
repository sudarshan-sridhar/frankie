"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const modePill = $("#mode-indicator");
const activeModePill = $("#active-mode-pill");
const estopPill = $("#estop-pill");
const statusEl = $("#status");
const cameraCanvas = $("#camera");
const cameraCtx = cameraCanvas.getContext("2d");
const zInput = $("#z-mm");
const clickAction = $("#click-action");
const describeBtn = $("#describe");
const describePrompt = $("#describe-prompt");

const JOINTS = ["base", "shoulder", "elbow", "wrist"];
const MODE_TABS = ["free", "defect", "toolship", "chess"];
const DEBOUNCE_MS = 100;

let frameWidth = 1280;
let frameHeight = 720;
let activeMode = null;

const debounceTimers = new Map();
function debounce(key, fn, ms = DEBOUNCE_MS) {
  clearTimeout(debounceTimers.get(key));
  debounceTimers.set(key, setTimeout(fn, ms));
}

async function api(path, opts = {}) {
  try {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    if (!res.ok) {
      const text = await res.text();
      logStatus(`ERR ${res.status} ${path}: ${text}`);
      return null;
    }
    return await res.json();
  } catch (e) {
    logStatus(`fetch failed ${path}: ${e}`);
    return null;
  }
}

function logStatus(line) {
  const ts = new Date().toLocaleTimeString();
  statusEl.textContent = `[${ts}] ${line}\n${statusEl.textContent}`.slice(0, 4000);
}

function paintState(payload) {
  if (!payload) return;
  modePill.textContent = (payload.mode || "?").toUpperCase();
  modePill.dataset.mode = payload.mode || "";
  const arm = payload.arm || {};
  const estopped = !!arm.estopped;
  estopPill.textContent = estopped ? "E-STOPPED" : "READY";
  estopPill.dataset.mode = estopped ? "estopped" : "ready";

  for (const j of JOINTS) {
    const js = arm.joints && arm.joints[j];
    const out = document.getElementById(`readout-${j}`);
    if (js && out) out.textContent = `${js.angle_deg.toFixed(0)}° · ${js.pulse_us}us`;
  }
  const grip = document.getElementById("readout-gripper");
  if (grip && typeof arm.gripper_ratio === "number") {
    grip.textContent = `${Math.round(arm.gripper_ratio * 100)}%`;
  }
}

function setActiveModePill(name) {
  activeMode = name;
  if (name) {
    activeModePill.textContent = name;
    activeModePill.dataset.mode = "ready";
  } else {
    activeModePill.textContent = "no mode";
    activeModePill.dataset.mode = "";
  }
}

// ---- joint sliders + gripper + home (Manual tab) ----------------------------

JOINTS.forEach((joint) => {
  const slider = document.querySelector(`input[data-joint="${joint}"]`);
  if (!slider) return;
  slider.addEventListener("input", () => {
    debounce(`jog:${joint}`, async () => {
      const angle = parseFloat(slider.value);
      const res = await api("/api/jog", {
        method: "POST",
        body: JSON.stringify({ joint, angle_deg: angle }),
      });
      if (res) {
        logStatus(`jog ${joint} -> ${angle}°`);
        paintState(res);
      }
    });
  });
});

document.getElementById("grip-slider").addEventListener("input", (e) => {
  debounce("grip", async () => {
    const ratio = parseFloat(e.target.value) / 100;
    const res = await api("/api/gripper/set", {
      method: "POST",
      body: JSON.stringify({ ratio }),
    });
    if (res) { logStatus(`grip ${(ratio * 100).toFixed(0)}%`); paintState(res); }
  });
});

document.getElementById("grip-open").addEventListener("click", async () => {
  const res = await api("/api/gripper/open", { method: "POST" });
  if (res) { logStatus("gripper open"); paintState(res); document.getElementById("grip-slider").value = 0; }
});
document.getElementById("grip-close").addEventListener("click", async () => {
  const res = await api("/api/gripper/close", { method: "POST" });
  if (res) { logStatus("gripper close"); paintState(res); document.getElementById("grip-slider").value = 100; }
});
document.getElementById("home").addEventListener("click", async () => {
  const res = await api("/api/home", { method: "POST" });
  if (res) {
    logStatus("home");
    paintState(res);
    JOINTS.forEach((j) => {
      const s = document.querySelector(`input[data-joint="${j}"]`);
      if (s) s.value = 0;
    });
    document.getElementById("grip-slider").value = 0;
  }
});
document.getElementById("estop").addEventListener("click", async () => {
  const res = await api("/api/estop", { method: "POST" });
  if (res) { logStatus("E-STOP"); paintState(res); }
});
document.getElementById("clear-estop").addEventListener("click", async () => {
  const res = await api("/api/clear_estop", { method: "POST" });
  if (res) { logStatus("estop cleared"); paintState(res); }
});

// ---- camera click handler ---------------------------------------------------

cameraCanvas.addEventListener("click", async (e) => {
  const rect = cameraCanvas.getBoundingClientRect();
  const px = (e.clientX - rect.left) * (frameWidth / rect.width);
  const py = (e.clientY - rect.top) * (frameHeight / rect.height);
  const action = clickAction.value;
  if (action === "move") {
    const z = parseFloat(zInput.value) || 60;
    logStatus(`click move @ px=(${px.toFixed(0)}, ${py.toFixed(0)}) z=${z}`);
    const res = await api("/api/move_to_pixel", {
      method: "POST",
      body: JSON.stringify({ px: [px, py], z_mm: z }),
    });
    if (res) {
      logStatus(`-> world=${JSON.stringify(res.target_world_mm)}`);
      paintState({ mode: res.mode, arm: res.arm });
    }
  } else {
    logStatus(`click inspect @ px=(${px.toFixed(0)}, ${py.toFixed(0)})`);
    const prompt = describePrompt.value || "Describe the object I am pointing at in this image.";
    const res = await api("/api/vision/describe", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    });
    if (res) logStatus(`vision: ${res.text}`);
  }
});

describeBtn.addEventListener("click", async () => {
  const prompt = describePrompt.value || "Describe what you see in this image in one sentence.";
  logStatus(`vision describe: ${prompt}`);
  const res = await api("/api/vision/describe", {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
  if (res) logStatus(`-> ${res.text}`);
});

// ---- tabs -------------------------------------------------------------------

async function activateMode(name) {
  if (name === activeMode) return true;
  const res = await api(`/api/mode/${name}`, { method: "POST" });
  if (res) {
    setActiveModePill(name);
    logStatus(`mode -> ${name}`);
    return true;
  }
  return false;
}

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", async () => {
    const name = tab.dataset.tab;
    $$(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    $$(".tab-pane").forEach((p) => {
      p.classList.toggle("hidden", p.dataset.pane !== name);
    });
    if (MODE_TABS.includes(name)) {
      await activateMode(name);
    }
  });
});

// ---- voice + command --------------------------------------------------------

function setOutput(mode, payload) {
  const out = document.querySelector(`.cmd-output[data-mode="${mode}"]`);
  if (out) out.textContent = JSON.stringify(payload, null, 2);
}

// Web Speech TTS. On Chrome the voices list often loads asynchronously;
// we warm it up once and queue any utterance the moment a voice is ready.
let ttsVoice = null;
function pickVoice() {
  if (!window.speechSynthesis) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  // Prefer an English voice if available; otherwise first available.
  const english = voices.find((v) => /^en[-_]/i.test(v.lang));
  return english || voices[0];
}
if (window.speechSynthesis) {
  ttsVoice = pickVoice();
  window.speechSynthesis.addEventListener("voiceschanged", () => {
    if (!ttsVoice) ttsVoice = pickVoice();
  });
}

function speak(text) {
  if (!text) return;
  if (!window.speechSynthesis) {
    logStatus("tts: speechSynthesis not available");
    return;
  }
  try {
    // Do NOT call cancel() — iOS Chrome can freeze the synth queue afterwards.
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 1.0;
    utter.pitch = 1.0;
    utter.volume = 1.0;
    if (!ttsVoice) ttsVoice = pickVoice();
    if (ttsVoice) utter.voice = ttsVoice;
    utter.onerror = (e) => logStatus(`tts utterance error: ${e.error || "(no error code)"}`);
    window.speechSynthesis.speak(utter);
  } catch (e) {
    logStatus(`tts error: ${e}`);
  }
}

// Some browsers (notably mobile Chrome) require a user-initiated speak() to
// "unlock" the synth. Fire a silent one on the first button press.
let ttsUnlocked = false;
function unlockTts() {
  if (ttsUnlocked || !window.speechSynthesis) return;
  ttsUnlocked = true;
  try {
    const u = new SpeechSynthesisUtterance(" ");
    u.volume = 0;
    window.speechSynthesis.speak(u);
  } catch (_) { /* ignore */ }
}
document.addEventListener("click", unlockTts, { once: true, capture: true });
document.addEventListener("touchstart", unlockTts, { once: true, capture: true });

async function sendCommand(mode, text) {
  if (!text || !text.trim()) return;
  const ok = await activateMode(mode);
  if (!ok) return;
  logStatus(`cmd[${mode}]: ${text}`);
  const res = await api("/api/command", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  if (res) {
    setOutput(mode, res);
    logStatus(`-> ${res.spoken}`);
    speak(res.spoken);
  }
}

$$(".quick-cmd").forEach((btn) => {
  btn.addEventListener("click", () => sendCommand(btn.dataset.mode, btn.dataset.text));
});

$$(".cmd-send").forEach((btn) => {
  btn.addEventListener("click", () => {
    const mode = btn.dataset.mode;
    const input = document.querySelector(`.cmd-input[data-mode="${mode}"]`);
    if (!input) return;
    const text = input.value;
    input.value = "";
    sendCommand(mode, text);
  });
});

$$(".cmd-input").forEach((input) => {
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const mode = input.dataset.mode;
      const text = input.value;
      input.value = "";
      sendCommand(mode, text);
    }
  });
});

// Web Speech API: STT for voice commands.
const SpeechRecog = window.SpeechRecognition || window.webkitSpeechRecognition;
$$(".cmd-mic").forEach((btn) => {
  if (!SpeechRecog) {
    btn.disabled = true;
    btn.title = "Web Speech API not supported in this browser";
    btn.textContent = "🎤✕";
    return;
  }
  btn.addEventListener("click", () => {
    const mode = btn.dataset.mode;
    const rec = new SpeechRecog();
    rec.lang = "en-US";
    rec.continuous = false;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    btn.classList.add("recording");
    btn.disabled = true;
    rec.onstart = () => logStatus(`listening (${mode})...`);
    rec.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      logStatus(`heard: "${transcript}"`);
      sendCommand(mode, transcript);
    };
    rec.onerror = (e) => logStatus(`speech error: ${e.error}`);
    rec.onend = () => {
      btn.classList.remove("recording");
      btn.disabled = false;
    };
    try { rec.start(); }
    catch (e) {
      logStatus(`speech start failed: ${e}`);
      btn.classList.remove("recording");
      btn.disabled = false;
    }
  });
});

// ---- websockets -------------------------------------------------------------

function wsUrl(path) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}`;
}

function connectStateWs() {
  const ws = new WebSocket(wsUrl("/ws/state"));
  ws.onopen = () => logStatus("ws/state connected");
  ws.onclose = () => { logStatus("ws/state closed; retry 2s"); setTimeout(connectStateWs, 2000); };
  ws.onerror = () => logStatus("ws/state error");
  ws.onmessage = (ev) => {
    try { paintState(JSON.parse(ev.data)); } catch (_) { /* ignore */ }
  };
}

function connectCameraWs() {
  const ws = new WebSocket(wsUrl("/ws/camera"));
  ws.binaryType = "blob";
  ws.onopen = () => logStatus("ws/camera connected");
  ws.onclose = () => { logStatus("ws/camera closed; retry 3s"); setTimeout(connectCameraWs, 3000); };
  ws.onerror = () => logStatus("ws/camera error");
  ws.onmessage = (ev) => {
    const blob = ev.data;
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      frameWidth = img.naturalWidth;
      frameHeight = img.naturalHeight;
      if (cameraCanvas.width !== frameWidth) cameraCanvas.width = frameWidth;
      if (cameraCanvas.height !== frameHeight) cameraCanvas.height = frameHeight;
      cameraCtx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
    };
    img.src = url;
  };
}

// Initial paint + ws + current mode pill from server.
api("/api/state").then(paintState);
api("/api/modes").then((m) => { if (m && m.active) setActiveModePill(m.active); });
connectStateWs();
connectCameraWs();
