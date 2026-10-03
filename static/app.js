/**
 * S.P.I.D.Y AI Voice Assistant - Frontend Core JavaScript v6.2.1
 * Handles Web Canvas, Audio Waveforms, Browser Mic, Whisper ASR,
 * Chat Messaging, Dynamic State, TTS, and V6 Session Management.
 */

// â”€â”€ Session Management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
let conversationId = 'sess_' + Date.now();

window.newConversation = function() {
  // Clear server-side history for old session
  fetch(`/api/conversations/${conversationId}`, { method: 'DELETE' }).catch(() => {});
  // Generate new session
  conversationId = 'sess_' + Date.now();
  const cb = getEl('cb');
  if (cb) {
    cb.innerHTML = '<div class="msg s-msg"><span class="msg-who">Spidey v6</span><div class="msg-text">New conversation started. Previous context cleared. How can I help you?</div></div>';
  }
  speak('New conversation started. How can I help you?');
};

// Safe element getters
const getEl = id => document.getElementById(id);

// Canvas & Web Background
const webCanvas = getEl('webCanvas');
let wctx = webCanvas ? webCanvas.getContext('2d') : null;

function resizeWeb() {
  if (!webCanvas || !wctx) return;
  webCanvas.width = window.innerWidth;
  webCanvas.height = window.innerHeight;
  drawWeb();
}

function drawWeb() {
  if (!webCanvas || !wctx) return;
  wctx.clearRect(0, 0, webCanvas.width, webCanvas.height);
  const cx = webCanvas.width / 2;
  const cy = webCanvas.height / 2;
  const maxR = Math.max(webCanvas.width, webCanvas.height);
  wctx.strokeStyle = 'rgba(204, 0, 0, 0.4)';
  wctx.lineWidth = 0.5;

  const spokes = 18;
  for (let i = 0; i < spokes; i++) {
    const angle = (i / spokes) * Math.PI * 2;
    wctx.beginPath();
    wctx.moveTo(cx, cy);
    wctx.lineTo(cx + Math.cos(angle) * maxR, cy + Math.sin(angle) * maxR);
    wctx.stroke();
  }

  const rings = 12;
  for (let r = 1; r <= rings; r++) {
    const radius = (r / rings) * maxR * 0.75;
    wctx.beginPath();
    for (let j = 0; j <= spokes; j++) {
      const a = (j / spokes) * Math.PI * 2;
      const x = cx + Math.cos(a) * radius;
      const y = cy + Math.sin(a) * radius;
      if (j === 0) wctx.moveTo(x, y);
      else wctx.lineTo(x, y);
    }
    wctx.closePath();
    wctx.stroke();
  }
}

if (webCanvas) {
  resizeWeb();
  window.addEventListener('resize', resizeWeb);
}

// Boot Sequence
const bootMessages = [
  'Initializing S.P.I.D.Y core...',
  'Connecting Groq AI brain...',
  'Loading Spider-Man protocols...',
  'Calibrating Whisper ASR & intent detection...',
  'Systems online. Ready to swing into action!'
];

let bootStep = 0;
function runBoot() {
  const bf = getEl('bf') || getEl('bootFill');
  const bs = getEl('bs') || getEl('bootStatus');
  const bootScreen = getEl('bootScreen');
  const mainUI = getEl('mainUI');

  if (!bootScreen) {
    if (mainUI) mainUI.classList.remove('hidden');
    startSystem();
    return;
  }

  if (bootStep >= bootMessages.length) {
    setTimeout(() => {
      bootScreen.style.opacity = '0';
      setTimeout(() => {
        bootScreen.style.display = 'none';
        if (mainUI) mainUI.classList.remove('hidden');
        startSystem();
        speak("Spidey online. Ready for your commands.");
      }, 700);
    }, 300);
    return;
  }

  if (bs) bs.textContent = bootMessages[bootStep];
  if (bf) bf.style.width = (((bootStep + 1) / bootMessages.length) * 100) + '%';
  bootStep++;
  setTimeout(runBoot, 420);
}
setTimeout(runBoot, 350);

// Waveform Visualization
const waveCanvas = getEl('waveCanvas');
const wctx2 = waveCanvas ? waveCanvas.getContext('2d') : null;
let waveAmp = 3;
let waveColor = 'rgba(204, 0, 0, 0.55)';

function drawWave() {
  if (!waveCanvas || !wctx2) return;
  const parentW = waveCanvas.parentElement ? waveCanvas.parentElement.offsetWidth - 28 : 600;
  waveCanvas.width = parentW > 0 ? parentW : 600;
  const w = waveCanvas.width;
  const h = waveCanvas.height || 50;

  wctx2.clearRect(0, 0, w, h);
  const t = Date.now() / 1000;
  wctx2.beginPath();
  wctx2.strokeStyle = waveColor;
  wctx2.lineWidth = 2;

  for (let x = 0; x < w; x++) {
    const y = (h / 2) + Math.sin(x * 0.04 + t * 2) * waveAmp
      + Math.sin(x * 0.015 + t * 1.3) * (waveAmp * 0.6)
      + Math.sin(x * 0.008 + t * 0.8) * (waveAmp * 0.3);
    if (x === 0) wctx2.moveTo(x, y);
    else wctx2.lineTo(x, y);
  }
  wctx2.stroke();
  requestAnimationFrame(drawWave);
}

function setWave(amp, color) {
  waveAmp = amp;
  waveColor = color || 'rgba(204, 0, 0, 0.55)';
}

// Clock & Diagnostics
function startClock() {
  function tick() {
    const now = new Date();
    const sbTime = getEl('sbTime');
    const sbDate = getEl('sbDate');
    if (sbTime) sbTime.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    if (sbDate) sbDate.textContent = now.toLocaleDateString([], { day: 'numeric', month: 'short' });
  }
  tick();
  setInterval(tick, 1000);
}

// System Startup Initiation
function startSystem() {
  drawWave();
  startClock();
  loadPanels();
}

// Dynamic UI State Management
let cmdCount = 0;
function setState(s) {
  const orb = getEl('orb') || getEl('mainOrb');
  const os = getEl('orbState');
  const ol = getEl('ol') || getEl('orbLabel');
  const wl = getEl('waveLbl');
  const ss = getEl('sbStatus');
  const info = getEl('infoBar');

  if (orb) orb.className = 'orb';

  if (s === 'listening') {
    if (orb) orb.classList.add('listening');
    if (os) os.textContent = 'LISTENING';
    if (ol) ol.textContent = 'Listening to voice...';
    if (wl) wl.textContent = 'VOICE INPUT';
    setWave(28, 'rgba(220, 0, 0, 0.85)');
    if (ss) ss.textContent = 'Listening';
    if (info) info.innerHTML = 'Status: <span style="color:#ff4444">Listening to speech...</span>';
  } else if (s === 'thinking') {
    if (orb) orb.classList.add('thinking');
    if (os) os.textContent = 'THINKING';
    if (ol) ol.textContent = 'Processing...';
    if (wl) wl.textContent = 'AI PROCESSING';
    setWave(14, 'rgba(0, 87, 168, 0.65)');
    if (ss) ss.textContent = 'Processing';
    if (info) info.innerHTML = 'Status: <span style="color:#1a7fd4">🧠 Thinking...</span>';
  } else if (s === 'searching') {
    if (orb) orb.classList.add('thinking');
    if (os) os.textContent = 'SEARCHING';
    if (ol) ol.textContent = 'Searching web...';
    if (wl) wl.textContent = 'WEB SEARCH';
    setWave(18, 'rgba(0, 168, 100, 0.7)');
    if (ss) ss.textContent = 'Searching';
    if (info) info.innerHTML = 'Status: <span style="color:#00a864">🌐 Checking current information...</span>';
  } else if (s === 'tool') {
    if (orb) orb.classList.add('thinking');
    if (os) os.textContent = 'EXECUTING';
    if (ol) ol.textContent = 'Running tool...';
    if (wl) wl.textContent = 'TOOL USE';
    setWave(12, 'rgba(168, 100, 0, 0.7)');
    if (ss) ss.textContent = 'Executing';
    if (info) info.innerHTML = 'Status: <span style="color:#a86400">⚙️ Executing action...</span>';
  } else if (s === 'speaking') {
    if (orb) orb.classList.add('speaking');
    if (os) os.textContent = 'SPEAKING';
    if (ol) ol.textContent = 'Speaking...';
    if (wl) wl.textContent = 'VOICE OUTPUT';
    setWave(20, 'rgba(26, 127, 212, 0.7)');
    if (ss) ss.textContent = 'Speaking';
    if (info) info.innerHTML = 'Status: <span style="color:#1a7fd4">Speaking...</span>';
  } else {
    if (os) os.textContent = 'READY';
    if (ol) ol.textContent = 'Click mic or orb to talk';
    if (wl) wl.textContent = 'IDLE';
    setWave(3, 'rgba(204, 0, 0, 0.55)');
    if (ss) ss.textContent = 'Standby';
    if (info) info.innerHTML = 'Status: <span>Ready — System Commands Active</span>';
  }
}

// Notes & Reminders Panels
function loadPanels() {
  fetch('/api/notes')
    .then(r => r.json())
    .then(data => {
      const el = getEl('notesList');
      if (!el) return;
      const notes = data.notes || (Array.isArray(data) ? data : []);
      if (!notes || notes.length === 0) {
        el.innerHTML = '<span class="panel-empty">No notes yet. Say "note [text]"</span>';
        return;
      }
      el.innerHTML = notes.slice(-4).map(n => `<div class="panel-item">${escapeHtml(n.text)}</div>`).join('');
    })
    .catch(() => {});

  fetch('/api/reminders')
    .then(r => r.json())
    .then(data => {
      const el = getEl('remindersList');
      if (!el) return;
      const rems = data.reminders || (Array.isArray(data) ? data : []);
      if (!rems || rems.length === 0) {
        el.innerHTML = '<span class="panel-empty">No reminders. Say "remind me..."</span>';
        return;
      }
      el.innerHTML = rems.map(r => `<div class="panel-item">${escapeHtml(r.text)} — ${escapeHtml(r.time)}</div>`).join('');
    })
    .catch(() => {});
}

// Chat Formatting & Code Highlights
function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatMsg(txt) {
  if (!txt) return '';
  txt = txt.replace(/```(\w+)\s*Copy\s*/gi, '```$1\n');
  txt = txt.replace(/(\w+)Copy\s*\n/g, '```$1\n');

  txt = txt.replace(/```(\w+)?\n?([\s\S]*?)```/g, (match, lang, code) => {
    const id = 'code_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
    const langLabel = lang || 'code';
    const escaped = escapeHtml(code.trim());
    return `<div class="code-block"><div class="code-header"><span class="code-lang">${langLabel}</span><button class="copy-btn" onclick="copyCode('${id}')">Copy</button></div><pre id="${id}"><code>${escaped}</code></pre></div>`;
  });

  txt = txt.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
  txt = txt.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  txt = txt.replace(/^[-•]\s(.+)/gm, '<div style="padding-left:12px;margin:2px 0">• $1</div>');
  txt = txt.replace(/\n/g, '<br>');
  return txt;
}

window.copyCode = function(id) {
  const el = getEl(id);
  if (el) {
    navigator.clipboard.writeText(el.innerText).then(() => {
      const btn = el.parentElement ? el.parentElement.querySelector('.copy-btn') : null;
      if (btn) {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
      }
    });
  }
};

function addMsg(who, txt) {
  const cb = getEl('cb') || getEl('chatBox');
  if (!cb) return;

  const d = document.createElement('div');
  const isSpidy = (who === 'SPIDY' || who === 'S.P.I.D.Y');
  d.className = 'msg ' + (isSpidy ? 's-msg' : 'u-msg');
  const formatted = isSpidy ? formatMsg(txt) : escapeHtml(txt);
  d.innerHTML = `<span class="msg-who">${isSpidy ? 'Spidey' : 'YOU'}</span><div class="msg-text">${formatted}</div>`;
  cb.appendChild(d);
  cb.scrollTop = cb.scrollHeight;
}

// Sources panel — shown below AI replies when web search is used
function addSources(sources) {
  if (!sources || sources.length === 0) return;
  const cb = getEl('cb');
  if (!cb) return;
  const d = document.createElement('div');
  d.className = 'msg s-msg sources-msg';
  const links = sources.slice(0, 4).map(s =>
    `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer"
        style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;
               background:rgba(204,0,0,0.12);border:1px solid rgba(204,0,0,0.3);
               border-radius:4px;color:#cc4444;font-size:11px;text-decoration:none">
       🔗 ${escapeHtml(s.title || s.source)}
     </a>`
  ).join('');
  d.innerHTML = `<span class="msg-who" style="color:#888;font-size:10px">Sources</span>
    <div class="msg-text" style="font-size:11px">${links}</div>`;
  cb.appendChild(d);
  cb.scrollTop = cb.scrollHeight;
}

function showTyping() {
  const cb = getEl('cb') || getEl('chatBox');
  if (!cb) return;
  const d = document.createElement('div');
  d.className = 'msg s-msg';
  d.id = 'td';
  d.innerHTML = '<span class="msg-who">Spidey</span><span class="msg-text tdots"><span></span><span></span><span></span></span>';
  cb.appendChild(d);
  cb.scrollTop = cb.scrollHeight;
}

function hideTyping() {
  const t = getEl('td');
  if (t) t.remove();
}

// Send Text to Backend
async function handleSend(txt) {
  const text = (txt || '').trim();
  if (!text) return;

  addMsg('YOU', text);
  const ti = getEl('ti') || getEl('textInput');
  if (ti && ti.value === txt) ti.value = '';

  cmdCount++;
  const sbCmds = getEl('sbCmds');
  if (sbCmds) sbCmds.textContent = cmdCount;

  setState('thinking');
  showTyping();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, conversation_id: conversationId })
    });

    const data = await res.json();
    hideTyping();

    const reply = data.reply || 'Something went wrong. Please try again.';
    addMsg('SPIDY', reply);

    // Show sources panel if web search was used
    if (data.sources && data.sources.length > 0) {
      addSources(data.sources);
    }

    // Show tool action indicator if any
    if (data.action) {
      const info = getEl('infoBar');
      if (info) info.innerHTML = `Status: <span style="color:#a86400">⚙️ ${escapeHtml(data.action)}</span>`;
      setTimeout(() => setState('ready'), 3000);
    }

    if (data.action === 'open_url' && data.url) {
      window.open(data.url, '_blank');
    }

    const tl = text.toLowerCase();
    if (tl.includes('note') || tl.includes('remind')) {
      setTimeout(loadPanels, 400);
    }

    setState('speaking');
    speak(reply, () => { setState('ready'); });

  } catch (err) {
    hideTyping();
    addMsg('SPIDY', 'Connection error. Make sure the Spidey server is running.');
    setState('ready');
  }
}

window.send = function() {
  const ti = getEl('ti') || getEl('textInput');
  if (ti) handleSend(ti.value);
};

window.sendQ = function(t) {
  handleSend(t);
};

window.orbClick = function() {
  toggleWhisper();
};

// ============================================================
// BROWSER MICROPHONE (Web Speech API)
// ============================================================
let recog = null;
let isListening = false;
let wakeActive = false;

window.toggleMic = function() {
  if (isListening) stopMic();
  else startMic();
};

function startMic() {
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
    addMsg('SPIDY', 'Browser voice recognition is not supported in this browser. Please use Chrome or use the Whisper button!');
    return;
  }
  if (isListening) return;

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recog = new SR();
  recog.lang = 'en-US';
  recog.interimResults = false;
  recog.maxAlternatives = 1;
  recog.continuous = false;

  recog.onstart = function() {
    isListening = true;
    const mb = getEl('mb');
    if (mb) mb.classList.add('active');
    setState('listening');
  };

  recog.onresult = function(e) {
    const transcript = e.results[0][0].transcript;
    if (transcript && transcript.trim()) {
      handleSend(transcript.trim());
    }
  };

  recog.onerror = function(e) {
    isListening = false;
    const mb = getEl('mb');
    if (mb) mb.classList.remove('active');
    setState('ready');
    if (e.error === 'not-allowed') {
      addMsg('SPIDY', 'Microphone access denied! Allow microphone permissions in your browser.');
    }
  };

  recog.onend = function() {
    isListening = false;
    const mb = getEl('mb');
    if (mb) mb.classList.remove('active');
    setState('ready');
    if (wakeActive) setTimeout(startMic, 800);
  };

  try {
    recog.start();
  } catch (e) {
    isListening = false;
    setState('ready');
  }
}

function stopMic() {
  wakeActive = false;
  const tog = getEl('wakeToggle');
  const lbl = getEl('wakeLabel');
  if (tog) tog.classList.remove('on');
  if (lbl) lbl.textContent = 'Wake: OFF';

  isListening = false;
  if (recog) {
    try { recog.abort(); } catch (e) {}
  }
  recog = null;
  const mb = getEl('mb');
  if (mb) mb.classList.remove('active');
  setState('ready');
}

window.toggleWake = function() {
  wakeActive = !wakeActive;
  const tog = getEl('wakeToggle');
  const lbl = getEl('wakeLabel');
  if (wakeActive) {
    if (tog) tog.classList.add('on');
    if (lbl) lbl.textContent = 'Wake: ON';
    addMsg('SPIDY', 'Wake mode ON! Continuously listening for your commands.');
    if (!isListening) startMic();
  } else {
    if (tog) tog.classList.remove('on');
    if (lbl) lbl.textContent = 'Wake: OFF';
    if (isListening) stopMic();
    addMsg('SPIDY', 'Wake mode OFF. Click microphone to talk.');
  }
};

// ============================================================
// OPENAI WHISPER ASR (GPU-Accelerated High Accuracy)
// ============================================================
let whisperRecorder = null;
let whisperChunks = [];
let isWhisperRecording = false;

window.toggleWhisper = function() {
  if (isWhisperRecording) stopWhisper();
  else startWhisper();
};

async function startWhisper() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    addMsg('SPIDY', 'Microphone recording API is not supported in this browser.');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    whisperChunks = [];

    let mimeType = 'audio/webm';
    if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
      mimeType = 'audio/webm;codecs=opus';
    }

    whisperRecorder = new MediaRecorder(stream, { mimeType: mimeType });

    whisperRecorder.ondataavailable = function(e) {
      if (e.data && e.data.size > 0) whisperChunks.push(e.data);
    };

    whisperRecorder.onstop = async function() {
      stream.getTracks().forEach(t => t.stop());
      const audioBlob = new Blob(whisperChunks, { type: whisperRecorder.mimeType || 'audio/webm' });
      await sendAudioToWhisper(audioBlob);
    };

    whisperRecorder.start();
    isWhisperRecording = true;

    const wb = getEl('wb');
    if (wb) wb.classList.add('active');
    setState('listening');

    const ol = getEl('ol') || getEl('orbLabel');
    if (ol) ol.textContent = 'Whisper recording... click to stop';

    const info = getEl('infoBar');
    if (info) info.innerHTML = 'Status: <span style="color:#a855f7">Whisper ASR recording...</span>';

  } catch (err) {
    addMsg('SPIDY', 'Microphone access denied. Please allow microphone permissions.');
    setState('ready');
  }
}

function stopWhisper() {
  if (whisperRecorder && isWhisperRecording) {
    isWhisperRecording = false;
    const wb = getEl('wb');
    if (wb) wb.classList.remove('active');

    setState('thinking');
    const ol = getEl('ol') || getEl('orbLabel');
    if (ol) ol.textContent = 'Whisper transcribing...';

    const info = getEl('infoBar');
    if (info) info.innerHTML = 'Status: <span style="color:#a855f7">Whisper AI transcribing... please wait</span>';

    setTimeout(() => {
      if (whisperRecorder.state !== 'inactive') {
        whisperRecorder.stop();
      }
    }, 250);
  }
}

async function sendAudioToWhisper(audioBlob) {
  try {
    if (!audioBlob || audioBlob.size < 100) {
      addMsg('SPIDY', 'Recording too short or silent. Please try speaking again.');
      setState('ready');
      return;
    }

    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('language', 'auto');

    const res = await fetch('/api/whisper/transcribe', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    const transcript = (data.text || '').trim();

    if (transcript) {
      // Log Whisper result to browser console only — not shown in chat UI
      console.log('Whisper heard:', transcript);
      await handleSend(transcript);
    } else {
      addMsg('SPIDY', data.message || 'Whisper could not hear any speech clearly. Please try again!');
      setState('ready');
    }

  } catch (err) {
    addMsg('SPIDY', `Whisper transcription error: ${err.message}`);
    setState('ready');
  }
}

// Text-to-Speech (TTS)
function speak(txt, callback) {
  if (!('speechSynthesis' in window)) {
    if (callback) callback();
    return;
  }

  window.speechSynthesis.cancel();
  const clean = txt.replace(/[🕷️🕸️⚡▶️🕐]/g, '').trim();
  const u = new SpeechSynthesisUtterance(clean);
  u.rate = 1.05;
  u.pitch = 0.92;
  u.volume = 1.0;

  const vs = window.speechSynthesis.getVoices();
  const pref = vs.find(v => v.name.includes('Google') && v.lang === 'en-US')
    || vs.find(v => v.lang === 'en-US');
  if (pref) u.voice = pref;

  u.onend = () => { if (callback) callback(); };
  u.onerror = () => { if (callback) callback(); };
  window.speechSynthesis.speak(u);
}

window.speechSynthesis.onvoiceschanged = () => {};

// Periodic Refresh
setInterval(loadPanels, 30000);

