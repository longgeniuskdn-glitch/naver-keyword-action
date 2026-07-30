'use strict';
const { app, BrowserWindow, Menu, Tray, nativeImage, shell, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { CodexClient } = require('./codexClient');
const { normalizeUsage } = require('./usage');

const OFFICIAL_USAGE_URL = 'https://chatgpt.com/codex/cloud/settings/analytics';
const TRAY_ICON_DATA = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAAAS0lEQVR4nGNgGLaAkYD8f2LV45JAN4CgPhYChqBrIGQBhmKSNFDVECZqGU6MQUQBbIGNDgglEZyArHDC5zVshuG0hGoJkmpZZBgDAFJLEQiuw3Y4AAAAAElFTkSuQmCC';
let tray = null;
let win = null;
let client = null;
let refreshTimer = null;
let reconnectTimer = null;
let loginPollTimer = null;
let state = { status: '시작 중', loggedIn: false, usage: null, error: null };

function binaryPath() {
  if (app.isPackaged) return path.join(process.resourcesPath, 'vendor', 'codex');
  const bundled = path.join(__dirname, '..', 'vendor', 'codex');
  return fs.existsSync(bundled) ? bundled : 'codex';
}
function codexHome() {
  const dir = path.join(app.getPath('userData'), 'codex-home');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
function formatReset(timestamp) {
  if (!timestamp) return '-';
  return new Intl.DateTimeFormat('ko-KR', { month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(timestamp * 1000));
}
function snapshot() { return JSON.parse(JSON.stringify(state)); }
function publish() {
  updateTray();
  if (win && !win.isDestroyed()) win.webContents.send('state', snapshot());
}
function setState(patch) { state = { ...state, ...patch }; publish(); }
function menuTitle() {
  if (state.usage?.weekly) return `C ${state.usage.weekly.remainingPercent}%`;
  if (!state.loggedIn && state.status === '로그인 필요') return 'C 로그인';
  if (state.error) return 'C !';
  return 'C --';
}
function openWindow() {
  if (win && !win.isDestroyed()) { win.show(); win.focus(); return; }
  win = new BrowserWindow({
    width: 470,
    height: 650,
    minWidth: 430,
    minHeight: 560,
    title: 'Codex 사용량',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  win.loadFile(path.join(__dirname, 'index.html'));
  win.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      win.hide();
    }
  });
  win.webContents.on('did-finish-load', () => publish());
}
function updateTray() {
  if (!tray) return;
  tray.setTitle(menuTitle(), { fontType: 'monospacedDigit' });
  const weekly = state.usage?.weekly ? `주간 ${state.usage.weekly.remainingPercent}% 남음` : state.status;
  const short = state.usage?.shortTerm ? `단기 ${state.usage.shortTerm.remainingPercent}% 남음` : '단기 한도 표시 없음';
  const reset = state.usage?.weekly ? `초기화 ${formatReset(state.usage.weekly.resetsAt)}` : '초기화 -';
  tray.setToolTip(`${weekly}\n${reset}`);
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: weekly, enabled: false },
    { label: short, enabled: false },
    { label: reset, enabled: false },
    { type: 'separator' },
    { label: '사용량 창 열기', click: openWindow },
    { label: '지금 새로고침', click: () => refreshUsage(true) },
    { label: 'ChatGPT 로그인', visible: !state.loggedIn, click: startLogin },
    { label: '공식 사용량 페이지 열기', click: () => shell.openExternal(OFFICIAL_USAGE_URL) },
    { type: 'separator' },
    {
      label: 'Mac 로그인 시 자동 실행',
      type: 'checkbox',
      checked: app.getLoginItemSettings().openAtLogin,
      click: (item) => app.setLoginItemSettings({ openAtLogin: item.checked })
    },
    { label: '종료', click: () => { app.isQuitting = true; app.quit(); } }
  ]));
}
function friendly(error) {
  const raw = error?.message || String(error);
  if (/permission denied|EACCES/i.test(raw)) return '내장 Codex 엔진 실행 권한을 확인하지 못했습니다.';
  if (/unauth|not logged|login|required/i.test(raw)) return null;
  return raw.slice(0, 260);
}
async function refreshUsage(showWindow = false) {
  try {
    setState({ status: '확인 중', error: null });
    const accountResult = await client.readAccount();
    const account = accountResult?.account || null;
    if (!account) {
      setState({ status: '로그인 필요', loggedIn: false, usage: null, error: null });
      if (showWindow) openWindow();
      return;
    }
    const result = await client.readRateLimits();
    const usage = normalizeUsage(result);
    if (!usage) throw new Error('사용량 데이터가 비어 있습니다. 잠시 후 다시 확인하세요.');
    setState({ status: '정상', loggedIn: true, usage, error: null });
    if (showWindow) openWindow();
  } catch (error) {
    const message = friendly(error);
    if (message === null) setState({ status: '로그인 필요', loggedIn: false, usage: null, error: null });
    else setState({ status: '오류', error: message });
    if (showWindow) openWindow();
  }
}
function startLoginPolling() {
  clearInterval(loginPollTimer);
  let attempts = 0;
  loginPollTimer = setInterval(async () => {
    attempts += 1;
    await refreshUsage();
    if (state.loggedIn || attempts >= 90) {
      clearInterval(loginPollTimer);
      loginPollTimer = null;
    }
  }, 2000);
}
async function startLogin() {
  try {
    openWindow();
    setState({ status: '로그인 진행 중', error: null });
    const result = await client.startLogin();
    const url = result?.authUrl || result?.auth_url;
    if (!url) throw new Error('로그인 주소를 받지 못했습니다.');
    await shell.openExternal(url);
    startLoginPolling();
  } catch (error) {
    setState({ status: '오류', error: friendly(error) });
  }
}
async function logout() {
  try {
    await client.logout();
    setState({ status: '로그인 필요', loggedIn: false, usage: null, error: null });
    openWindow();
  } catch (error) {
    setState({ status: '오류', error: friendly(error) });
  }
}
function makeClient() {
  const c = new CodexClient({ binaryPath: binaryPath(), codexHome: codexHome() });
  c.on('notification', async (msg) => {
    if (msg.method === 'account/login/completed' || msg.method === 'account/updated' || msg.method === 'account/rateLimits/updated') {
      await refreshUsage();
    }
  });
  c.on('disconnected', (error) => {
    setState({ status: '재연결 중', error: friendly(error) });
    scheduleReconnect();
  });
  c.on('error', (error) => setState({ status: '오류', error: friendly(error) }));
  return c;
}
function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(async () => {
    try {
      if (client) client.stop();
      client = makeClient();
      await client.start();
      await refreshUsage();
    } catch (error) {
      setState({ status: '재연결 중', error: friendly(error) });
      scheduleReconnect();
    }
  }, 8000);
}

ipcMain.handle('state:get', () => snapshot());
ipcMain.handle('account:login', startLogin);
ipcMain.handle('account:logout', logout);
ipcMain.handle('usage:refresh', () => refreshUsage(false));
ipcMain.handle('usage:official', () => shell.openExternal(OFFICIAL_USAGE_URL));

app.whenReady().then(async () => {
  app.setName('Codex Usage');
  app.setLoginItemSettings({ openAtLogin: true });
  const icon = nativeImage.createFromDataURL(TRAY_ICON_DATA);
  icon.setTemplateImage(true);
  tray = new Tray(icon);
  tray.on('click', openWindow);
  updateTray();
  client = makeClient();
  try {
    await client.start();
    await refreshUsage();
  } catch (error) {
    setState({ status: '오류', error: friendly(error) });
    scheduleReconnect();
  }
  if (!state.loggedIn) openWindow();
  refreshTimer = setInterval(() => refreshUsage(), 60 * 1000);
});
app.on('activate', openWindow);
app.on('window-all-closed', () => {});
app.on('before-quit', () => {
  app.isQuitting = true;
  clearInterval(refreshTimer);
  clearInterval(loginPollTimer);
  clearTimeout(reconnectTimer);
  if (client) client.stop();
});
