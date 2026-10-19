const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lt', {
  list: () => ipcRenderer.invoke('t:list'),
  set: (id, on) => ipcRenderer.invoke('t:set', id, on),
  reset: () => ipcRenderer.invoke('t:reset'),
  hasKey: () => ipcRenderer.invoke('k:has'),
  setKey: (k) => ipcRenderer.invoke('k:set', k),
  chat: (msgs) => ipcRenderer.invoke('c:send', msgs)
});
