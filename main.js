const { app, BrowserWindow, shell, ipcMain } = require('electron');
const { execFile } = require('child_process');
const path = require('path');

const run = (c, a) => new Promise(resolve =>
  execFile(c, a, { windowsHide: true }, (e, o, s) => resolve({ e, o: o || '', s: s || '' })));
const R = (k, n, on, def, t) => ({ k, n, on, def, t: t || 'REG_DWORD' });
const HP = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c';
const BAL = '381b4222-f694-41f0-9685-ff5bb260df2e';
const IS_WIN = process.platform === 'win32';

// These options change only the current Windows user's settings.
const T = [
  { id: 'capture', name: 'Turn off background game recording',
    desc: 'Stops Windows from recording gameplay in the background, which may free CPU, GPU and disk resources.',
    regs: [
      R('HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR', 'AppCaptureEnabled', 0, 1),
      R('HKCU\\System\\GameConfigStore', 'GameDVR_Enabled', 0, 1)] },
  { id: 'mouse', name: 'Turn off mouse acceleration',
    desc: 'Makes pointer movement more consistent. You can turn it back on here.',
    note: 'Sign out and back in for this to take effect.',
    regs: [
      R('HKCU\\Control Panel\\Mouse', 'MouseSpeed', '0', '1', 'REG_SZ'),
      R('HKCU\\Control Panel\\Mouse', 'MouseThreshold1', '0', '6', 'REG_SZ'),
      R('HKCU\\Control Panel\\Mouse', 'MouseThreshold2', '0', '10', 'REG_SZ')] },
  { id: 'xbox', name: 'Stop the Xbox button opening Game Bar',
    desc: 'Prevents the controller’s Xbox button from opening Game Bar.',
    regs: [R('HKCU\\Software\\Microsoft\\GameBar', 'UseNexusForGameBarEnabled', 0, 1)] },
  { id: 'transparency', name: 'Turn off transparency effects',
    desc: 'Removes see-through window effects.',
    regs: [R('HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize', 'EnableTransparency', 0, 1)] },
  { id: 'power', name: 'Use the High performance power plan',
    desc: 'Uses more power and may make laptops run hotter. Off switches to Balanced.',
    note: 'If this fails, your PC may not offer this plan.', power: true }
];

async function getState(t) {
  if (t.power) {
    const r = await run('powercfg', ['/getactivescheme']);
    return r.o.toLowerCase().includes(HP);
  }
  for (const x of t.regs) {
    const r = await run('reg', ['query', x.k, '/v', x.n]);
    const m = r.o.match(/REG_\w+\s+(.+)/);
    let v;
    if (!m) v = String(x.def);
    else {
      v = m[1].trim();
      if (/REG_DWORD/.test(m[0])) v = String(parseInt(v, 16));
    }
    if (v !== String(x.on)) return false;
  }
  return true;
}

async function setState(t, on) {
  if (t.power) {
    const r = await run('powercfg', ['/setactive', on ? HP : BAL]);
    return r.e ? (r.s || r.e.message) : null;
  }
  for (const x of t.regs) {
    const r = await run('reg', ['add', x.k, '/v', x.n, '/t', x.t, '/d', String(on ? x.on : x.def), '/f']);
    if (r.e) return r.s || r.e.message;
  }
  return null;
}

ipcMain.handle('t:list', async () => {
  if (!IS_WIN) return [];
  return Promise.all(T.map(async t => ({
    id: t.id, name: t.name, desc: t.desc, note: t.note || '', on: await getState(t)
  })));
});
ipcMain.handle('t:set', async (_, id, on) => {
  const t = T.find(x => x.id === id);
  if (!t || !IS_WIN) return { ok: false, err: 'Not available on this PC.' };
  const err = await setState(t, !!on);
  return err ? { ok: false, err } : { ok: true };
});
ipcMain.handle('t:reset', async () => {
  if (IS_WIN) for (const t of T) await setState(t, false);
  return { ok: true };
});

// Free local AI via Ollama. No paid API key is used or stored.
const OLLAMA_URL = 'http://127.0.0.1:11434/api/chat';
const OLLAMA_MODEL = 'llama3.2:3b';
const SYS = 'You are the assistant inside Limit Tweaks, a Windows gaming performance app. Give clear, practical help with PC performance, Windows settings and in-game settings. Only suggest safe, reversible changes, explain how to undo them, and remind users to create a restore point before system changes. Do not recommend unverified third-party optimizers or risky registry edits. Keep answers concise.';

// Keep the existing renderer/preload interface compatible. Local Ollama needs no key.
ipcMain.handle('k:has', () => true);
ipcMain.handle('k:set', () => ({ ok: true }));
ipcMain.handle('c:send', async (_, msgs) => {
  try {
    const m = (Array.isArray(msgs) ? msgs : []).slice(-20).map(x => ({
      role: x.role === 'assistant' ? 'assistant' : 'user',
      content: String(x.content || '').slice(0, 4000)
    })).filter(x => x.content.trim());
    if (!m.length) return { err: 'Type a message first.' };

    let res;
    try {
      res = await fetch(OLLAMA_URL, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ model: OLLAMA_MODEL, stream: false, messages: [{ role: 'system', content: SYS }, ...m] }),
        signal: AbortSignal.timeout(120000)
      });
    } catch (e) {
      return { err: 'Cannot connect to Ollama. Install/open Ollama, then run `ollama run ' + OLLAMA_MODEL + '` in Command Prompt. Details: ' + e.message };
    }

    const raw = await res.text();
    let data;
    try { data = JSON.parse(raw); } catch { data = {}; }
    if (!res.ok) {
      const detail = data.error || ('HTTP ' + res.status);
      if (res.status === 404) return { err: 'The model may not be installed. Open Command Prompt and run: ollama run ' + OLLAMA_MODEL };
      return { err: 'Ollama error: ' + detail };
    }
    const answer = data && data.message && data.message.content;
    if (!answer) return { err: 'Ollama returned an empty response. Check that the model is installed and try again.' };
    return { text: answer };
  } catch (e) {
    return { err: 'AI chat failed: ' + (e && e.message ? e.message : String(e)) };
  }
});

function createWindow() {
  const win = new BrowserWindow({
    width: 1280, height: 820, minWidth: 900, minHeight: 600,
    backgroundColor: '#050914', title: 'Limit Tweaks', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false }
  });
  win.loadFile('index.html');
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());
