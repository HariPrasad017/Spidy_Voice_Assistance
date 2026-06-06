// ---- WEB CANVAS BACKGROUND ----
const webCanvas = document.getElementById('webCanvas');
const wctx = webCanvas.getContext('2d');
 
function resizeWeb() {
  webCanvas.width = window.innerWidth;
  webCanvas.height = window.innerHeight;
}
resizeWeb();
window.addEventListener('resize', resizeWeb);
 
function drawWeb() {
  wctx.clearRect(0, 0, webCanvas.width, webCanvas.height);
  const cx = webCanvas.width / 2;
  const cy = webCanvas.height / 2;
  const maxR = Math.max(webCanvas.width, webCanvas.height);
  wctx.strokeStyle = 'rgba(204,0,0,0.4)';
  wctx.lineWidth = 0.5;
  const spokes = 16;
  for (let i = 0; i < spokes; i++) {
    const angle = (i / spokes) * Math.PI * 2;
    wctx.beginPath();
    wctx.moveTo(cx, cy);
    wctx.lineTo(cx + Math.cos(angle) * maxR, cy + Math.sin(angle) * maxR);
    wctx.stroke();
  }
  const rings = 12;
  for (let r = 1; r <= rings; r++) {
    const radius = (r / rings) * maxR * 0.8;
    wctx.beginPath();
    for (let i = 0; i < spokes; i++) {
      const a1 = (i / spokes) * Math.PI * 2;
      const a2 = ((i + 1) / spokes) * Math.PI * 2;
      const x1 = cx + Math.cos(a1) * radius;
      const y1 = cy + Math.sin(a1) * radius;
      const x2 = cx + Math.cos(a2) * radius;
      const y2 = cy + Math.sin(a2) * radius;
      if (i === 0) wctx.moveTo(x1, y1);
      wctx.lineTo(x2, y2);
    }
    wctx.closePath();
    wctx.stroke();
  }
}
drawWeb();
 
// ---- BOOT SEQUENCE ----
const bootMessages = [
  'Initializing S.P.I.D.Y core...',
  'Connecting to web network...',
  'Loading Spider-Man protocols...',
  'Calibrating spider-sense...',
  'Activating AI brain...',
  'Systems online. Welcome back!'
];
 
const bootFill = document.getElementById('bootFill');
const bootStatus = document.getElementById('bootStatus');
const bootScreen = document.getElementById('bootScreen');
const mainUI = document.getElementById('mainUI');
 
let bootStep = 0;
function runBoot() {
  if (bootStep >= bootMessages.length) {
    setTimeout(() => {
      bootScreen.style.opacity = '0';
      setTimeout(() => {
        bootScreen.style.display = 'none';
        mainUI.classList.remove('hidden');
        startWaveform();
      }, 800);
    }, 400);
    return;
  }
  bootStatus.textContent = bootMessages[bootStep];
  bootFill.style.width = ((bootStep + 1) / bootMessages.length * 100) + '%';
  bootStep++;
  setTimeout(runBoot, 480);
}
setTimeout(runBoot, 400);
 
// ---- WAVEFORM ----
const waveCanvas = document.getElementById('waveCanvas');
const wctx2 = waveCanvas.getContext('2d');
let waveActive = false;
let waveAnim;
let waveAmplitude = 4;
 
function drawWaveIdle() {
  const w = waveCanvas.width;
  const h = waveCanvas.height;
  wctx2.clearRect(0, 0, w, h);
  const t = Date.now() / 1000;
  wctx2.beginPath();
  wctx2.strokeStyle = 'rgba(204,0,0,0.5)';
  wctx2.lineWidth = 2;
  for (let x = 0; x < w; x++) {
    const y = h / 2 + Math.sin(x * 0.04 + t * 2) * waveAmplitude
                    + Math.sin(x * 0.01 + t) * (waveAmplitude * 0.5);
    if (x === 0) wctx2.moveTo(x, y);
    else wctx2.lineTo(x, y);
  }
  wctx2.stroke();
  waveAnim = requestAnimationFrame(drawWaveIdle);
}
 
function startWaveform() {
  waveActive = true;
  drawWaveIdle();
}
 
function setWaveAmplitude(amp) {
  waveAmplitude = amp;
}
 
// ---- CHAT ----
const chatBox = document.getElementById('chatBox');
const textInput = document.getElementById('textInput');
const sendBtn = document.getElementById('sendBtn');
const micBtn = document.getElementById('micBtn');
const orbLabel = document.getElementById('orbLabel');
const mainOrb = document.getElementById('mainOrb');
 
function addMessage(who, text) {
  const div = document.createElement('div');
  div.className = `msg ${who === 'SPIDY' ? 'spidy-msg' : 'user-msg'}`;
  div.innerHTML = `
    <span class="msg-who">${who}</span>
    <span class="msg-text">${text}</span>
  `;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}
 
function showTyping() {
  const div = document.createElement('div');
  div.className = 'msg spidy-msg';
  div.id = 'typingDiv';
  div.innerHTML = `
    <span class="msg-who">S.P.I.D.Y</span>
    <span class="msg-text typing-dots"><span></span><span></span><span></span></span>
  `;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}
 
function removeTyping() {
  const t = document.getElementById('typingDiv');
  if (t) t.remove();
}
 
// Local response engine (Phase 3 la Gemini replace pannuvom)
function getSpidyResponse(input) {
  const q = input.toLowerCase();
  if (q.includes('time')) {
    return `It's ${new Date().toLocaleTimeString()} — time flies when you're web-slinging!`;
  }
  if (q.includes('date')) {
    return `Today is ${new Date().toLocaleDateString('en-IN', {weekday:'long',year:'numeric',month:'long',day:'numeric'})}.`;
  }
  if (q.includes('youtube')) {
    window.open('https://youtube.com', '_blank');
    return `Opening YouTube! Probably searching for Spider-Man clips, right? 🕷️`;
  }
  if (q.includes('google')) {
    window.open('https://google.com', '_blank');
    return `Google is open! Even Spider-Man Googles things sometimes.`;
  }
  if (q.includes('quote') || q.includes('spider')) {
    const quotes = [
      "With great power comes great responsibility. — Uncle Ben",
      "I'm Spider-Man. I stop bad guys.",
      "Anyone can wear the mask.",
      "If you help everyone, you can save everyone.",
      "Whatever life holds in store for me, I will never forget these words: With great power comes great responsibility."
    ];
    return quotes[Math.floor(Math.random() * quotes.length)];
  }
  if (q.includes('marvel') || q.includes('trivia')) {
    const trivia = [
      "Spider-Man first appeared in Amazing Fantasy #15 in 1962!",
      "Peter Parker was bitten by a radioactive spider at age 15.",
      "Miles Morales is also Spider-Man in the Ultimate universe!",
      "Spider-Man can lift up to 10 tons!",
      "The Sinister Six was formed by Doctor Octopus to destroy Spider-Man."
    ];
    return trivia[Math.floor(Math.random() * trivia.length)];
  }
  if (q.includes('hello') || q.includes('hi') || q.includes('hey')) {
    return "Hey there! S.P.I.D.Y online and ready. Your friendly neighborhood AI at your service! 🕸️";
  }
  if (q.includes('who are you') || q.includes('what are you')) {
    return "I'm S.P.I.D.Y — Spider-Man Personal Intelligence Digital Yield-system. Think JARVIS, but cooler and in red & blue. Built for you, wall-crawler!";
  }
  if (q.includes('name')) {
    return "S.P.I.D.Y — Spider-Man Personal Intelligence Digital Yield-system. Phase 3 la full AI brain add pannuvom!";
  }
  return `Received: "${input}". Phase 3 la Gemini AI connect panna porom — then I'll be fully intelligent! 🕷️`;
}
 
async function handleSend(text) {
  if (!text.trim()) return;
  addMessage('YOU', text);
  textInput.value = '';
  setWaveAmplitude(18);
  orbLabel.textContent = 'Processing';
  mainOrb.classList.add('listening');
  showTyping();
 
  await new Promise(r => setTimeout(r, 800 + Math.random() * 600));
  removeTyping();
 
  const reply = getSpidyResponse(text);
  addMessage('S.P.I.D.Y', reply);
  speak(reply);
  setWaveAmplitude(4);
  orbLabel.textContent = 'Ready';
  mainOrb.classList.remove('listening');
}
 
sendBtn.addEventListener('click', () => handleSend(textInput.value));
textInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleSend(textInput.value); });
 
function sendQuick(text) { handleSend(text); }
 
// ---- VOICE INPUT ----
let recognition;
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.onresult = e => {
    const transcript = e.results[0][0].transcript;
    handleSend(transcript);
  };
  recognition.onend = () => {
    micBtn.classList.remove('active');
    orbLabel.textContent = 'Ready';
    setWaveAmplitude(4);
  };
}
 
micBtn.addEventListener('click', () => {
  if (!recognition) {
    addMessage('S.P.I.D.Y', 'Voice not supported in this browser. Try Chrome! 🕷️');
    return;
  }
  micBtn.classList.add('active');
  orbLabel.textContent = 'Listening...';
  setWaveAmplitude(24);
  recognition.start();
});
 
// ---- TTS ----
function speak(text) {
  if ('speechSynthesis' in window) {
    const clean = text.replace(/[🕷️🕸️⚡▶️🕐]/g, '');
    const utt = new SpeechSynthesisUtterance(clean);
    utt.rate = 1.0;
    utt.pitch = 0.9;
    utt.volume = 1.0;
    const voices = speechSynthesis.getVoices();
    const pref = voices.find(v => v.name.includes('Google') && v.lang === 'en-US')
               || voices.find(v => v.lang === 'en-US');
    if (pref) utt.voice = pref;
    speechSynthesis.speak(utt);
  }
}
 
speechSynthesis.onvoiceschanged = () => {};