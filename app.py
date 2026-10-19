import os, sys, json, secrets, shutil, subprocess, threading, webbrowser
import ctypes, urllib.request, urllib.error
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

IS_WIN = sys.platform == 'win32'
if IS_WIN:
    import winreg

BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'LimitTweaks')
KEYFILE = os.path.join(DATA, 'key.dat')
TOKEN = secrets.token_hex(16)
NOWIN = 0x08000000 if IS_WIN else 0
HP = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'
BAL = '381b4222-f694-41f0-9685-ff5bb260df2e'

# Every tweak only changes your own user settings (no admin needed).
# "Off" always puts back the Windows default value.
D, S = 'dword', 'sz'
def R(path, name, on, default, kind=D):
    return (path, name, on, default, kind)

GDVR = r'Software\Microsoft\Windows\CurrentVersion\GameDVR'
MOUSE = r'Control Panel\Mouse'
TWEAKS = [
    dict(id='capture', name='Turn off background game recording',
         desc='Stops Windows from recording gameplay in the background, which frees up CPU, GPU and disk.',
         regs=[R(GDVR, 'AppCaptureEnabled', 0, 1),
               R(r'System\GameConfigStore', 'GameDVR_Enabled', 0, 1)]),
    dict(id='mouse', name='Turn off mouse acceleration',
         desc='Makes the pointer move exactly as far as your hand does, which helps aim in shooters.',
         note='Sign out and back in for this to take effect.',
         regs=[R(MOUSE, 'MouseSpeed', '0', '1', S),
               R(MOUSE, 'MouseThreshold1', '0', '6', S),
               R(MOUSE, 'MouseThreshold2', '0', '10', S)]),
    dict(id='xbox', name='Stop the Xbox button opening Game Bar',
         desc='Prevents the controller’s Xbox button from opening Game Bar in the middle of a game.',
         regs=[R(r'Software\Microsoft\GameBar', 'UseNexusForGameBarEnabled', 0, 1)]),
    dict(id='transparency', name='Turn off transparency effects',
         desc='Removes see-through window effects, which uses a little less GPU.',
         regs=[R(r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize', 'EnableTransparency', 0, 1)]),
    dict(id='power', name='Use the High performance power plan',
         desc='Keeps your CPU ready for games instead of saving power. Uses more power and runs laptops hotter. Off switches to Balanced.',
         note='If this fails, your PC may not offer this plan.', power=True),
]

def run(*a):
    r = subprocess.run(a, capture_output=True, text=True, creationflags=NOWIN)
    return r.returncode, (r.stdout or '') + (r.stderr or '')

def get_state(t):
    if t.get('power'):
        return HP in run('powercfg', '/getactivescheme')[1].lower()
    for path, name, on, default, kind in t['regs']:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
                v = winreg.QueryValueEx(k, name)[0]
        except OSError:
            v = default
        if str(v) != str(on):
            return False
    return True

def set_state(t, on):
    try:
        if t.get('power'):
            code, out = run('powercfg', '/setactive', HP if on else BAL)
            return None if code == 0 else (out.strip() or 'powercfg failed')
        for path, name, onv, default, kind in t['regs']:
            val = onv if on else default
            if kind == D:
                val = int(val)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as k:
                winreg.SetValueEx(k, name, 0, winreg.REG_DWORD if kind == D else winreg.REG_SZ, val)
    except Exception as e:
        return str(e)
    return None

# Your API key is stored encrypted with Windows (only your Windows account can read it).
class BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

def crypt(data, fn):
    buf = ctypes.create_string_buffer(data, len(data))
    bi = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    bo = BLOB()
    if not fn(ctypes.byref(bi), None, None, None, None, 0, ctypes.byref(bo)):
        raise OSError('Windows could not encrypt or decrypt the key.')
    out = ctypes.string_at(bo.pbData, bo.cbData)
    ctypes.windll.kernel32.LocalFree(bo.pbData)
    return out

def set_key(k):
    k = str(k).strip()
    if not k:
        return {'err': 'Enter a key first.'}
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(KEYFILE, 'wb') as f:
            f.write(crypt(k.encode(), ctypes.windll.crypt32.CryptProtectData))
        return {'ok': True}
    except Exception as e:
        return {'err': str(e)}

SYS = ('You are the assistant inside Limit Tweaks, a Windows gaming performance app. '
       'Give clear, practical help with PC performance, Windows settings and in-game settings. '
       'Only suggest safe, reversible changes, say how to undo them, and remind people to create a restore point '
       'before system changes. Do not recommend unverified third-party optimizers or risky registry edits. '
       'Keep answers short.')

def chat(msgs):
    if not os.path.exists(KEYFILE):
        return {'err': 'Add your API key first.'}
    try:
        with open(KEYFILE, 'rb') as f:
            key = crypt(f.read(), ctypes.windll.crypt32.CryptUnprotectData).decode()
        msgs = msgs if isinstance(msgs, list) else []
        m = [{'role': 'assistant' if x.get('role') == 'assistant' else 'user',
              'content': str(x.get('content', ''))[:4000]} for x in msgs[-20:]]
        body = json.dumps({'model': 'claude-sonnet-5-5', 'max_tokens': 1000, 'system': SYS, 'messages': m}).encode()
        req = urllib.request.Request('https://api.anthropic.com/v1/messages', body, {
            'content-type': 'application/json', 'x-api-key': key, 'anthropic-version': '2023-06-01'})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        return {'text': '\n'.join(b['text'] for b in d['content'] if b.get('type') == 'text')}
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e)['error']['message']
        except Exception:
            msg = 'Request failed (%s)' % e.code
        return {'err': msg}
    except Exception as e:
        return {'err': str(e)}

def api(path, b):
    if path == '/api/list':
        if not IS_WIN:
            return []
        return [dict(id=t['id'], name=t['name'], desc=t['desc'], note=t.get('note', ''), on=get_state(t))
                for t in TWEAKS]
    if path == '/api/set':
        t = next((x for x in TWEAKS if x['id'] == b.get('id')), None)
        if not t or not IS_WIN:
            return {'ok': False, 'err': 'Not available on this PC.'}
        err = set_state(t, bool(b.get('on')))
        return {'ok': False, 'err': err} if err else {'ok': True}
    if path == '/api/reset':
        if IS_WIN:
            for t in TWEAKS:
                set_state(t, False)
        return {'ok': True}
    if path == '/api/haskey':
        return os.path.exists(KEYFILE)
    if path == '/api/setkey':
        return set_key(b.get('key', ''))
    if path == '/api/chat':
        return chat(b.get('messages'))
    return None

# This small script is added to the page so the buttons can talk to this program.
SHIM = ("<script>var T=%s;function P(u,b){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json','X-Token':T},"
        "body:JSON.stringify(b||{})}).then(function(r){return r.json()})}"
        "window.lt={list:function(){return P('/api/list')},set:function(i,o){return P('/api/set',{id:i,on:o})},"
        "reset:function(){return P('/api/reset')},hasKey:function(){return P('/api/haskey')},"
        "setKey:function(k){return P('/api/setkey',{key:k})},chat:function(m){return P('/api/chat',{messages:m})}};"
        "addEventListener('pagehide',function(){navigator.sendBeacon('/api/bye?t='+T)});</script>")

bye = [None]
def cancel_bye():
    if bye[0]:
        bye[0].cancel()
        bye[0] = None

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body, ctype='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        return self.headers.get('Host', '').split(':')[0] in ('127.0.0.1', 'localhost')

    def do_GET(self):
        cancel_bye()
        if not self.host_ok():
            return self.reply(403, b'Forbidden', 'text/plain')
        if urlparse(self.path).path not in ('/', '/index.html'):
            return self.reply(404, b'Not found', 'text/plain')
        with open(os.path.join(BASE, 'index.html'), encoding='utf-8') as f:
            html = f.read()
        html = html.replace('<body>', '<body>' + SHIM % json.dumps(TOKEN), 1)
        self.reply(200, html.encode('utf-8'), 'text/html; charset=utf-8')

    def do_POST(self):
        u = urlparse(self.path)
        if not self.host_ok():
            return self.reply(403, b'{"err":"Forbidden"}')
        if u.path == '/api/bye':
            if parse_qs(u.query).get('t') == [TOKEN]:
                cancel_bye()
                bye[0] = threading.Timer(4, lambda: os._exit(0))
                bye[0].start()
            return self.reply(204, b'')
        cancel_bye()
        if self.headers.get('X-Token') != TOKEN:
            return self.reply(403, b'{"err":"Forbidden"}')
        try:
            n = int(self.headers.get('Content-Length') or 0)
            res = api(u.path, json.loads(self.rfile.read(n) or b'{}'))
        except Exception as e:
            res = {'err': str(e)}
        if res is None:
            return self.reply(404, b'{"err":"Unknown"}')
        self.reply(200, json.dumps(res).encode())

def open_window(url):
    for p in (os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
              os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),
              shutil.which('msedge')):
        if p and os.path.exists(p):
            subprocess.Popen([p, '--app=' + url, '--window-size=1280,820'])
            return
    webbrowser.open(url)

if __name__ == '__main__':
    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    url = 'http://127.0.0.1:%d/' % srv.server_address[1]
    if os.environ.get('LT_NO_WINDOW'):
        print(url, flush=True)
    else:
        open_window(url)
    srv.serve_forever()
