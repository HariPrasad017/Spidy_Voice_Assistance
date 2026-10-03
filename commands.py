"""
S.P.I.D.Y Deterministic Command Routing, Normalization, & Execution
"""

import os
import re
import json
import datetime
import subprocess
import platform
from config import (
    APPLICATION_WHITELIST,
    WEBSITE_MAP,
    NOTES_FILE,
    REMINDERS_FILE,
    logger
)

# ===== PERSISTENCE HELPERS =====
def load_json(file_path):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
    return []

def save_json(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")

# ===== VOICE COMMAND NORMALIZATION =====
def normalize_voice_text(text: str) -> str:
    """
    Cleans raw ASR output and resolves common voice misrecognitions.
    Example: 'open noted' -> 'open notepad'
    """
    if not text:
        return ""

    t = text.lower().strip()
    t = re.sub(r"[^\w\s\:\-\.\?']", ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()

    # Known ASR misrecognition mappings
    misrecognitions = [
        (r"\bwhat\s+s\b", "what's"),
        (r'\bopen (noted|not bad|not that|note pad|notes pad)\b', 'open notepad'),
        (r'\bopen (calc|calculate|calculates)\b', 'open calculator'),
        (r'\bopen (visual studio code|vs code)\b', 'open vscode'),
        (r'\b(screen shot|capture screen|take screen shot|take a screen shot)\b', 'take a screenshot'),
        (r'\b(raise volume|sound up|turn up volume|turn volume up|increase sound|volume up|make it louder)\b', 'increase volume'),
        (r'\b(lower volume|sound down|turn down volume|turn volume down|decrease sound|volume down|make it quieter)\b', 'decrease volume'),
        (r'\b(mute sound|mute audio|silence volume|silence audio|turn off sound)\b', 'mute volume'),
        (r'\b(unmute sound|unmute audio|restore sound|restore audio|turn on sound)\b', 'unmute volume'),
        (r'\b(shut down pc|turn off computer|turn off pc)\b', 'shutdown'),
        (r'\bl\s+o\s+q\b', 'loq'),
        (r'\bl\s*\.\s*o\s*\.\s*q\b', 'loq'),
        (r'\blenova\b', 'lenovo'),
    ]

    for pattern, replacement in misrecognitions:
        t = re.sub(pattern, replacement, t)

    return t

# ===== APPLICATION LAUNCHING SAFETY =====
def resolve_app_key(target: str):
    """
    Safely matches input against verified application whitelist aliases.
    Strictly rejects shell operators, path traversal, flags, or arbitrary arguments.
    """
    if not target:
        return None

    target = target.lower().strip()

    # Reject any shell metacharacters, pipes, redirects, or flag arguments
    if re.search(r'[;&|`$><\/\\\-]', target):
        return None

    # Exact key or display name match
    for key, data in APPLICATION_WHITELIST.items():
        if target == key or target == data['display_name'].lower():
            return key
        for alias in data['aliases']:
            if target == alias:
                return key

    # Clean multi-word matching with optional 'app' or 'application' suffix
    for key, data in APPLICATION_WHITELIST.items():
        for alias in data['aliases']:
            pattern = r'^(the\s+)?' + re.escape(alias) + r'(\s+app|\s+application)?$'
            if re.match(pattern, target):
                return key

    return None

def open_app(app_name: str) -> str:
    """
    Safely opens an application from the verified whitelist without shell injection.
    """
    app_key = resolve_app_key(app_name)
    if not app_key:
        logger.warning(f"Rejected unwhitelisted application request: '{app_name}'")
        return f"For security reasons, I can only launch verified applications (Notepad, Calculator, Chrome, VS Code, Explorer, Terminal, etc.). '{app_name}' is not in the allowed list."

    app_info = APPLICATION_WHITELIST[app_key]
    display_name = app_info['display_name']

    if platform.system() != "Windows":
        return f"Application launching is only supported on local Windows desktop. Simulated launch of {display_name}."

    try:
        cmd = app_info['windows_cmd']
        proc = subprocess.Popen(cmd, shell=False)
        # Check that process started or didn't immediately error out
        if proc.poll() is None or proc.returncode == 0:
            return f"Opening {display_name}!"
        else:
            return f"Failed to open {display_name}: process exited with code {proc.returncode}."
    except Exception as e:
        logger.error(f"Failed to open {display_name}: {e}")
        return f"Failed to open {display_name}: {str(e)[:60]}"

def close_app(app_name: str) -> str:
    """
    Safely terminates an application from the verified whitelist.
    """
    app_key = resolve_app_key(app_name)
    if not app_key:
        return f"Cannot close unrecognized application: '{app_name}'."

    display_name = APPLICATION_WHITELIST[app_key]['display_name']

    proc_map = {
        'chrome': 'chrome.exe',
        'notepad': 'notepad.exe',
        'calculator': 'CalculatorApp.exe',
        'vscode': 'Code.exe',
        'edge': 'msedge.exe',
        'paint': 'mspaint.exe',
        'terminal': 'cmd.exe',
        'taskmgr': 'Taskmgr.exe'
    }

    proc = proc_map.get(app_key)
    if not proc or platform.system() != "Windows":
        return f"Closing {display_name} is not supported on this platform."

    try:
        subprocess.Popen(['taskkill', '/F', '/IM', proc], shell=False)
        return f"Closed {display_name}!"
    except Exception as e:
        return f"Failed to close {display_name}: {str(e)[:60]}"

# ===== SYSTEM HARDWARE & UTILITIES =====
def get_desktop_path() -> str:
    """Accurately locates the user's active Windows Desktop, including OneDrive redirection."""
    user_home = os.path.expanduser('~')
    candidates = [
        os.path.join(user_home, 'OneDrive', 'Desktop'),
        os.path.join(user_home, 'Desktop'),
    ]
    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            # CSIDL_DESKTOPDIRECTORY = 0x0010
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:
                if buf.value and os.path.exists(buf.value):
                    candidates.insert(0, buf.value)
        except Exception as e:
            logger.debug(f"SHGetFolderPath note: {e}")

    for p in candidates:
        if os.path.exists(p):
            return p

    fallback = os.path.join(user_home, 'Desktop')
    try:
        os.makedirs(fallback, exist_ok=True)
        return fallback
    except Exception:
        return os.path.dirname(os.path.abspath(__file__))

def take_screenshot() -> str:
    try:
        desktop = get_desktop_path()
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'SPIDY_screenshot_{timestamp}.png'
        path = os.path.join(desktop, filename)

        # Attach calling thread to active input desktop if on Windows
        if platform.system() == "Windows":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
                if hdesk:
                    user32.SetThreadDesktop(hdesk)
            except Exception as win_e:
                logger.debug(f"Input desktop attach note: {win_e}")

        screenshot = None

        # Method 1: PIL ImageGrab
        try:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab()
        except Exception as ig_err:
            logger.warning(f"PIL ImageGrab note: {ig_err}")

        # Method 2: Win32 GDI BitBlt fallback
        if screenshot is None and platform.system() == "Windows":
            try:
                import ctypes
                from ctypes import wintypes
                from PIL import Image
                u32 = ctypes.windll.user32
                gdi = ctypes.windll.gdi32
                hwnd = u32.GetDesktopWindow()
                hdc = u32.GetDC(hwnd)
                if hdc:
                    w = u32.GetSystemMetrics(0)
                    h = u32.GetSystemMetrics(1)
                    memdc = gdi.CreateCompatibleDC(hdc)
                    hbmp = gdi.CreateCompatibleBitmap(hdc, w, h)
                    old_bmp = gdi.SelectObject(memdc, hbmp)
                    if gdi.BitBlt(memdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020):
                        class BITMAPINFOHEADER(ctypes.Structure):
                            _fields_ = [
                                ('biSize', wintypes.DWORD),
                                ('biWidth', wintypes.LONG),
                                ('biHeight', wintypes.LONG),
                                ('biPlanes', wintypes.WORD),
                                ('biBitCount', wintypes.WORD),
                                ('biCompression', wintypes.DWORD),
                                ('biSizeImage', wintypes.DWORD),
                                ('biXPelsPerMeter', wintypes.LONG),
                                ('biYPelsPerMeter', wintypes.LONG),
                                ('biClrUsed', wintypes.DWORD),
                                ('biClrImportant', wintypes.DWORD)
                            ]
                        bmi = BITMAPINFOHEADER()
                        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                        bmi.biWidth = w
                        bmi.biHeight = -h
                        bmi.biPlanes = 1
                        bmi.biBitCount = 32
                        bmi.biCompression = 0
                        buf = ctypes.create_string_buffer(w * h * 4)
                        gdi.GetDIBits(memdc, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
                        img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
                        screenshot = img.convert('RGB')
                    gdi.SelectObject(memdc, old_bmp)
                    gdi.DeleteDC(memdc)
                    gdi.DeleteObject(hbmp)
                    u32.ReleaseDC(hwnd, hdc)
            except Exception as gdi_err:
                logger.warning(f"GDI screenshot fallback note: {gdi_err}")

        # Method 3: PowerShell .NET screen capture fallback
        if screenshot is None and platform.system() == "Windows":
            try:
                # Escape backslashes for PowerShell single quotes
                safe_path = path.replace("'", "''")
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "Add-Type -AssemblyName System.Drawing; "
                    "$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                    "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; "
                    "$g = [System.Drawing.Graphics]::FromImage($bmp); "
                    "$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); "
                    f"$bmp.Save('{safe_path}'); "
                    "$g.Dispose(); $bmp.Dispose()"
                )
                subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_script], capture_output=True, text=True, check=False)
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    return f"Screenshot captured and saved to Desktop as {filename} (full path: {path})!"
            except Exception as ps_err:
                logger.warning(f"PowerShell screenshot fallback note: {ps_err}")

        if screenshot is None:
            return "Screenshot failed: could not capture display (no interactive display device available)."

        screenshot.save(path)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return f"Screenshot captured and saved to Desktop as {filename} (full path: {path})!"
        else:
            return "Screenshot failed: file could not be created or is empty."
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        return f"Screenshot failed: {str(e)[:60]}"

def control_volume(action: str, level=None) -> str:
    if platform.system() != "Windows":
        return f"Volume control ({action}) simulated on non-Windows environment."

    try:
        import pythoncom
        pythoncom.CoInitialize()
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        device = AudioUtilities.GetSpeakers()
        if hasattr(device, 'EndpointVolume'):
            volume = device.EndpointVolume
        else:
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
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
            return f"Volume increased to {int(new * 100)}%!"
        elif action == 'down':
            cur = volume.GetMasterVolumeLevelScalar()
            new = max(0.0, cur - 0.1)
            volume.SetMasterVolumeLevelScalar(new, None)
            return f"Volume decreased to {int(new * 100)}%!"
    except Exception as e:
        logger.warning(f"pycaw volume control fallback: {e}")
        # Safe PowerShell key simulation fallback
        try:
            if action == 'up':
                subprocess.run(['powershell', '-c', '$wsh = New-Object -ComObject WScript.Shell; for($i=0;$i -lt 5;$i++){$wsh.SendKeys([char]175)}'], check=False)
                return "Volume increased!"
            elif action == 'down':
                subprocess.run(['powershell', '-c', '$wsh = New-Object -ComObject WScript.Shell; for($i=0;$i -lt 5;$i++){$wsh.SendKeys([char]174)}'], check=False)
                return "Volume decreased!"
            elif action == 'mute':
                subprocess.run(['powershell', '-c', '$wsh = New-Object -ComObject WScript.Shell; $wsh.SendKeys([char]173)'], check=False)
                return "Volume muted!"
            elif action == 'unmute':
                subprocess.run(['powershell', '-c', '$wsh = New-Object -ComObject WScript.Shell; $wsh.SendKeys([char]173)'], check=False)
                return "Volume unmuted!"
        except Exception as ps_e:
            return f"Volume control unavailable: {str(ps_e)[:50]}"

    return "Volume command processed."

def control_brightness(action: str, level=None) -> str:
    if platform.system() != "Windows":
        return f"Brightness control ({action}) simulated on non-Windows environment."

    try:
        if action == 'set' and level is not None:
            val = max(0, min(100, int(float(level))))
            ps = f'(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{val})'
            subprocess.run(['powershell', '-c', ps], check=False)
            return f"Brightness set to {val}%!"
        elif action == 'up':
            ps = '$b=(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness; $n=[math]::Min(100,$b+10); (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,$n); Write-Output $n'
            res = subprocess.run(['powershell', '-c', ps], capture_output=True, text=True, check=False)
            val = res.stdout.strip()
            return f"Brightness increased to {val}%!" if val else "Brightness increased!"
        elif action == 'down':
            ps = '$b=(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness; $n=[math]::Max(0,$b-10); (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,$n); Write-Output $n'
            res = subprocess.run(['powershell', '-c', ps], capture_output=True, text=True, check=False)
            val = res.stdout.strip()
            return f"Brightness decreased to {val}%!" if val else "Brightness decreased!"
    except Exception as e:
        return f"Brightness control failed: {str(e)[:60]}"

    return "Brightness updated."

def shutdown_system(action: str) -> str:
    if platform.system() != "Windows":
        return f"System power action '{action}' is not permitted on this server."

    if action == 'shutdown':
        subprocess.Popen(['shutdown', '/s', '/t', '30'], shell=False)
        return "System will shut down in 30 seconds! Say 'cancel shutdown' to stop."
    elif action == 'restart':
        subprocess.Popen(['shutdown', '/r', '/t', '30'], shell=False)
        return "System will restart in 30 seconds! Say 'cancel restart' to stop."
    elif action == 'cancel':
        subprocess.Popen(['shutdown', '/a'], shell=False)
        return "Shutdown/restart cancelled!"
    elif action == 'sleep':
        subprocess.Popen(['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'], shell=False)
        return "Entering sleep mode!"
    elif action == 'lock':
        subprocess.Popen(['rundll32.exe', 'user32.dll,LockWorkStation'], shell=False)
        return "Workstation locked!"
    return "Unknown power command."

# ===== NOTES & REMINDERS LOGIC =====
def handle_notes_command(text: str):
    t = text.lower().strip()
    # If the user is referencing prior text (e.g. "save that to my notes"), pass through to context resolution
    if any(p in t for p in ['save that', 'save this', 'add that', 'add this']) and ('note' in t or 'notes' in t):
        return None

    if 'show notes' in t or 'my notes' in t or 'read notes' in t or 'show my notes' in t:
        notes = load_json(NOTES_FILE)
        if not notes:
            return "No notes saved yet! Say 'note [your text]' to create one."
        recent = notes[-3:]
        texts = [f"{i+1}. {n['text']}" for i, n in enumerate(recent)]
        return "Your recent notes: " + " | ".join(texts)

    if 'clear notes' in t or 'delete notes' in t:
        save_json(NOTES_FILE, [])
        return "All notes have been cleared!"

    if t.startswith('note ') or t.startswith('save note') or t.startswith('add note'):
        note_text = re.sub(r'^(note|save note|add note)\s+', '', t).strip()
        if note_text:
            notes = load_json(NOTES_FILE)
            notes.append({'text': note_text, 'time': datetime.datetime.now().isoformat()})
            save_json(NOTES_FILE, notes)
            return f"Note saved: '{note_text}'"

    return None

def handle_reminders_command(text: str):
    t = text.lower().strip()
    if 'show reminders' in t or 'my reminders' in t:
        reminders = load_json(REMINDERS_FILE)
        active = [r for r in reminders if not r.get('fired')]
        if not active:
            return "No active reminders!"
        texts = [f"{r['text']} at {r['time']}" for r in active[:3]]
        return "Active reminders: " + " | ".join(texts)

    if 'remind' in t or 'reminder' in t or 'set alarm' in t or 'set reminder' in t:
        now = datetime.datetime.now()
        reminder_time = None

        # Pattern: "in X minutes/hours"
        m = re.search(r'in\s+(\d+)\s+(minute|minutes|hour|hours)', t)
        if m:
            amount = int(m.group(1))
            unit = m.group(2)
            if 'hour' in unit:
                reminder_time = now + datetime.timedelta(hours=amount)
            else:
                reminder_time = now + datetime.timedelta(minutes=amount)

        # Pattern: "at HH:MM am/pm"
        if not reminder_time:
            m = re.search(r'at\s+(\d{1,2}):?(\d{2})?\s*(am|pm)?', t)
            if m:
                h = int(m.group(1))
                mn = int(m.group(2)) if m.group(2) else 0
                ampm = m.group(3)
                if ampm == 'pm' and h != 12:
                    h += 12
                elif ampm == 'am' and h == 12:
                    h = 0
                reminder_time = now.replace(hour=h, minute=mn, second=0)
                if reminder_time < now:
                    reminder_time += datetime.timedelta(days=1)

        clean_text = re.sub(r'\b(remind me|set reminder|set alarm|to|at|in|for)\b.*', '', t).strip()
        reminder_desc = clean_text or "General Reminder"

        if reminder_time:
            reminders = load_json(REMINDERS_FILE)
            reminders.append({
                'text': reminder_desc,
                'time': reminder_time.strftime('%Y-%m-%d %H:%M'),
                'fired': False
            })
            save_json(REMINDERS_FILE, reminders)
            return f"Reminder set for {reminder_time.strftime('%I:%M %p')}! I'll alert you then."
        else:
            return "When should I remind you? Say like 'remind me in 30 minutes' or 'remind me at 5 pm'."

    return None

# ===== PRIMARY DETERMINISTIC COMMAND PARSER =====
def parse_command(msg: str):
    """
    Inspects input text for deterministic system commands.
    Returns:
      - string response (for direct reply)
      - dict (for UI actions like URL open)
      - None (if it should fall through to intent detection / Groq)
    """
    if not msg:
        return None

    # Step 0: Voice normalization
    t = normalize_voice_text(msg)

    # Guard: Multi-step requests must not be intercepted as single deterministic commands
    try:
        from agent.task_engine import is_multi_step_request
        if is_multi_step_request(t):
            return None
    except Exception:
        pass

    # 1. Greetings
    hour = datetime.datetime.now().hour
    greeting_triggers = {
        'hello', 'hi', 'hey',
        'hello spidey', 'hi spidey', 'hey spidey', 'spidey',
        'hello spidy', 'hi spidy', 'hey spidy', 'spidy',
        'good morning', 'good afternoon', 'good evening', 'good night',
        'greetings', 'howdy', "what's up", 'sup'
    }
    t_clean = t.strip()
    is_greeting = (
        t_clean in greeting_triggers or
        bool(re.match(r'^(?:hello|hi|hey|greetings)\s+(?:spidey|spidy)[!.]*$', t_clean)) or
        bool(re.match(r'^(?:hello|hi|hey)[!.]*$', t_clean)) or
        any(t_clean == g or t_clean.startswith(g + " ") for g in ['good morning', 'good afternoon', 'good evening', 'good night'])
    )

    if is_greeting:
        if hour < 12:
            greeting = "Good morning"
            energy = "How may I assist you today?"
        elif hour < 17:
            greeting = "Good afternoon"
            energy = "Hope your day is going well."
        elif hour < 21:
            greeting = "Good evening"
            energy = "How can I help you this evening?"
        else:
            greeting = "Good night"
            energy = "Have a restful night."
        return f"{greeting}! I'm Spidey, your personal assistant. {energy} The time is {datetime.datetime.now().strftime('%I:%M %p')}."

    # 2. Time & Date
    if ('time' in t and any(x in t for x in ['what', 'tell', 'current', 'is it'])) or t == 'what time is it':
        return f"It's {datetime.datetime.now().strftime('%I:%M %p')}."
    if any(x in t for x in ['what date', 'today date', "what's today", 'what day', "what is today's date"]):
        return f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}."

    # 3. Brightness control
    if 'brightness' in t:
        nums = re.findall(r'\d+', t)
        if nums:
            return control_brightness('set', nums[0])
        if any(x in t for x in ['increase', 'up', 'raise', 'higher', 'more']):
            return control_brightness('up')
        if any(x in t for x in ['decrease', 'down', 'lower', 'reduce', 'less', 'dim']):
            return control_brightness('down')
        return control_brightness('up')

    # 4. Screenshots
    if any(x in t for x in ['screenshot', 'take a screenshot', 'capture screen', 'screen shot']):
        return take_screenshot()

    # 5. Volume control
    if 'volume' in t or 'mute' in t or 'unmute' in t:
        if 'unmute' in t:
            return control_volume('unmute')
        if 'mute' in t and 'un' not in t:
            return control_volume('mute')

        nums = re.findall(r'\d+', t)
        if nums:
            return control_volume('set', nums[0])
        if any(x in t for x in ['increase', 'up', 'louder', 'raise', 'higher']):
            return control_volume('up')
        if any(x in t for x in ['decrease', 'down', 'lower', 'quieter', 'reduce', 'less']):
            return control_volume('down')
        return control_volume('up')

    # 6. System Power
    if 'shut down' in t or 'shutdown' in t:
        return shutdown_system('shutdown')
    if 'restart' in t or 'reboot' in t:
        return shutdown_system('restart')
    if 'cancel shutdown' in t or 'cancel restart' in t:
        return shutdown_system('cancel')
    if 'sleep' in t and any(x in t for x in ['computer', 'laptop', 'system', 'pc']):
        return shutdown_system('sleep')
    # Workstation Lock Safety Check
    # Never trigger lock on product/brand names, models, or ambiguous utterances
    is_product_query = any(b in t for b in ['lenovo', 'loq', 'asus', 'dell', 'hp', 'acer', 'macbook', 'legion', 'laptop model', 'specs', 'price'])
    if ('lenovo' in t or 'lenova' in t) and 'lock' in t:
        # Ambiguous speech recognition — clarify rather than locking the machine
        return "Did you mean the Lenovo LOQ laptop? I can search for details or specifications if you like."

    if not is_product_query:
        # Require explicit lock intent
        lock_patterns = [
            r'^(?:please\s+)?lock\s+(?:the\s+|my\s+|this\s+)?(?:computer|workstation|pc|screen)[.?!]*$',
            r'^lock\s+down\s+(?:the\s+|my\s+)?(?:computer|pc|workstation)[.?!]*$',
            r'^lock\s+(?:workstation|pc|screen|computer)[.?!]*$'
        ]
        if any(re.search(p, t) for p in lock_patterns):
            return shutdown_system('lock')

    # 7. Notes
    note_resp = handle_notes_command(t)
    if note_resp:
        return note_resp

    # 8. Reminders
    rem_resp = handle_reminders_command(t)
    if rem_resp:
        return rem_resp

    # 9. Open Websites & Apps
    if t.startswith('open ') or t.startswith('launch '):
        target = re.sub(r'^(open|launch)\s+', '', t).strip()

        # Check websites
        for site, url in WEBSITE_MAP.items():
            if site in target:
                return {
                    'action': 'open_url',
                    'url': url,
                    'message': f"Opening {site.title()}!"
                }

        # Check applications
        return open_app(target)

    # 10. Close Apps
    if t.startswith('close ') or t.startswith('kill ') or t.startswith('quit '):
        target = re.sub(r'^(close|kill|quit)\s+', '', t).strip()
        return close_app(target)

    # 11. Search
    if t.startswith('search ') or t.startswith('google '):
        query = re.sub(r'^(search|google)\s+', '', t).strip()
        return {
            'action': 'open_url',
            'url': f'https://www.google.com/search?q={query.replace(" ", "+")}',
            'message': f"Searching for: {query}"
        }

    # 12. Play / YouTube
    if t.startswith('play ') or t.startswith('youtube '):
        query = re.sub(r'^(play|youtube)\s+', '', t).strip()
        return {
            'action': 'open_url',
            'url': f'https://www.youtube.com/results?search_query={query.replace(" ", "+")}',
            'message': f"Playing {query} on YouTube!"
        }

    # 13. Weather (deterministic parsing)
    # Strip trailing '?' for matching (kept in normalized text for other purposes)
    t_no_q = t.rstrip('?').strip()
    weather_phrases = {
        "what's the weather", "whats the weather",
        "what is the weather", "weather today",
        "what's the weather today", "what is the weather today",
        "what's the weather like", "what is the weather like",
    }
    if t_no_q in weather_phrases or t_no_q.startswith('weather in ') or t_no_q.startswith('temperature in '):
        if t_no_q in weather_phrases:
            city = 'Chennai'
        elif t_no_q.startswith('weather in '):
            city = t_no_q[11:].strip() or 'Chennai'
        elif t_no_q.startswith('temperature in '):
            city = t_no_q[15:].strip() or 'Chennai'
        else:
            city = re.sub(r'^(weather in|temperature in|weather)\s*', '', t_no_q).strip() or 'Chennai'
        try:
            import requests
            r = requests.get(f'https://wttr.in/{city}?format=j1', timeout=5)
            data = r.json()
            curr = data['current_condition'][0]
            temp = curr['temp_C']
            desc = curr['weatherDesc'][0]['value']
            humidity = curr['humidity']
            return f"Weather in {city.title()}: {temp}°C, {desc}. Humidity: {humidity}%. Stay safe out there!"
        except Exception:
            return {
                'action': 'open_url',
                'url': f'https://www.google.com/search?q=weather+{city}',
                'message': f"Opening weather forecast for {city}!"
            }

    # 14. Battery
    if 'battery' in t:
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery:
                status_str = "charging" if battery.power_plugged else "not charging"
                return f"Battery is at {int(battery.percent)}% and {status_str}."
        except Exception:
            pass
        return "Battery info unavailable on this system."

    # 15. System Info
    if 'system info' in t or 'computer info' in t:
        return f"Running {platform.system()} {platform.release()}. Processor: {platform.processor()[:40]}."

    return None
