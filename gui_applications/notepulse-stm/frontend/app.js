/**
 * NotePulse — app.js
 *
 * Real-time AI Audio & Musical Pitch Dashboard
 * - Continuous Pitch Contour & Note Roll (VOCANO / vocal visualizer)
 * - 3-Class ML Model (C4, C5, F5) + Vocal Pitch Tracking (C3 to C6)
 * - Microsecond/Millisecond Latency Telemetry
 * - Live MEMS Microphone Waveform & Tuning Feedback
 */

"use strict";

const WS_URL          = "ws://localhost:8765";
const RECONNECT_DELAY = 3000;
const MAX_HISTORY     = 10;
const MAX_PITCH_PTS   = 50;   // ~12.5 seconds of pitch history

// ══════════════════════════════════════════════════════════════════════════════
// AI API Key Configuration (OpenRouter / Gemini)
// ══════════════════════════════════════════════════════════════════════════════
// Enter your OpenRouter API key below or enter it directly in the dashboard UI:
let gemini_key = "";

// ══════════════════════════════════════════════════════════════════════════════
// State
// ══════════════════════════════════════════════════════════════════════════════

let ws             = null;
let wsConnected    = false;
let mode           = "real";       // "real" | "mic" | "mock"
let running        = false;
let history        = [];
let pitchPoints    = [];           // [{ midi, note, inTune, ts }]
let currentSession = null;         // Live song performance tracker

// ══════════════════════════════════════════════════════════════════════════════
// DOM refs
// ══════════════════════════════════════════════════════════════════════════════

const $ = id => document.getElementById(id);

const dom = {
  noteCard:        $("noteCard"),
  noteDisplay:     $("noteDisplay"),
  noteFreq:        $("noteFreq"),
  centsBadge:      $("centsBadge"),
  noteBadge:       $("noteBadge"),
  noteGlow:        $("noteGlow"),
  modelScopeHint:  $("modelScopeHint"),

  confArc:         $("confArc"),
  confPct:         $("confPct"),
  probBars:        $("probBars"),

  btnStart:        $("btnStart"),
  btnStop:         $("btnStop"),
  btnFinishSong:   $("btnFinishSong"),
  btnReal:         $("btnReal"),
  btnMic:          $("btnMic"),
  btnMock:         $("btnMock"),
  systemState:     $("systemState"),
  connBadge:       $("connBadge"),

  pitchCanvas:     $("pitchCanvas"),
  tuningPill:      $("tuningPill"),

  waveCanvas:      $("waveCanvas"),
  sigBarFill:      $("sigBarFill"),
  sigPct:          $("sigPct"),
  latencyVal:      $("latencyVal"),
  latencySpeed:    $("latencySpeed"),
  latencyBarFill:  $("latencyBarFill"),

  // AI Summary elements
  summaryCard:       $("summaryCard"),
  aiModelTag:        $("aiModelTag"),
  btnToggleKey:      $("btnToggleKey"),
  btnAnalyzeNow:     $("btnAnalyzeNow"),
  apiKeyPanel:       $("apiKeyPanel"),
  inputApiKey:       $("inputApiKey"),
  btnSaveKey:        $("btnSaveKey"),
  sumScore:          $("sumScore"),
  sumScoreSub:       $("sumScoreSub"),
  sumInTune:         $("sumInTune"),
  sumInTuneSub:      $("sumInTuneSub"),
  sumDrift:          $("sumDrift"),
  sumDriftSub:       $("sumDriftSub"),
  sumTargets:        $("sumTargets"),
  sumTargetsSub:     $("sumTargetsSub"),
  sumDuration:       $("sumDuration"),
  sumEventsSub:      $("sumEventsSub"),
  summaryIdleNotice: $("summaryIdleNotice"),
  summaryLoading:    $("summaryLoading"),
  summaryResults:    $("summaryResults"),
  summaryKeyAlert:   $("summaryKeyAlert"),
  inputAlertKey:     $("inputAlertKey"),
  btnAlertSaveKey:   $("btnAlertSaveKey"),

  histBody:        $("histBody"),
  histCount:       $("histCount"),

  dotSensor:       $("dotSensor"),  txtSensor: $("txtSensor"),
  dotModel:        $("dotModel"),   txtModel:  $("txtModel"),
  dotWs:           $("dotWs"),      txtWs:     $("txtWs"),
  dotStream:       $("dotStream"),  txtStream: $("txtStream"),

  miName:          $("mi-name"),
  miNotes:         $("mi-notes"),
  miSr:            $("mi-sr"),
  miWin:           $("mi-win"),
  miStep:          $("mi-step"),
  miAcc:           $("mi-acc"),

  siBoard:         $("si-board"),
  siMic:           $("si-mic"),
  siSr:            $("si-sr"),
  siConn:          $("si-conn"),
  siMode:          $("si-mode"),

  consoleBody:     $("consoleBody"),
};

const waveCtx  = dom.waveCanvas.getContext("2d");
const pitchCtx = dom.pitchCanvas.getContext("2d");

// ══════════════════════════════════════════════════════════════════════════════
// WebSocket Connection
// ══════════════════════════════════════════════════════════════════════════════

function connect() {
  log("Connecting to " + WS_URL + " …", "info");
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    wsConnected = true;
    setConnBadge(true);
    setDot(dom.dotWs, dom.txtWs, "on", "SERVER ONLINE");
    log("WebSocket connected ✔", "ok");
    ws.send(JSON.stringify({ command: "get_status" }));
  };

  ws.onclose = () => {
    wsConnected = false;
    running = false;
    setConnBadge(false);
    setDot(dom.dotWs, dom.txtWs, "off", "SERVER OFFLINE");
    setDot(dom.dotStream, dom.txtStream, "off", "IDLE");
    updateControlButtons(false);
    log("WebSocket disconnected. Retrying in 3 s …", "warn");
    setTimeout(connect, RECONNECT_DELAY);
  };

  ws.onerror = () => {
    log("WebSocket connection error.", "error");
  };

  ws.onmessage = evt => {
    let msg;
    try { msg = JSON.parse(evt.data); } catch { return; }

    if (msg.type === "status")        return handleStatus(msg);
    if (msg.type === "start_result")  return handleStartResult(msg);
    if (msg.type === "stopped")       return handleStopped();
    if (msg.type === "pong")          return;

    // Regular prediction & pitch packet
    if (msg.note !== undefined)       return updateDashboard(msg);
  };
}

// ══════════════════════════════════════════════════════════════════════════════
// Message Handlers
// ══════════════════════════════════════════════════════════════════════════════

function handleStatus(msg) {
  const modelOk  = msg.model_loaded;
  const sensorOk = msg.sensor_connected;
  const mi       = msg.model_info || {};
  const si       = msg.sensor_info || {};

  setDot(dom.dotModel, dom.txtModel, modelOk ? "on" : "err",
         modelOk ? "MODEL LOADED" : "MODEL NOT LOADED");

  setDot(dom.dotSensor, dom.txtSensor, sensorOk ? "on" : "off",
         sensorOk ? "SENSOR CONNECTED" : "SENSOR DISCONNECTED");

  if (modelOk) populateModelInfo(mi);
  if (sensorOk) populateSensorInfo(si);

  // If server is already running real, mic, or mock, reflect it right away
  if (msg.mode === "real" && sensorOk) {
    running = true;
    mode = "real";
    updateControlButtons(true);
    setSystemState("LIVE (SENSOR)", "live");
    setDot(dom.dotStream, dom.txtStream, "on", "LISTENING (SENSOR)");
  } else if (msg.mode === "mic" && sensorOk) {
    running = true;
    mode = "mic";
    updateControlButtons(true);
    setSystemState("LIVE (PC MIC)", "live");
    setDot(dom.dotStream, dom.txtStream, "on", "LISTENING (PC MIC)");
  } else if (msg.mode === "mock") {
    running = true;
    mode = "mock";
    updateControlButtons(true);
    setSystemState("MOCK SIM", "mock");
    setDot(dom.dotStream, dom.txtStream, "on", "MOCK MODE");
  } else {
    running = false;
    updateControlButtons(false);
    setSystemState("SYSTEM PAUSED", "paused");
  }
  syncModeButtons();
}

function handleStartResult(msg) {
  if (msg.started) {
    running = true;
    updateControlButtons(true);
    const modeStr = msg.mode === "mock" ? "MOCK" : msg.mode === "mic" ? "LIVE (PC MIC)" : "LIVE (SENSOR)";
    setSystemState(modeStr, msg.mode === "mock" ? "mock" : "live");
    setDot(dom.dotStream, dom.txtStream, "on",
           msg.mode === "mock" ? "MOCK MODE" : msg.mode === "mic" ? "LISTENING (PC MIC)" : "LISTENING (SENSOR)");
    log("Monitoring active (" + msg.mode + " mode) ✔", "ok");
    startSongSession();
  } else {
    running = false;
    updateControlButtons(false);
    setSystemState("ERROR", "error");
    log("Failed to start: " + (msg.error || "unknown error"), "error");
  }
}

function handleStopped() {
  running = false;
  updateControlButtons(false);
  setSystemState("SYSTEM PAUSED", "paused");
  setDot(dom.dotStream, dom.txtStream, "off", "IDLE");
  log("Monitoring stopped.", "info");
  onSongCompleted();
}

// ══════════════════════════════════════════════════════════════════════════════
// Dashboard Update
// ══════════════════════════════════════════════════════════════════════════════

function updateDashboard(d) {
  recordSessionSample(d);

  const note         = d.note          || "—";
  const musicalNote  = d.musical_note  || note;
  const freq         = d.frequency     || 0;
  const targetFreq   = d.target_freq   || 0;
  const centsOff     = d.cents_off     != null ? d.cents_off : 0;
  const tuningStatus = d.tuning_status || "NONE";
  const midi         = d.midi          || 0;
  const conf         = d.confidence    || 0;
  const status       = d.status        || "LIVE";
  const latency      = d.latency_ms    || 0;
  const sigLv        = d.signal_level  || 0;
  const waveform     = d.waveform      || [];
  const probs        = d.all_probs     || {};
  const isModelNote  = Boolean(d.is_model_note);

  // ── Note Display & Frequency ──────────────────────────────────────────────
  if (status === "SILENCE" || status === "LISTENING") {
    dom.noteDisplay.textContent = "—";
    dom.noteFreq.textContent    = "— Hz";
    dom.centsBadge.textContent  = "±0 cents";
    dom.centsBadge.className    = "cents-badge";
    dom.tuningPill.textContent  = "PITCH: LISTENING";
    dom.tuningPill.className    = "tuning-pill";
    dom.modelScopeHint.textContent = "Listening for audio (targets: C4, C5, F5)...";
  } else {
    // A concrete musical note or ML target is detected
    dom.noteDisplay.textContent = note !== "—" ? note : musicalNote;
    dom.noteFreq.textContent    = freq > 0 ? freq.toFixed(1) + " Hz" : "— Hz";

    // Cents tuning badge
    const sign = centsOff > 0 ? "+" : "";
    dom.centsBadge.textContent = `${sign}${centsOff.toFixed(0)} cents`;
    if (Math.abs(centsOff) <= 15) {
      dom.centsBadge.className = "cents-badge in-tune";
      dom.tuningPill.textContent = `PITCH: IN TUNE (${sign}${centsOff}¢)`;
      dom.tuningPill.className = "tuning-pill in-tune";
    } else if (centsOff < -15) {
      dom.centsBadge.className = "cents-badge flat";
      dom.tuningPill.textContent = `PITCH: FLAT (${centsOff}¢)`;
      dom.tuningPill.className = "tuning-pill flat";
    } else {
      dom.centsBadge.className = "cents-badge sharp";
      dom.tuningPill.textContent = `PITCH: SHARP (+${centsOff}¢)`;
      dom.tuningPill.className = "tuning-pill sharp";
    }

    if (isModelNote) {
      dom.modelScopeHint.textContent = "★ Specialized 3-class ML target";
    } else {
      dom.modelScopeHint.textContent = `Extended vocal range (model targets: C4, C5, F5)`;
    }
  }

  // ── Note Card Color Theme ──────────────────────────────────────────────────
  dom.noteCard.className = "card card-note";
  if (["C4", "C5", "F5"].includes(musicalNote)) {
    dom.noteCard.classList.add("note-" + musicalNote);
  } else if (status !== "SILENCE" && musicalNote !== "—") {
    dom.noteCard.classList.add("note-other");
  }

  // ── Note Badge ────────────────────────────────────────────────────────────
  const badgeMap = {
    LIVE:           ["live",          status === "MOCK" ? "⬤ MOCK" : "⬤ LIVE TARGET"],
    OUTSIDE_RANGE:  ["outside-range", "⬤ VOCAL PITCH"],
    LISTENING:      ["silence",       "LISTENING"],
    SILENCE:        ["silence",       "SILENCE"],
    LOW_CONFIDENCE: ["silence",       "LISTENING"],
    ERROR:          ["error",         "ERROR"],
    MODEL_ERROR:    ["error",         "MODEL ERROR"],
  };
  const [badgeCls, badgeTxt] = badgeMap[status] || ["", status];
  dom.noteBadge.className = "note-badge " + badgeCls;
  dom.noteBadge.textContent = badgeTxt;

  // ── Confidence Ring ────────────────────────────────────────────────────────
  const pct    = Math.round(conf * 100);
  const circ   = 2 * Math.PI * 50; // 314.16
  const filled = circ * conf;
  dom.confArc.setAttribute("stroke-dasharray", filled + " " + circ);
  dom.confPct.textContent = pct + "%";

  const confColour = conf >= 0.7 ? "var(--accent)"
                   : conf >= 0.5 ? "var(--accent4)"
                   : "var(--accent3)";
  dom.confArc.style.stroke = confColour;
  dom.confArc.style.filter = "drop-shadow(0 0 4px " + confColour + ")";

  // ── 3-Class Probability Bars ───────────────────────────────────────────────
  renderProbBars(probs);

  // ── Signal Level ──────────────────────────────────────────────────────────
  const sigPct = Math.min(100, Math.round(sigLv * 100));
  dom.sigBarFill.style.width = sigPct + "%";
  dom.sigPct.textContent     = sigPct + "%";

  // ── Latency (Backend Inference) ───────────────────────────────────────────
  dom.latencyVal.textContent = latency > 0 ? latency.toFixed(1) + " ms" : "— ms";
  const latPct = Math.min(100, (latency / 250) * 100);
  dom.latencyBarFill.style.width = latPct + "%";

  if (latency > 0) {
    const headroom = (250 / latency).toFixed(1);
    dom.latencySpeed.textContent = latency < 60 ? `ULTRA-FAST (${headroom}x real-time)` : `GOOD (${headroom}x real-time)`;
  }

  // ── Waveform Canvas ───────────────────────────────────────────────────────
  if (waveform.length > 0) drawWaveform(waveform);

  // ── Continuous Pitch Contour & Note Roll ──────────────────────────────────
  if (status !== "SILENCE" && midi > 0) {
    pitchPoints.push({
      midi: midi,
      note: musicalNote,
      inTune: Math.abs(centsOff) <= 15,
      isModel: isModelNote,
      ts: Date.now()
    });
    if (pitchPoints.length > MAX_PITCH_PTS) pitchPoints.shift();
  } else if (status === "SILENCE") {
    // Record silence gap
    pitchPoints.push({ midi: null, note: "—", inTune: false, isModel: false, ts: Date.now() });
    if (pitchPoints.length > MAX_PITCH_PTS) pitchPoints.shift();
  }
  drawPitchContour();

  // ── Sensor / Model Status Panels ──────────────────────────────────────────
  if (d.sensor_info) populateSensorInfo(d.sensor_info);
  if (d.model_info)  populateModelInfo(d.model_info);

  // ── Status Dots ───────────────────────────────────────────────────────────
  const sensorOk = d.sensor_info && d.sensor_info.mode === "real";
  setDot(dom.dotSensor, dom.txtSensor, sensorOk ? "on" : "off",
         sensorOk ? "SENSOR CONNECTED" : "SENSOR DISCONNECTED");
  setDot(dom.dotStream, dom.txtStream,
         status === "LIVE" || status === "OUTSIDE_RANGE" || status === "MOCK" ? "on"
         : status === "SILENCE" ? "warn" : "err",
         status === "OUTSIDE_RANGE" ? "VOCAL PITCH" : status);

  // ── Detection History ─────────────────────────────────────────────────────
  if ((status === "LIVE" || status === "OUTSIDE_RANGE" || status === "MOCK") && musicalNote !== "—" && musicalNote !== "?") {
    const lastEntry = history[0];
    // Push if note changed or > 1.0s elapsed
    if (!lastEntry || lastEntry.note !== musicalNote || (d.timestamp - lastEntry.ts) > 1.2) {
      pushHistory({
        ts: d.timestamp,
        note: musicalNote,
        freq: freq,
        cents: centsOff,
        conf: pct,
        type: isModelNote ? "ML TARGET" : "VOCAL PITCH"
      });
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Continuous Pitch Contour & Target Note Roll (ChatGPT image visualizer)
// ══════════════════════════════════════════════════════════════════════════════

// Musical scale rows from MIDI 57 (A3) to 77 (F5)
const DISPLAY_NOTES = [
  { name: "F5", midi: 77, target: true },
  { name: "E5", midi: 76, target: false },
  { name: "D5", midi: 74, target: false },
  { name: "C5", midi: 72, target: true },
  { name: "B4", midi: 71, target: false },
  { name: "A4", midi: 69, target: false },
  { name: "G4", midi: 67, target: false },
  { name: "F4", midi: 65, target: false },
  { name: "E4", midi: 64, target: false },
  { name: "D4", midi: 62, target: false },
  { name: "C4", midi: 60, target: true },
];

function drawPitchContour() {
  const W = dom.pitchCanvas.width;
  const H = dom.pitchCanvas.height;
  const padLeft = 40;
  const padRight = 10;
  const plotW = W - padLeft - padRight;

  pitchCtx.clearRect(0, 0, W, H);

  const minMidi = 58;  // Below C4
  const maxMidi = 78;  // Above F5
  const midiRange = maxMidi - minMidi;

  const midiToY = m => H - ((m - minMidi) / midiRange) * H;

  // 1. Draw horizontal note lanes
  DISPLAY_NOTES.forEach(dn => {
    const y = midiToY(dn.midi);

    // If it's a model target note (C4, C5, F5), highlight the lane
    if (dn.target) {
      pitchCtx.fillStyle = dn.name === "C4" ? "rgba(0, 245, 196, 0.08)"
                         : dn.name === "C5" ? "rgba(123, 97, 255, 0.08)"
                         : "rgba(255, 107, 107, 0.08)";
      pitchCtx.fillRect(padLeft, y - 7, plotW, 14);

      pitchCtx.strokeStyle = dn.name === "C4" ? "rgba(0, 245, 196, 0.25)"
                           : dn.name === "C5" ? "rgba(123, 97, 255, 0.25)"
                           : "rgba(255, 107, 107, 0.25)";
      pitchCtx.lineWidth = 1;
      pitchCtx.strokeRect(padLeft, y - 7, plotW, 14);
    } else {
      pitchCtx.strokeStyle = "rgba(30, 34, 53, 0.6)";
      pitchCtx.lineWidth = 1;
      pitchCtx.beginPath();
      pitchCtx.moveTo(padLeft, y);
      pitchCtx.lineTo(W - padRight, y);
      pitchCtx.stroke();
    }

    // Note label on left axis
    pitchCtx.font = "10px 'Space Mono', monospace";
    pitchCtx.fillStyle = dn.target ? (dn.name === "C4" ? "#00f5c4" : dn.name === "C5" ? "#7b61ff" : "#ff6b6b") : "#8892b0";
    pitchCtx.textAlign = "right";
    pitchCtx.textBaseline = "middle";
    pitchCtx.fillText(dn.name, padLeft - 6, y);
  });

  // 2. Draw continuous singer pitch trace & contour points
  if (pitchPoints.length < 2) return;

  const stepX = plotW / (MAX_PITCH_PTS - 1);
  const startIdx = MAX_PITCH_PTS - pitchPoints.length;

  // Continuous line
  pitchCtx.lineWidth = 2.5;
  pitchCtx.lineCap = "round";
  pitchCtx.lineJoin = "round";

  let segmentActive = false;

  for (let i = 0; i < pitchPoints.length; i++) {
    const pt = pitchPoints[i];
    const x = padLeft + (startIdx + i) * stepX;

    if (pt.midi === null) {
      segmentActive = false;
      continue;
    }

    const y = midiToY(pt.midi);

    if (!segmentActive) {
      pitchCtx.beginPath();
      pitchCtx.moveTo(x, y);
      segmentActive = true;
    } else {
      pitchCtx.lineTo(x, y);
    }

    // Color based on in-tune status
    pitchCtx.strokeStyle = pt.inTune ? "#00f5c4" : "#4cc9f0";
    pitchCtx.shadowColor = pt.inTune ? "rgba(0, 245, 196, 0.6)" : "rgba(76, 201, 240, 0.6)";
    pitchCtx.shadowBlur = 6;
    pitchCtx.stroke();
  }
  pitchCtx.shadowBlur = 0;

  // Draw discrete pitch nodes (points)
  for (let i = 0; i < pitchPoints.length; i++) {
    const pt = pitchPoints[i];
    if (pt.midi === null) continue;

    const x = padLeft + (startIdx + i) * stepX;
    const y = midiToY(pt.midi);

    pitchCtx.beginPath();
    pitchCtx.arc(x, y, i === pitchPoints.length - 1 ? 4.5 : 2.5, 0, Math.PI * 2);
    pitchCtx.fillStyle = pt.inTune ? "#00f5c4" : "#4cc9f0";
    pitchCtx.fill();

    // Pulse head on newest point
    if (i === pitchPoints.length - 1) {
      pitchCtx.strokeStyle = "#ffffff";
      pitchCtx.lineWidth = 1.5;
      pitchCtx.stroke();
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Waveform Canvas
// ══════════════════════════════════════════════════════════════════════════════

function drawWaveform(samples) {
  const W = dom.waveCanvas.width;
  const H = dom.waveCanvas.height;
  const mid = H / 2;

  waveCtx.clearRect(0, 0, W, H);

  // Grid line
  waveCtx.strokeStyle = "rgba(30, 34, 53, 0.8)";
  waveCtx.lineWidth = 1;
  waveCtx.beginPath();
  waveCtx.moveTo(0, mid);
  waveCtx.lineTo(W, mid);
  waveCtx.stroke();

  // Waveform fill
  const step = W / samples.length;
  const grad = waveCtx.createLinearGradient(0, 0, W, 0);
  grad.addColorStop(0,   "rgba(0, 245, 196, 0.15)");
  grad.addColorStop(0.5, "rgba(123, 97, 255, 0.15)");
  grad.addColorStop(1,   "rgba(0, 245, 196, 0.15)");
  waveCtx.fillStyle = grad;
  waveCtx.beginPath();
  waveCtx.moveTo(0, mid);
  samples.forEach((v, i) => {
    const x = i * step;
    const y = mid - v * mid * 0.9;
    waveCtx.lineTo(x, y);
  });
  waveCtx.lineTo(W, mid);
  waveCtx.closePath();
  waveCtx.fill();

  // Waveform line
  const lineGrad = waveCtx.createLinearGradient(0, 0, W, 0);
  lineGrad.addColorStop(0,   "#00f5c4");
  lineGrad.addColorStop(0.5, "#7b61ff");
  lineGrad.addColorStop(1,   "#00f5c4");
  waveCtx.strokeStyle = lineGrad;
  waveCtx.lineWidth   = 1.5;
  waveCtx.beginPath();
  samples.forEach((v, i) => {
    const x = i * step;
    const y = mid - v * mid * 0.9;
    i === 0 ? waveCtx.moveTo(x, y) : waveCtx.lineTo(x, y);
  });
  waveCtx.stroke();
}

// ══════════════════════════════════════════════════════════════════════════════
// 3-Class Probability Bars
// ══════════════════════════════════════════════════════════════════════════════

const NOTE_COLOURS = {
  C4: "var(--note-c4)",
  C5: "var(--note-c5)",
  F5: "var(--note-f5)",
};

function renderProbBars(probs) {
  if (!probs || Object.keys(probs).length === 0) return;
  dom.probBars.innerHTML = "";
  Object.entries(probs)
    .sort(([,a],[,b]) => b - a)
    .forEach(([cls, p]) => {
      const colour = NOTE_COLOURS[cls] || "var(--text2)";
      const row = document.createElement("div");
      row.className = "prob-row";
      row.innerHTML = `
        <span class="prob-note">${cls}</span>
        <div class="prob-bar-wrap">
          <div class="prob-bar-fill" style="width:${(p*100).toFixed(1)}%;background:${colour}"></div>
        </div>
        <span class="prob-val">${(p*100).toFixed(0)}%</span>
      `;
      dom.probBars.appendChild(row);
    });
}

// ══════════════════════════════════════════════════════════════════════════════
// Info Panels
// ══════════════════════════════════════════════════════════════════════════════

function populateModelInfo(mi) {
  if (!mi) return;
  dom.miName.textContent  = mi.name            || "NotePulse v1";
  dom.miNotes.textContent = (mi.known_notes    || ["C4", "C5", "F5"]).join(", ");
  dom.miSr.textContent    = mi.sample_rate_hz  ? (mi.sample_rate_hz/1000).toFixed(1) + " kHz" : "44.1 kHz";
  dom.miWin.textContent   = mi.window_seconds  ? mi.window_seconds + " s"  : "0.50 s";
  dom.miStep.textContent  = mi.step_seconds    ? mi.step_seconds   + " s"  : "0.25 s";
  dom.miAcc.textContent   = mi.val_accuracy_pct != null ? mi.val_accuracy_pct + "%" : "95.49%";
  if (mi.loaded) setDot(dom.dotModel, dom.txtModel, "on", "MODEL LOADED");
}

function populateSensorInfo(si) {
  if (!si) return;
  dom.siBoard.textContent = si.board       || "SensorTile.box PRO";
  dom.siMic.textContent   = si.microphone  || "mp23db01hp_mic";
  dom.siSr.textContent    = si.input_sr_hz ? (si.input_sr_hz/1000) + " kHz" : "48 kHz";
  dom.siConn.textContent  = si.connection  || "USB";
  dom.siMode.textContent  = (si.mode || "—").toUpperCase();
}

// ══════════════════════════════════════════════════════════════════════════════
// Detection History
// ══════════════════════════════════════════════════════════════════════════════

function pushHistory(entry) {
  history.unshift(entry);
  if (history.length > MAX_HISTORY) history.pop();
  renderHistory();
}

function renderHistory() {
  dom.histCount.textContent = history.length + " events";
  dom.histBody.innerHTML = history.map(h => {
    const t = new Date(h.ts * 1000).toLocaleTimeString();
    const nc = ["C4","C5","F5"].includes(h.note) ? "note-" + h.note : "note-other";
    const sign = h.cents > 0 ? "+" : "";
    return `<tr>
      <td>${t}</td>
      <td class="note-cell ${nc}">${h.note}</td>
      <td>${h.freq > 0 ? h.freq.toFixed(1) + " Hz" : "—"}</td>
      <td>${sign}${h.cents.toFixed(0)}¢</td>
      <td>${h.conf}%</td>
      <td style="font-size:0.6rem;color:var(--text3)">${h.type}</td>
    </tr>`;
  }).join("");
}

// ══════════════════════════════════════════════════════════════════════════════
// UI Helpers
// ══════════════════════════════════════════════════════════════════════════════

function setConnBadge(connected) {
  dom.connBadge.textContent = connected ? "⬤ CONNECTED" : "⬤ DISCONNECTED";
  dom.connBadge.className   = "conn-badge " + (connected ? "connected" : "disconnected");
}

function setDot(dot, txt, state, label) {
  dot.className = "status-dot " + (state === "on" ? "on" : state === "warn" ? "warn" : state === "err" ? "err" : "");
  txt.textContent = label;
}

function setSystemState(label, cls) {
  dom.systemState.textContent = label;
  dom.systemState.className   = "system-state " + (cls || "");
}

function updateControlButtons(isRunning) {
  dom.btnStart.disabled = isRunning;
  dom.btnStop.disabled  = !isRunning;
  if (dom.btnFinishSong) dom.btnFinishSong.disabled = !isRunning;
}

function syncModeButtons() {
  dom.btnReal.classList.toggle("active", mode === "real");
  dom.btnMic.classList.toggle("active",  mode === "mic");
  dom.btnMock.classList.toggle("active", mode === "mock");
}

function log(msg, type = "info") {
  const line = document.createElement("div");
  line.className = "log-line " + type;
  const ts = new Date().toLocaleTimeString();
  line.textContent = "[" + ts + "] " + msg;
  dom.consoleBody.prepend(line);
  while (dom.consoleBody.childElementCount > 40) {
    dom.consoleBody.lastChild.remove();
  }
}

function send(obj) {
  if (ws && wsConnected) ws.send(JSON.stringify(obj));
}

// ══════════════════════════════════════════════════════════════════════════════
// Song Session Tracking & AI Summary Logic
// ══════════════════════════════════════════════════════════════════════════════

function getEffectiveGeminiKey() {
  // 1. In-memory / declared variable
  if (typeof gemini_key === "string" && gemini_key.trim().length > 0) {
    return gemini_key.trim();
  }
  // 2. Window variable check
  if (typeof window !== "undefined" && typeof window.gemini_key === "string" && window.gemini_key.trim().length > 0) {
    return window.gemini_key.trim();
  }
  // 3. Local storage fallback
  const stored = localStorage.getItem("notepulse_gemini_key");
  if (stored && stored.trim().length > 0) {
    return stored.trim();
  }
  return "";
}

function setEffectiveGeminiKey(key) {
  const cleaned = (key || "").trim();
  gemini_key = cleaned;
  if (typeof window !== "undefined") window.gemini_key = cleaned;
  if (cleaned) {
    localStorage.setItem("notepulse_gemini_key", cleaned);
    if (dom.inputApiKey) dom.inputApiKey.value = cleaned;
    if (dom.inputAlertKey) dom.inputAlertKey.value = cleaned;
    log("API key saved ✔", "ok");
  } else {
    localStorage.removeItem("notepulse_gemini_key");
  }
}

function startSongSession() {
  currentSession = {
    startTime: Date.now(),
    endTime: null,
    totalFrames: 0,
    activeFrames: 0,
    silenceFrames: 0,
    notesSung: {},         // { "C4": 14, "G4": 8, ... }
    centsErrors: [],        // [cents_off, ...]
    confidences: [],
    inTuneCount: 0,         // |cents| <= 15
    flatCount: 0,           // cents < -15
    sharpCount: 0,          // cents > 15
    targetStats: {
      C4: { hits: 0, inTune: 0, centsList: [] },
      C5: { hits: 0, inTune: 0, centsList: [] },
      F5: { hits: 0, inTune: 0, centsList: [] },
    },
    problemMoments: [],     // Significant pitch deviations (> 22 cents)
    timeline: [],           // Transition timeline
    metrics: null
  };

  // Reset summary view to live recording indicator
  if (dom.summaryIdleNotice) {
    dom.summaryIdleNotice.style.display = "flex";
    const titleEl = dom.summaryIdleNotice.querySelector(".idle-text strong");
    const subEl = dom.summaryIdleNotice.querySelector(".idle-text span");
    if (titleEl) titleEl.textContent = "● Song performance in progress...";
    if (subEl) subEl.textContent = "Listening live. Hit 'STOP MONITORING' or 'COMPLETE SONG' when done to generate AI analysis.";
  }
  if (dom.summaryLoading) dom.summaryLoading.style.display = "none";
  if (dom.summaryResults) dom.summaryResults.style.display = "none";
  if (dom.summaryKeyAlert) dom.summaryKeyAlert.style.display = "none";
}

function recordSessionSample(d) {
  if (!currentSession || !running) return;

  const note = d.musical_note || d.note;
  const status = d.status || "LIVE";
  const cents = d.cents_off != null ? Number(d.cents_off) : 0;
  const freq = d.frequency || 0;
  const conf = d.confidence || 0;

  currentSession.totalFrames++;

  if (status === "SILENCE" || !note || note === "—" || note === "?") {
    currentSession.silenceFrames++;
    return;
  }

  currentSession.activeFrames++;
  currentSession.centsErrors.push(cents);
  currentSession.confidences.push(conf);

  // Note frequency distribution
  currentSession.notesSung[note] = (currentSession.notesSung[note] || 0) + 1;

  // Intonation tracking
  if (Math.abs(cents) <= 15) {
    currentSession.inTuneCount++;
  } else if (cents < -15) {
    currentSession.flatCount++;
  } else {
    currentSession.sharpCount++;
  }

  // Model Target notes (C4, C5, F5)
  if (currentSession.targetStats[note]) {
    currentSession.targetStats[note].hits++;
    if (Math.abs(cents) <= 15) {
      currentSession.targetStats[note].inTune++;
    }
    currentSession.targetStats[note].centsList.push(cents);
  }

  // Problem / off-pitch moment tracking (|cents| > 22 or sudden jumps)
  const elapsedSec = ((Date.now() - currentSession.startTime) / 1000).toFixed(1);
  if (Math.abs(cents) >= 22) {
    const lastProb = currentSession.problemMoments[currentSession.problemMoments.length - 1];
    // Throttle to not record duplicate consecutive 250ms frames for same note
    if (!lastProb || (lastProb.note !== note) || (Number(elapsedSec) - Number(lastProb.time) > 1.2)) {
      currentSession.problemMoments.push({
        time: elapsedSec,
        note: note,
        freq: freq.toFixed(1),
        cents: Math.round(cents),
        type: cents < 0 ? "flat" : "sharp"
      });
    }
  }

  // Live timeline transitions
  if (currentSession.timeline.length === 0 || 
      currentSession.timeline[currentSession.timeline.length - 1].note !== note) {
    currentSession.timeline.push({
      time: elapsedSec,
      note: note,
      cents: Math.round(cents),
      inTune: Math.abs(cents) <= 15
    });
  }
}

function onSongCompleted() {
  if (!currentSession) return;
  currentSession.endTime = Date.now();
  const durSec = Math.max(1, Math.round((currentSession.endTime - currentSession.startTime) / 1000));

  const active = currentSession.activeFrames;
  if (active < 3) {
    // Too short
    dom.sumScore.textContent = "—";
    dom.sumInTune.textContent = "—";
    dom.sumDrift.textContent = "—";
    dom.sumTargets.textContent = "0/3";
    dom.sumDuration.textContent = durSec + "s";
    dom.sumEventsSub.textContent = "0 active notes";

    dom.summaryIdleNotice.style.display = "flex";
    const titleEl = dom.summaryIdleNotice.querySelector(".idle-text strong");
    const subEl = dom.summaryIdleNotice.querySelector(".idle-text span");
    if (titleEl) titleEl.textContent = "Performance too short for AI critique";
    if (subEl) subEl.textContent = "Sing or play notes for at least a few seconds before stopping to generate a full analysis.";
    dom.summaryLoading.style.display = "none";
    dom.summaryResults.style.display = "none";
    dom.summaryKeyAlert.style.display = "none";
    return;
  }

  const inTunePct = Math.round((currentSession.inTuneCount / active) * 100);
  const flatPct = Math.round((currentSession.flatCount / active) * 100);
  const sharpPct = Math.round((currentSession.sharpCount / active) * 100);

  const meanCents = currentSession.centsErrors.length > 0
    ? (currentSession.centsErrors.reduce((a, b) => a + b, 0) / currentSession.centsErrors.length)
    : 0;

  // Intonation score: 0 to 100
  const score = Math.max(15, Math.min(99, Math.round(
    inTunePct * 0.75 + (100 - Math.min(100, Math.abs(meanCents) * 2.2)) * 0.25
  )));

  // Target notes hit count
  const targetsHit = Object.entries(currentSession.targetStats).filter(([, v]) => v.hits > 0).length;
  const hitNames = Object.entries(currentSession.targetStats).filter(([, v]) => v.hits > 0).map(([k]) => k).join(", ") || "None";

  // Update quick stat chips
  dom.sumScore.textContent = score + "%";
  dom.sumScoreSub.textContent = score >= 85 ? "Excellent accuracy" : score >= 70 ? "Good pitch control" : "Needs intonation work";

  dom.sumInTune.textContent = inTunePct + "%";
  dom.sumInTuneSub.textContent = `${currentSession.inTuneCount}/${active} frames on pitch`;

  const driftSign = meanCents > 0 ? "+" : "";
  dom.sumDrift.textContent = `${driftSign}${meanCents.toFixed(0)}¢`;
  dom.sumDrift.className = "summary-stat-val val-drift " + (meanCents < -6 ? "flat" : meanCents > 6 ? "sharp" : "");
  dom.sumDriftSub.textContent = flatPct > sharpPct + 10 ? `${flatPct}% flat bias` : sharpPct > flatPct + 10 ? `${sharpPct}% sharp bias` : "Balanced pitch center";

  dom.sumTargets.textContent = `${targetsHit}/3`;
  dom.sumTargetsSub.textContent = hitNames ? `Hit: ${hitNames}` : "No targets hit";

  dom.sumDuration.textContent = durSec + "s";
  const distinctNotesCount = Object.keys(currentSession.notesSung).length;
  dom.sumEventsSub.textContent = `${active} frames · ${distinctNotesCount} notes`;

  dom.summaryCard.classList.add("has-data");

  // Save calculated metrics in session
  currentSession.metrics = {
    durationSec: durSec,
    activeFrames: active,
    score,
    inTunePct,
    flatPct,
    sharpPct,
    meanCents,
    targetsHit,
    hitNames,
    distinctNotesCount
  };

  // Trigger AI evaluation
  generateSongSummary();
}

async function generateSongSummary() {
  if (!currentSession || currentSession.activeFrames < 3) {
    log("No recent song performance data to analyze.", "warn");
    return;
  }

  const apiKey = getEffectiveGeminiKey();
  if (!apiKey) {
    // Show API Key needed alert box
    dom.summaryIdleNotice.style.display = "none";
    dom.summaryLoading.style.display = "none";
    dom.summaryResults.style.display = "none";
    dom.summaryKeyAlert.style.display = "block";
    log("OpenRouter API key required. Add to 'gemini_key' in app.js or enter it in the summary panel.", "warn");
    return;
  }

  // Key is available, show loading spinner
  dom.summaryIdleNotice.style.display = "none";
  dom.summaryKeyAlert.style.display = "none";
  dom.summaryResults.style.display = "none";
  dom.summaryLoading.style.display = "flex";

  const m = currentSession.metrics || {
    durationSec: 10,
    activeFrames: currentSession.activeFrames,
    score: 75,
    inTunePct: 70,
    flatPct: 20,
    sharpPct: 10,
    meanCents: -5
  };

  // Prepare notes distribution string
  const notesBreakdown = Object.entries(currentSession.notesSung)
    .sort(([, a], [, b]) => b - a)
    .map(([note, count]) => `${note}: ${count} frames (${Math.round((count / m.activeFrames) * 100)}%)`)
    .join(", ");

  // Target notes status
  const targetReport = Object.entries(currentSession.targetStats).map(([note, data]) => {
    if (data.hits === 0) return `${note}: Not detected in performance`;
    const acc = Math.round((data.inTune / data.hits) * 100);
    const avgCents = Math.round(data.centsList.reduce((a, b) => a + b, 0) / data.hits);
    return `${note}: ${data.hits} hits (${acc}% in-tune ±15¢, avg drift ${avgCents > 0 ? "+" : ""}${avgCents}¢)`;
  }).join("; ");

  // Notable issues log
  const issuesLog = currentSession.problemMoments.slice(0, 8).map(p =>
    `- At ${p.time}s: Note ${p.note} (${p.freq} Hz) went ${p.type} by ${p.cents > 0 ? "+" : ""}${p.cents} cents`
  ).join("\n") || "No extreme pitch spikes (>25¢) detected.";

  // Build structured prompt for Gemini via OpenRouter
  const userPrompt = `You are NotePulse AI, an expert vocal coach and musical performance analyst.

A musician/singer just completed a song. Below is their real-time telemetry from NotePulse:

SONG PERFORMANCE METRICS:
- Song Duration: ${m.durationSec}s (${m.activeFrames} frames analyzed)
- Intonation Score: ${m.score} / 100
- In-Tune Rate (±15 cents): ${m.inTunePct}%
- Flat Pitch Bias: ${m.flatPct}% (singing under pitch)
- Sharp Pitch Bias: ${m.sharpPct}% (singing over pitch)
- Net Pitch Offset: ${m.meanCents > 0 ? "+" : ""}${m.meanCents.toFixed(1)} cents (${Math.abs(m.meanCents) <= 6 ? "Well centered" : m.meanCents < 0 ? "Noticeable flat drag" : "Noticeable sharp push"})

TARGET ML MODEL NOTES (C4, C5, F5):
${targetReport}

ALL DETECTED VOCAL NOTES:
${notesBreakdown}

NOTABLE PITCH PROBLEMS / DRIFT:
${issuesLog}

YOUR TASK:
Provide a concise, expert, and practical performance critique formatted in EXACTLY three markdown sections:

### 1. Right Notes Hit
State clearly whether the right notes and target notes were hit. Evaluate accuracy on C4, C5, F5, key vocal scale pitches, and pitch centering.

### 2. What Went Wrong
Analyze specifically what went wrong during the song: intonation drift (flat vs sharp), register breaks, pitch fatigue on higher notes, note transition wobble, or sustain instability. Mention specific notes and cents if relevant.

### 3. How to Improve
Give 2 to 3 actionable, specific vocal exercises or physical adjustments (e.g. breath compression / appoggio, vowel shaping, lip trills, sirens, octave intervals) to fix these exact issues.

Keep the response concise (under 220 words total), sharp, and formatted with bullet points for readability.`;

  try {
    let aiText = "";

    if (apiKey.startsWith("AIzaSy")) {
      // Direct Google Gemini API endpoint
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ parts: [{ text: userPrompt }] }]
        })
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.error?.message || `Gemini API HTTP ${res.status}`);
      }
      const data = await res.json();
      aiText = data.candidates?.[0]?.content?.parts?.[0]?.text || "";
    } else {
      // OpenRouter API endpoint
      const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${apiKey}`,
          "HTTP-Referer": window.location.href || "http://localhost",
          "X-Title": "NotePulse"
        },
        body: JSON.stringify({
          model: "google/gemini-2.0-flash-001",
          messages: [
            {
              role: "system",
              content: "You are NotePulse AI Vocal Coach. Provide structured, concise, expert musical feedback."
            },
            {
              role: "user",
              content: userPrompt
            }
          ],
          temperature: 0.35,
          max_tokens: 700
        })
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.error?.message || `OpenRouter HTTP ${res.status}`);
      }
      const data = await res.json();
      aiText = data.choices?.[0]?.message?.content || "";
    }

    if (!aiText) throw new Error("Empty response returned by AI model.");

    renderAISummary(aiText);
    log("AI Song Performance Summary generated ✔", "ok");

  } catch (err) {
    console.error("AI Summary Error:", err);
    log("AI Summary Error: " + err.message, "error");
    dom.summaryLoading.style.display = "none";
    dom.summaryResults.style.display = "block";
    dom.summaryResults.innerHTML = `
      <div class="summary-block block-issues">
        <div class="block-header">
          <div class="block-title">⚠️ AI SUMMARY GENERATION FAILED</div>
          <span class="block-tag">ERROR</span>
        </div>
        <div class="block-body">
          <p><strong>Error details:</strong> ${escapeHtml(err.message)}</p>
          <p>Please check your OpenRouter API key and network connection. Click <strong>ANALYZE</strong> to retry.</p>
        </div>
      </div>
    `;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatMarkdown(text) {
  if (!text) return "";
  const safe = escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  const lines = safe.split("\n");
  let inList = false;
  const result = [];

  for (let line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ") || /^\d+\.\s/.test(trimmed)) {
      if (!inList) {
        result.push("<ul>");
        inList = true;
      }
      const itemContent = trimmed.replace(/^[-*]\s+|\d+\.\s+/, "");
      result.push(`<li>${itemContent}</li>`);
    } else {
      if (inList) {
        result.push("</ul>");
        inList = false;
      }
      if (trimmed.length > 0) {
        result.push(`<p>${trimmed}</p>`);
      }
    }
  }
  if (inList) result.push("</ul>");
  return result.join("");
}

function renderAISummary(markdownText) {
  dom.summaryLoading.style.display = "none";
  dom.summaryResults.style.display = "flex";

  let part1 = "", part2 = "", part3 = "";

  const sec1Match = markdownText.match(/(?:###?\s*(?:1[.)]?\s*)?Right Notes Hit[\s\S]*?)(?=###?\s*(?:2[.)]?\s*)?What Went Wrong|$)/i);
  const sec2Match = markdownText.match(/(?:###?\s*(?:2[.)]?\s*)?What Went Wrong[\s\S]*?)(?=###?\s*(?:3[.)]?\s*)?How to Improve|$)/i);
  const sec3Match = markdownText.match(/(?:###?\s*(?:3[.)]?\s*)?How to Improve[\s\S]*?)$/i);

  if (sec1Match && sec2Match && sec3Match) {
    part1 = sec1Match[0].replace(/^###?.*?\n/, "").trim();
    part2 = sec2Match[0].replace(/^###?.*?\n/, "").trim();
    part3 = sec3Match[0].replace(/^###?.*?\n/, "").trim();
  } else {
    const parts = markdownText.split(/###?\s+/).filter(Boolean);
    if (parts.length >= 3) {
      part1 = parts[0].replace(/^.*?\n/, "").trim();
      part2 = parts[1].replace(/^.*?\n/, "").trim();
      part3 = parts[2].replace(/^.*?\n/, "").trim();
    } else {
      part1 = markdownText;
    }
  }

  dom.summaryResults.innerHTML = `
    <div class="summary-block block-notes">
      <div class="block-header">
        <div class="block-title">🎯 1. RIGHT NOTES HIT</div>
        <span class="block-tag">TARGET ACCURACY</span>
      </div>
      <div class="block-body">
        ${formatMarkdown(part1)}
      </div>
    </div>

    <div class="summary-block block-issues">
      <div class="block-header">
        <div class="block-title">⚠️ 2. WHAT WENT WRONG</div>
        <span class="block-tag">PITCH DIAGNOSTIC</span>
      </div>
      <div class="block-body">
        ${formatMarkdown(part2)}
      </div>
    </div>

    <div class="summary-block block-improve">
      <div class="block-header">
        <div class="block-title">🚀 3. HOW TO IMPROVE</div>
        <span class="block-tag">VOCAL DRILLS</span>
      </div>
      <div class="block-body">
        ${formatMarkdown(part3)}
      </div>
    </div>

    <div class="summary-coach-footer">
      <span>AI Model: OpenRouter / Gemini Flash</span>
      <button type="button" id="btnCopyReport">📋 Copy Report</button>
    </div>
  `;

  const btnCopy = $("btnCopyReport");
  if (btnCopy) {
    btnCopy.addEventListener("click", () => {
      navigator.clipboard.writeText(markdownText).then(() => {
        btnCopy.textContent = "✔ Copied!";
        setTimeout(() => { btnCopy.textContent = "📋 Copy Report"; }, 2000);
      });
    });
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Event Listeners
// ══════════════════════════════════════════════════════════════════════════════

dom.btnStart.addEventListener("click", () => {
  if (running) {
    log("Monitoring is already active.", "info");
    return;
  }
  log("Requesting start in " + mode + " mode …", "info");
  send({ command: "start", mode });
});

dom.btnStop.addEventListener("click", () => {
  log("Stopping monitoring & concluding song …", "info");
  send({ command: "stop" });
  if (running) {
    running = false;
    updateControlButtons(false);
    onSongCompleted();
  }
});

if (dom.btnFinishSong) {
  dom.btnFinishSong.addEventListener("click", () => {
    log("Completing song & generating AI summary …", "info");
    send({ command: "stop" });
    if (running) {
      running = false;
      updateControlButtons(false);
      onSongCompleted();
    }
  });
}

if (dom.btnAnalyzeNow) {
  dom.btnAnalyzeNow.addEventListener("click", () => {
    log("Re-analyzing last song performance …", "info");
    generateSongSummary();
  });
}

if (dom.btnToggleKey) {
  dom.btnToggleKey.addEventListener("click", () => {
    const isHidden = dom.apiKeyPanel.style.display === "none";
    dom.apiKeyPanel.style.display = isHidden ? "block" : "none";
  });
}

if (dom.btnSaveKey) {
  dom.btnSaveKey.addEventListener("click", () => {
    setEffectiveGeminiKey(dom.inputApiKey.value);
    dom.apiKeyPanel.style.display = "none";
  });
}

if (dom.btnAlertSaveKey) {
  dom.btnAlertSaveKey.addEventListener("click", () => {
    setEffectiveGeminiKey(dom.inputAlertKey.value);
    generateSongSummary();
  });
}

dom.btnReal.addEventListener("click", () => {
  mode = "real";
  syncModeButtons();
  log("Target mode set to SENSORTILE USB", "info");
  if (running) {
    send({ command: "start", mode: "real" });
  }
});

dom.btnMic.addEventListener("click", () => {
  mode = "mic";
  syncModeButtons();
  log("Target mode set to PC BUILT-IN MIC", "info");
  if (running) {
    send({ command: "start", mode: "mic" });
  }
});

dom.btnMock.addEventListener("click", () => {
  mode = "mock";
  syncModeButtons();
  log("Target mode set to MOCK SIMULATION", "info");
  if (running) {
    send({ command: "start", mode: "mock" });
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// Init
// ══════════════════════════════════════════════════════════════════════════════

// Populate API key input if stored or set in gemini_key
const initialKey = getEffectiveGeminiKey();
if (initialKey) {
  if (dom.inputApiKey) dom.inputApiKey.value = initialKey;
  if (dom.inputAlertKey) dom.inputAlertKey.value = initialKey;
}

drawPitchContour();
setSystemState("SYSTEM PAUSED", "paused");
connect();
