const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const net = require('net');
const path = require('path');

// Finder-launched apps get a bare PATH; b2 and python3 usually live in Homebrew's.
const PATH = ['/opt/homebrew/bin', '/usr/local/bin', process.env.PATH].filter(Boolean).join(':');
const resource = f => app.isPackaged ? path.join(process.resourcesPath, f) : path.join(__dirname, '..', f);

let server, win;

const freePort = () => new Promise(res => {
  const s = net.createServer().listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => res(port)); });
});

async function waitFor(port) {
  for (let i = 0; i < 100; i++) {
    const ok = await new Promise(res => net.connect(port, '127.0.0.1').once('connect', function () { this.end(); res(true); }).once('error', () => res(false)));
    if (ok) return;
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error('The B2 Browser server did not start. Is python3 installed?');
}

async function start() {
  const port = await freePort();
  server = spawn('python3', [resource('app.py')], {
    env: { ...process.env, PATH, HOST: '127.0.0.1', PORT: String(port), CONFIG_DIR: path.join(app.getPath('userData'), 'config'),
           B2UI_TEMP_DIR: path.join(app.getPath('userData'), 'tmp') },
    stdio: 'inherit',
  });
  server.on('exit', code => { if (code) dialog.showErrorBox('B2 Browser', `The server stopped (exit ${code}). Is python3 installed?`); });
  await waitFor(port);
  win = new BrowserWindow({ width: 1180, height: 760, minWidth: 560, minHeight: 400, title: 'B2 Browser',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: false } });
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  win.loadURL(`http://127.0.0.1:${port}/`);
}

ipcMain.handle('choose', async (_e, dir) => {
  const r = await dialog.showOpenDialog(win, { properties: ['multiSelections', dir ? 'openDirectory' : 'openFile'] });
  return r.canceled ? [] : r.filePaths;
});

app.whenReady().then(() => start().catch(e => { dialog.showErrorBox('B2 Browser', String(e.message || e)); app.quit(); }));
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => server?.kill());  // jobs run in the server, so quitting stops them
