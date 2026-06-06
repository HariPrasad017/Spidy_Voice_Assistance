from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq
import os, subprocess, json, datetime, threading, time, platform, requests

# Import HuggingFace Intent Detector
try:
    from intent_detector import intent_detector
    INTENT_AVAILABLE = True
    print("Intent detector module loaded!")
except Exception as e:
    INTENT_AVAILABLE = False
    intent_detector = None
    print(f"Intent detector not available: {e}")

# Import PyTorch Sentiment Analyzer
try:
    from sentiment_analyzer import sentiment_analyzer as pytorch_sentiment
    SENTIMENT_AVAILABLE = True
    print("PyTorch Sentiment Analyzer loaded!")
except Exception as e:
    SENTIMENT_AVAILABLE = False
    pytorch_sentiment = None
    print(f"Sentiment analyzer not available: {e}")

# Import Whisper ASR
try:
    from whisper_asr import whisper_asr
    WHISPER_AVAILABLE = True
    print("Whisper ASR module loaded!")
except Exception as e:
    WHISPER_AVAILABLE = False
    whisper_asr = None
    print(f"Whisper ASR not available: {e}")

# Legacy sentiment (fallback)
sentiment_analyzer = None
def load_legacy_sentiment():
    global sentiment_analyzer
    try:
        from transformers import pipeline
        sentiment_analyzer = pipeline('sentiment-analysis', model='distilbert-base-uncased-finetuned-sst-2-english')
    except:
        pass
threading.Thread(target=load_legacy_sentiment, daemon=True).start()

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='')
client = Groq(api_key=os.getenv('GROQ_API_KEY'))

# ===== DATA STORAGE =====
NOTES_FILE = 'spidy_notes.json'
REMINDERS_FILE = 'spidy_reminders.json'

def load_json(file):
    try:
        if os.path.exists(file):
            with open(file, 'r') as f:
                return json.load(f)
    except:
        pass
    return []

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

# ===== SYSTEM COMMANDS =====
def open_app(app_name):
    apps = {
        'chrome': 'start chrome',
        'google chrome': 'start chrome',
        'edge': r'start msedge',
        'microsoft edge': r'start msedge',
        'notepad': 'start notepad',
        'calculator': 'start calc',
        'calc': 'start calc',
        'vs code': 'code .',
        'vscode': 'code .',
        'visual studio code': 'code .',
        'file explorer': 'start explorer',
        'explorer': 'start explorer',
        'my computer': 'start explorer',
        'paint': 'start mspaint',
        'word': 'start winword',
        'excel': 'start excel',
        'powerpoint': 'start powerpnt',
        'cmd': 'start cmd',
        'command prompt': 'start cmd',
        'terminal': 'start wt || start cmd',
        'task manager': 'start taskmgr',
        'settings': 'start ms-settings:',
        'camera': 'start microsoft.windows.camera:',
        'spotify': 'start spotify:',
        'discord': 'start discord:',
        'whatsapp': 'start whatsapp:',
        'vlc': 'start vlc',
        'zoom': 'start zoom:',
        'teams': 'start msteams:',
    }
    for key, cmd in apps.items():
        if key in app_name.lower():
            subprocess.Popen(cmd, shell=True)
            return f"Opening {key.title()}!"
    subprocess.Popen(f'start {app_name}', shell=True)
    return f"Trying to open {app_name}!"

def take_screenshot():
    try:
        from PIL import ImageGrab
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        path = os.path.join(desktop, f'SPIDY_screenshot_{timestamp}.png')
        screenshot = ImageGrab.grab()
        screenshot.save(path)
        return f"Screenshot saved to Desktop as SPIDY_screenshot_{timestamp}.png!"
    except Exception as e:
        return f"Screenshot failed: {str(e)}"

def control_volume(action, level=None):
    try:
        import pythoncom
        pythoncom.CoInitialize()
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))

        if action == 'mute':
            volume.SetMute(1, None)
            return "Volume muted!"
        elif action == 'unmute':
            volume.SetMute(0, None)
            return "Volume unmuted!"
        elif action == 'set' and level is not None:
            vol = max(0.0, min(1.0, float(level) / 100.0))
            volume.SetMasterVolumeLevelScalar(vol, None)
            cur = int(volume.GetMasterVolumeLevelScalar() * 100)
            return f"Volume set to {cur}%!"
        elif action == 'up':
            cur = volume.GetMasterVolumeLevelScalar()
            new = min(1.0, cur + 0.1)
            volume.SetMasterVolumeLevelScalar(new, None)
            return f"Volume increased to {int(new*100)}%!"
        elif action == 'down':
            cur = volume.GetMasterVolumeLevelScalar()
            new = max(0.0, cur - 0.1)
            volume.SetMasterVolumeLevelScalar(new, None)
            return f"Volume decreased to {int(new*100)}%!"
    except Exception as e:
        # Fallback — PowerShell keyboard simulation
        if action == 'up':
            subprocess.run('powershell -c "$wsh = New-Object -ComObject WScript.Shell; for($i=0;$i -lt 5;$i++){$wsh.SendKeys([char]175)}"', shell=True)
            return "Volume increased!"
        elif action == 'down':
            subprocess.run('powershell -c "$wsh = New-Object -ComObject WScript.Shell; for($i=0;$i -lt 5;$i++){$wsh.SendKeys([char]174)}"', shell=True)
            return "Volume decreased!"
        elif action == 'mute':
            subprocess.run('powershell -c "$wsh = New-Object -ComObject WScript.Shell; $wsh.SendKeys([char]173)"', shell=True)
            return "Volume muted!"
        elif action == 'set' and level is not None:
            vol = max(0, min(100, int(float(level))))
            ps = f'powershell -c "Add-Type -TypeDefinition \'using System; public class V {{ [System.Runtime.InteropServices.DllImport(\\"winmm.dll\\")] public static extern int waveOutSetVolume(IntPtr h, uint v); }}\'; $v = [uint32](({vol}/100.0)*65535); [V]::waveOutSetVolume([IntPtr]::Zero, ($v -shl 16) -bor $v)"'
            subprocess.run(ps, shell=True)
            return f"Volume set to {vol}%!"
        return f"Volume error: {str(e)[:50]}"

def control_brightness(action, level=None):
    try:
        import re
        if action == 'set' and level is not None:
            val = max(0, min(100, int(float(level))))
            ps = f'powershell -c "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{val})"'
            subprocess.run(ps, shell=True)
            return f"Brightness set to {val}%!"
        elif action == 'up':
            ps = '''powershell -c "$b=(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness; $n=[math]::Min(100,$b+10); (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,$n); Write-Output $n"'''
            result = subprocess.run(ps, shell=True, capture_output=True, text=True)
            val = result.stdout.strip()
            return f"Brightness increased to {val}%!" if val else "Brightness increased!"
        elif action == 'down':
            ps = '''powershell -c "$b=(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness; $n=[math]::Max(0,$b-10); (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,$n); Write-Output $n"'''
            result = subprocess.run(ps, shell=True, capture_output=True, text=True)
            val = result.stdout.strip()
            return f"Brightness decreased to {val}%!" if val else "Brightness decreased!"
    except Exception as e:
        return f"Brightness control failed: {str(e)[:60]}"

def shutdown_system(action):
    if action == 'shutdown':
        subprocess.Popen('shutdown /s /t 30', shell=True)
        return "System will shut down in 30 seconds! Say 'cancel shutdown' to stop."
    elif action == 'restart':
        subprocess.Popen('shutdown /r /t 30', shell=True)
        return "System will restart in 30 seconds! Say 'cancel restart' to stop."
    elif action == 'cancel':
        subprocess.Popen('shutdown /a', shell=True)
        return "Shutdown/restart cancelled!"
    elif action == 'sleep':
        subprocess.Popen('rundll32.exe powrprof.dll,SetSuspendState 0,1,0', shell=True)
        return "Going to sleep!"
    elif action == 'lock':
        subprocess.Popen('rundll32.exe user32.dll,LockWorkStation', shell=True)
        return "System locked!"

# ===== REMINDER SYSTEM =====
reminders = load_json(REMINDERS_FILE)

def check_reminders():
    while True:
        now = datetime.datetime.now()
        updated = False
        for r in reminders:
            if not r.get('fired') and r.get('time'):
                try:
                    rt = datetime.datetime.strptime(r['time'], '%Y-%m-%d %H:%M')
                    if now >= rt:
                        r['fired'] = True
                        updated = True
                        # Show Windows notification
                        subprocess.Popen(f'msg * "S.P.I.D.Y REMINDER: {r["text"]}"', shell=True)
                except:
                    pass
        if updated:
            save_json(REMINDERS_FILE, reminders)
        time.sleep(30)

threading.Thread(target=check_reminders, daemon=True).start()

# ===== COMMAND PARSER =====
SYSTEM_PROMPT = """You are S.P.I.D.Y (Spider-Man Personal Intelligence Digital Yield-system), a smart voice assistant with Spider-Man's personality. You are like JARVIS but Spider-Man themed.

Rules:
- Keep answers SHORT (2-3 sentences max for voice)
- Be friendly and witty like Peter Parker
- Give accurate factual answers
- Never say you are an AI or ChatGPT — you are S.P.I.D.Y
- Occasionally use spider/web references
- ALWAYS wrap code in triple backticks with language name like ```python or ```java or ```sql
- Never give code without triple backtick formatting

Special modes:
- If user asks for a QUIZ or TEST, generate 1 multiple choice question with 4 options (A,B,C,D)
- If user asks for CODING HELP, give short clear code snippet wrapped in ```language code blocks
- If user seems SAD or STRESSED, be extra supportive and encouraging
- If user asks about CAREER or JOBS, give practical advice

User says: """

def parse_command(msg):
    t = msg.lower().strip()

    # Good morning/evening greeting
    hour = datetime.datetime.now().hour
    if any(x in t for x in ['good morning', 'good evening', 'good night', 'good afternoon', 'hello spidy', 'hi spidy']):
        if hour < 12:
            greeting = "Good morning"
            energy = "Ready to swing into action!"
        elif hour < 17:
            greeting = "Good afternoon"
            energy = "Hope your day is going great!"
        elif hour < 21:
            greeting = "Good evening"
            energy = "Time to wind down like a web-slinger!"
        else:
            greeting = "Good night"
            energy = "Rest well, hero!"
        return f"{greeting}! I'm S.P.I.D.Y, your friendly neighborhood AI. {energy} The time is {datetime.datetime.now().strftime('%I:%M %p')}."

    # Time & Date
    if 'time' in t and 'what' in t:
        return f"It's {datetime.datetime.now().strftime('%I:%M %p')} — time flies when web-slinging!"
    if any(x in t for x in ['what date', 'today date', "what's today", 'what day']):
        return f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}."

    # Brightness control
    if 'brightness' in t:
        import re
        nums = re.findall(r'\d+', t)
        if nums:
            return control_brightness('set', nums[0])
        if any(x in t for x in ['increase', 'up', 'raise', 'higher', 'more']):
            return control_brightness('up')
        if any(x in t for x in ['decrease', 'down', 'lower', 'reduce', 'less', 'dim']):
            return control_brightness('down')
        return control_brightness('up')

    # Screenshot
    if 'screenshot' in t or 'screen shot' in t or 'capture screen' in t:
        return take_screenshot()

    # Volume control
    if 'volume' in t or 'mute' in t or 'unmute' in t:
        import re
        if 'unmute' in t:
            return control_volume('unmute')
        if 'mute' in t and 'un' not in t:
            return control_volume('mute')

        nums = re.findall(r'\d+', t)

        # "increase/raise/up to 50" or "decrease/down/lower to 50" — set exact %
        if nums:
            return control_volume('set', nums[0])

        # No number — direction only
        if any(x in t for x in ['increase', 'up', 'louder', 'raise', 'higher']):
            return control_volume('up')
        if any(x in t for x in ['decrease', 'down', 'lower', 'quieter', 'reduce', 'less']):
            return control_volume('down')
        return control_volume('up')

    # System power
    if 'shut down' in t or 'shutdown' in t:
        return shutdown_system('shutdown')
    if 'restart' in t or 'reboot' in t:
        return shutdown_system('restart')
    if 'cancel shutdown' in t or 'cancel restart' in t:
        return shutdown_system('cancel')
    if 'sleep' in t and ('computer' in t or 'laptop' in t or 'system' in t or 'pc' in t):
        return shutdown_system('sleep')
    if 'lock' in t and ('computer' in t or 'screen' in t or 'laptop' in t):
        return shutdown_system('lock')

    # Open apps
    if t.startswith('open '):
        app_name = t.replace('open ', '').strip()
        # Check if it's a website
        websites = ['youtube', 'google', 'github', 'spotify', 'netflix', 'instagram',
                   'twitter', 'whatsapp', 'gmail', 'maps', 'facebook', 'linkedin']
        for site in websites:
            if site in app_name:
                url_map = {
                    'youtube': 'https://youtube.com',
                    'google': 'https://google.com',
                    'github': 'https://github.com',
                    'spotify': 'https://spotify.com',
                    'netflix': 'https://netflix.com',
                    'instagram': 'https://instagram.com',
                    'twitter': 'https://x.com',
                    'whatsapp': 'https://web.whatsapp.com',
                    'gmail': 'https://mail.google.com',
                    'maps': 'https://maps.google.com',
                    'facebook': 'https://facebook.com',
                    'linkedin': 'https://linkedin.com',
                }
                return {'action': 'open_url', 'url': url_map[site], 'message': f"Opening {site.title()}!"}
        return open_app(app_name)

    # Close apps
    if t.startswith('close '):
        app_name = t.replace('close ', '').strip()
        proc_map = {
            'chrome': 'chrome.exe', 'notepad': 'notepad.exe',
            'calculator': 'calculator.exe', 'spotify': 'spotify.exe',
            'discord': 'discord.exe', 'vs code': 'code.exe', 'vscode': 'code.exe'
        }
        for key, proc in proc_map.items():
            if key in app_name:
                subprocess.Popen(f'taskkill /f /im {proc}', shell=True)
                return f"Closing {key.title()}!"
        subprocess.Popen(f'taskkill /f /im {app_name}.exe', shell=True)
        return f"Trying to close {app_name}!"

    # Search
    if t.startswith('search ') or t.startswith('google '):
        query = t.replace('search ', '').replace('google ', '').strip()
        return {'action': 'open_url', 'url': f'https://google.com/search?q={query}', 'message': f"Searching for: {query}"}

    if t.startswith('play ') or t.startswith('youtube '):
        query = t.replace('play ', '').replace('youtube ', '').strip()
        return {'action': 'open_url', 'url': f'https://youtube.com/results?search_query={query}', 'message': f"Playing {query} on YouTube!"}

    # Notes
    if t.startswith('note ') or t.startswith('save note') or t.startswith('add note'):
        note_text = t.replace('note ', '').replace('save note ', '').replace('add note ', '').strip()
        notes = load_json(NOTES_FILE)
        notes.append({'text': note_text, 'time': datetime.datetime.now().isoformat()})
        save_json(NOTES_FILE, notes)
        return f"Note saved: '{note_text}'"

    if 'show notes' in t or 'my notes' in t or 'read notes' in t:
        notes = load_json(NOTES_FILE)
        if not notes:
            return "No notes saved yet! Say 'note [your text]' to save one."
        recent = notes[-3:]
        texts = [f"{i+1}. {n['text']}" for i, n in enumerate(recent)]
        return "Your recent notes: " + " | ".join(texts)

    if 'clear notes' in t or 'delete notes' in t:
        save_json(NOTES_FILE, [])
        return "All notes cleared!"

    # Reminders
    if 'remind' in t or 'reminder' in t or 'set alarm' in t or 'set reminder' in t:
        import re
        # Extract time from message
        time_patterns = [
            r'(\d{1,2}):(\d{2})\s*(am|pm)',
            r'(\d{1,2})\s*(am|pm)',
            r'in (\d+) (minute|minutes|hour|hours)',
        ]
        reminder_text = t.replace('remind me', '').replace('set reminder', '').replace('set alarm', '').strip()
        reminder_text = re.sub(r'(at|to|for|in)\s+\d+.*', '', reminder_text).strip()
        if not reminder_text:
            reminder_text = "Reminder"

        # Try to parse time
        now = datetime.datetime.now()
        reminder_time = None

        # "in X minutes/hours"
        m = re.search(r'in (\d+) (minute|minutes|hour|hours)', t)
        if m:
            amount = int(m.group(1))
            unit = m.group(2)
            if 'hour' in unit:
                reminder_time = now + datetime.timedelta(hours=amount)
            else:
                reminder_time = now + datetime.timedelta(minutes=amount)

        # "at HH:MM am/pm"
        if not reminder_time:
            m = re.search(r'at (\d{1,2}):(\d{2})\s*(am|pm)?', t)
            if m:
                h, mn = int(m.group(1)), int(m.group(2))
                ampm = m.group(3)
                if ampm == 'pm' and h != 12:
                    h += 12
                reminder_time = now.replace(hour=h, minute=mn, second=0)

        if reminder_time:
            reminders.append({
                'text': reminder_text or 'Reminder',
                'time': reminder_time.strftime('%Y-%m-%d %H:%M'),
                'fired': False
            })
            save_json(REMINDERS_FILE, reminders)
            return f"Reminder set for {reminder_time.strftime('%I:%M %p')}! I'll alert you then."
        else:
            return "When should I remind you? Say like 'remind me in 30 minutes' or 'remind me at 3pm'"

    if 'show reminders' in t or 'my reminders' in t:
        active = [r for r in reminders if not r.get('fired')]
        if not active:
            return "No active reminders!"
        texts = [f"{r['text']} at {r['time']}" for r in active[:3]]
        return "Active reminders: " + " | ".join(texts)

    # File search
    if 'find file' in t or 'search file' in t or 'locate file' in t:
        filename = t.replace('find file', '').replace('search file', '').replace('locate file', '').strip()
        subprocess.Popen(f'explorer /e,/root,C:\\,/select,{filename}', shell=True)
        return {'action': 'open_url', 'url': f'search-ms:query={filename}&crumb=location:C%3A%5C', 'message': f"Searching for {filename}..."}

    # Create folder
    if 'create folder' in t or 'new folder' in t or 'make folder' in t or 'create a folder' in t or 'make a folder' in t:
        import re
        # Detect location
        if 'document' in t or 'documents' in t:
            base_path = os.path.join(os.path.expanduser('~'), 'Documents')
            loc_name = 'Documents'
        elif 'desktop' in t:
            base_path = os.path.join(os.path.expanduser('~'), 'Desktop')
            loc_name = 'Desktop'
        elif 'download' in t:
            base_path = os.path.join(os.path.expanduser('~'), 'Downloads')
            loc_name = 'Downloads'
        else:
            base_path = os.path.join(os.path.expanduser('~'), 'Documents')
            loc_name = 'Documents'

        # Extract folder name — remove action words and location words
        folder_name = t
        for word in ['create', 'new', 'make', 'a', 'folder', 'directory',
                     'in', 'on', 'at', 'the', 'my', 'inside',
                     'document', 'documents', 'desktop', 'download', 'downloads']:
            folder_name = re.sub(r'\b' + word + r'\b', '', folder_name)
        folder_name = folder_name.strip()

        if not folder_name:
            folder_name = f'SPIDY_{datetime.datetime.now().strftime("%d%m%Y_%H%M%S")}'

        full_path = os.path.join(base_path, folder_name)
        os.makedirs(full_path, exist_ok=True)
        subprocess.Popen(f'explorer "{full_path}"', shell=True)
        return f'Folder "{folder_name}" created in {loc_name} and opened!'

    # Weather search
    if 'weather' in t:
        import re
        # Remove common filler words to get location
        location = t
        for word in ['what', 'whats', "what's", 'is', 'the', 'current', 'today', 'weather',
                     'in', 'at', 'for', 'search', 'google', 'check', 'of', 'on', 'show',
                     'tell', 'me', 'find', 'get', 'type', 'go', 'to', 'and']:
            location = re.sub(r'\b' + word + r'\b', '', location)
        location = location.strip()
        if not location:
            location = 'today'
        search_query = f'weather {location}'
        url = f'https://www.google.com/search?q={search_query.replace(" ", "+")}'
        return {'action': 'open_url', 'url': url, 'message': f"Searching weather for {location} on Google!"}

    # Battery status
    if 'battery' in t:
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery:
                status_str = "charging" if battery.power_plugged else "not charging"
                return f"Battery is at {int(battery.percent)}% and {status_str}."
        except:
            pass
        return "Battery info unavailable!"

    # ===== PHASE 5 COMMANDS =====

    # News
    if any(x in t for x in ['news', 'headlines', 'what happened', 'latest news']):
        category = 'general'
        if 'tech' in t or 'technology' in t:
            category = 'technology'
        elif 'sport' in t or 'cricket' in t:
            category = 'sports'
        elif 'business' in t or 'finance' in t:
            category = 'business'
        return {'action': 'open_url', 'url': f'https://news.google.com/search?q={category}+news+india&hl=en-IN', 'message': f"Opening {category} news!"}

    # Real weather using wttr.in
    if 'tell me weather' in t or 'current temperature' in t or ('temperature' in t and 'in' in t):
        import re
        city = t
        for word in ['what', 'whats', "what's", 'is', 'the', 'current', 'today', 'weather',
                     'temperature', 'celsius', 'degrees', 'tell', 'me', 'in', 'at', 'for',
                     'search', 'check', 'of', 'show', 'get', 'find', 'how', 'much']:
            city = re.sub(r'\b' + word + r'\b', '', city)
        city = city.strip() or 'Chennai'
        try:
            r = requests.get(f'https://wttr.in/{city}?format=j1', timeout=5)
            data = r.json()
            current = data['current_condition'][0]
            temp = current['temp_C']
            desc = current['weatherDesc'][0]['value']
            humidity = current['humidity']
            return f"Weather in {city}: {temp}°C, {desc}. Humidity: {humidity}%. Stay safe out there!"
        except:
            return {'action': 'open_url', 'url': f'https://www.google.com/search?q=weather+{city}', 'message': f"Opening weather for {city}!"}

    # Stock price
    if 'stock' in t or 'share price' in t:
        import re
        company = re.sub(r'\b(stock|share|price|market|of|what|is|the|check|tell|me)\b', '', t).strip()
        query = f'{company} stock price NSE' if company else 'NSE BSE stock market today'
        return {'action': 'open_url', 'url': f'https://www.google.com/search?q={query.replace(" ", "+")}', 'message': f"Checking stock price for {company}!"}

    # System info
    if 'system info' in t or 'computer info' in t:
        import platform
        info = f"Running {platform.system()} {platform.release()}. Processor: {platform.processor()[:40]}."
        return info

    return None  # Not a system command, send to AI

@app.route('/')
def index():
    return open('static/SPIDY.html', encoding='utf-8').read()

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_msg = data.get('message', '')
        if not user_msg:
            return jsonify({'reply': 'I did not catch that!'})

        # Step 1: Try keyword-based system command first (fast)
        result = parse_command(user_msg)
        if result:
            if isinstance(result, dict):
                return jsonify({'reply': result['message'], 'action': result.get('action'), 'url': result.get('url'), 'status': 'ok'})
            return jsonify({'reply': result, 'status': 'ok'})

        # Step 2: HuggingFace intent detection (if loaded)
        intent_result = None
        if INTENT_AVAILABLE and intent_detector and intent_detector.loaded:
            intent_result = intent_detector.detect(user_msg)

            if intent_result:
                action = intent_result['action']
                confidence = intent_result['confidence']
                intent = intent_result['intent']

                # Route based on detected intent
                if action == 'open_app' and confidence > 0.5:
                    import re
                    app_name = re.sub(r'\b(open|launch|start|run|can you|please|for me)\b', '', user_msg.lower()).strip()
                    res = open_app(app_name)
                    return jsonify({'reply': res, 'status': 'ok', 'intent': intent, 'confidence': confidence})

                elif action == 'screenshot' and confidence > 0.5:
                    res = take_screenshot()
                    return jsonify({'reply': res, 'status': 'ok', 'intent': intent})

                elif action == 'weather' and confidence > 0.5:
                    import re
                    city = re.sub(r'\b(weather|temperature|what|is|the|in|at|for|tell|me|current|today|how|degrees)\b', '', user_msg.lower()).strip()
                    city = city or 'Chennai'
                    try:
                        r = requests.get(f'https://wttr.in/{city}?format=j1', timeout=5)
                        d = r.json()
                        curr = d['current_condition'][0]
                        return jsonify({'reply': f"Weather in {city}: {curr['temp_C']}°C, {curr['weatherDesc'][0]['value']}. Humidity: {curr['humidity']}%!", 'status': 'ok', 'intent': intent})
                    except:
                        return jsonify({'reply': f"Let me search weather for {city}!", 'action': 'open_url', 'url': f'https://www.google.com/search?q=weather+{city}', 'status': 'ok'})

                elif action == 'news' and confidence > 0.5:
                    return jsonify({'reply': "Opening latest news!", 'action': 'open_url', 'url': 'https://news.google.com/?hl=en-IN', 'status': 'ok', 'intent': intent})

                elif action == 'play_media' and confidence > 0.5:
                    import re
                    query = re.sub(r'\b(play|listen|watch|song|music|video|on|youtube|the)\b', '', user_msg.lower()).strip()
                    url = f'https://www.youtube.com/results?search_query={query.replace(" ", "+")}'
                    return jsonify({'reply': f"Playing {query} on YouTube!", 'action': 'open_url', 'url': url, 'status': 'ok', 'intent': intent})

                elif action == 'web_search' and confidence > 0.5:
                    import re
                    query = re.sub(r'\b(search|google|find|look up|can you|please|for me)\b', '', user_msg.lower()).strip()
                    url = f'https://www.google.com/search?q={query.replace(" ", "+")}'
                    return jsonify({'reply': f"Searching for: {query}", 'action': 'open_url', 'url': url, 'status': 'ok', 'intent': intent})

                elif action == 'datetime':
                    now = datetime.datetime.now()
                    return jsonify({'reply': f"It's {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')}.", 'status': 'ok', 'intent': intent})

                elif action == 'greet':
                    hour = datetime.datetime.now().hour
                    g = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
                    return jsonify({'reply': f"{g}! I'm S.P.I.D.Y, your friendly neighborhood AI! How can I help? 🕷️", 'status': 'ok', 'intent': intent})

        # Step 3: PyTorch Sentiment Analysis
        sentiment = 'NEUTRAL'
        tone_note = ''

        if SENTIMENT_AVAILABLE and pytorch_sentiment and pytorch_sentiment.loaded:
            # Use PyTorch model
            sent_result = pytorch_sentiment.analyze(user_msg)
            sentiment = sent_result['label']
            tone_note = f' ({sent_result["tone"]})' if sent_result['tone'] != 'normal' else ''
        elif sentiment_analyzer:
            # Fallback to pipeline
            try:
                s = sentiment_analyzer(user_msg[:512])[0]
                sentiment = s['label']
                if sentiment == 'NEGATIVE':
                    tone_note = ' (User seems stressed — be extra supportive)'
            except:
                pass

        # Step 4: Send to Groq AI
        response = client.chat.completions.create(
            model='llama-3.1-8b-instant',
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT + tone_note},
                {'role': 'user', 'content': user_msg}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        reply = response.choices[0].message.content.strip()
        intent_info = intent_result['intent'] if intent_result else 'ai_chat'
        return jsonify({'reply': reply, 'status': 'ok', 'sentiment': sentiment, 'intent': intent_info})

    except Exception as e:
        return jsonify({'reply': f'Spider-sense malfunction! {str(e)[:80]}'})

@app.route('/api/notes', methods=['GET'])
def get_notes():
    return jsonify(load_json(NOTES_FILE))

@app.route('/api/reminders', methods=['GET'])
def get_reminders():
    return jsonify([r for r in reminders if not r.get('fired')])

@app.route('/api/status')
def status():
    intent_status = 'not available'
    sentiment_status = 'not available'
    whisper_status_info = 'not available'
    if INTENT_AVAILABLE and intent_detector:
        intent_status = intent_detector.get_status()
    if SENTIMENT_AVAILABLE and pytorch_sentiment:
        sentiment_status = pytorch_sentiment.get_status()
    if WHISPER_AVAILABLE and whisper_asr:
        whisper_status_info = whisper_asr.get_status()
    return jsonify({
        'status': 'online',
        'version': '5.1',
        'ai': 'Groq-Llama + HuggingFace + PyTorch + Whisper ASR',
        'phase': '5 Complete',
        'intent_detector': intent_status,
        'sentiment_analyzer': sentiment_status,
        'whisper_asr': whisper_status_info,
        'torch_device': str(pytorch_sentiment.device) if SENTIMENT_AVAILABLE and pytorch_sentiment else 'N/A'
    })

@app.route('/api/sentiment', methods=['POST'])
def analyze_sentiment():
    try:
        data = request.get_json()
        text = data.get('text', '')
        if SENTIMENT_AVAILABLE and pytorch_sentiment and pytorch_sentiment.loaded:
            result = pytorch_sentiment.analyze(text)
            return jsonify(result)
        return jsonify({'label': 'UNKNOWN', 'error': 'PyTorch model loading...'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/sentiment/batch', methods=['POST'])
def batch_sentiment():
    try:
        data = request.get_json()
        texts = data.get('texts', [])
        if SENTIMENT_AVAILABLE and pytorch_sentiment and pytorch_sentiment.loaded:
            results = pytorch_sentiment.batch_analyze(texts)
            return jsonify({'results': results, 'count': len(results)})
        return jsonify({'error': 'Model loading...'})
    except Exception as e:
        return jsonify({'error': str(e)})

# ===== WHISPER ASR API =====
@app.route('/api/whisper/transcribe', methods=['POST'])
def whisper_transcribe():
    """
    Receive audio blob from browser → Whisper transcribe → return text.
    Browser records audio → sends to this endpoint → Python Whisper processes it.
    """
    try:
        if not WHISPER_AVAILABLE or not whisper_asr:
            return jsonify({'error': 'Whisper not available', 'text': ''})

        if not whisper_asr.loaded:
            return jsonify({'error': 'Whisper model loading...', 'text': '', 'status': 'loading'})

        # Get language preference
        language = request.form.get('language', 'auto')

        # Get audio file from browser
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file received', 'text': ''})

        audio_file = request.files['audio']
        audio_bytes = audio_file.read()

        # Transcribe using Whisper
        text, detected_lang = whisper_asr.transcribe_from_bytes(audio_bytes, language)

        if text:
            return jsonify({
                'text': text,
                'language': detected_lang,
                'status': 'ok',
                'model': whisper_asr.model_size
            })
        else:
            return jsonify({'error': detected_lang, 'text': ''})

    except Exception as e:
        return jsonify({'error': str(e), 'text': ''})

@app.route('/api/whisper/record', methods=['POST'])
def whisper_record():
    """
    Python records from laptop mic directly using Whisper.
    No browser mic needed!
    """
    try:
        if not WHISPER_AVAILABLE or not whisper_asr or not whisper_asr.loaded:
            return jsonify({'error': 'Whisper not ready', 'text': ''})

        data = request.get_json() or {}
        duration = data.get('duration', 5)
        language = data.get('language', 'en')

        # Record and transcribe
        text, lang = whisper_asr.record_audio(duration=duration, language=language)

        if text:
            return jsonify({'text': text, 'language': lang, 'status': 'ok'})
        else:
            return jsonify({'error': lang, 'text': ''})

    except Exception as e:
        return jsonify({'error': str(e), 'text': ''})

@app.route('/api/whisper/status', methods=['GET'])
def whisper_status():
    status_info = 'not available'
    if WHISPER_AVAILABLE and whisper_asr:
        status_info = whisper_asr.get_status()
    return jsonify({'whisper': status_info})

# ===== PHASE 5 — NEWS =====
@app.route('/api/news', methods=['GET'])
def get_news():
    try:
        category = request.args.get('category', 'technology')
        url = f'https://newsapi.org/v2/top-headlines?country=in&category={category}&pageSize=5&apiKey={os.getenv("NEWS_API_KEY", "")}'
        if not os.getenv('NEWS_API_KEY'):
            # Free fallback — RSS feed
            import xml.etree.ElementTree as ET
            feeds = {
                'technology': 'https://feeds.feedburner.com/TechCrunch',
                'general': 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms',
                'sports': 'https://www.espncricinfo.com/rss/content/story/feeds/0.xml',
            }
            feed_url = feeds.get(category, feeds['general'])
            r = requests.get(feed_url, timeout=5)
            root = ET.fromstring(r.content)
            items = root.findall('.//item')[:5]
            news = [{'title': i.find('title').text, 'description': i.find('description').text if i.find('description') is not None else ''} for i in items]
            return jsonify({'articles': news, 'source': 'RSS'})
        r = requests.get(url, timeout=5)
        data = r.json()
        return jsonify({'articles': data.get('articles', [])[:5], 'source': 'NewsAPI'})
    except Exception as e:
        return jsonify({'error': str(e), 'articles': []})

# ===== PHASE 5 — WEATHER API =====
@app.route('/api/weather', methods=['GET'])
def get_weather():
    try:
        city = request.args.get('city', 'Chennai')
        api_key = os.getenv('WEATHER_API_KEY', '')
        if not api_key:
            # Free fallback — wttr.in
            r = requests.get(f'https://wttr.in/{city}?format=j1', timeout=5)
            data = r.json()
            current = data['current_condition'][0]
            temp = current['temp_C']
            desc = current['weatherDesc'][0]['value']
            humidity = current['humidity']
            return jsonify({
                'city': city,
                'temp': temp,
                'description': desc,
                'humidity': humidity,
                'source': 'wttr.in'
            })
        r = requests.get(f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric', timeout=5)
        data = r.json()
        return jsonify({
            'city': city,
            'temp': data['main']['temp'],
            'description': data['weather'][0]['description'],
            'humidity': data['main']['humidity'],
            'source': 'OpenWeatherMap'
        })
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    print("S.P.I.D.Y Phase 5 - Web + AI Features Active!")
    print("Features: News, Weather, YouTube, HuggingFace Intent, Sentiment")
    app.run(debug=False, port=5000)