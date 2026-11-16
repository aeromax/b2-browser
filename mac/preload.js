const { contextBridge, ipcRenderer, webUtils } = require('electron');

// The page can't see a dropped file's path; Electron can. Only these two calls cross into the page.
contextBridge.exposeInMainWorld('native', {
  pathFor: file => webUtils.getPathForFile(file),
  choose: dir => ipcRenderer.invoke('choose', !!dir),
});
