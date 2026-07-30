'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('bridge', {
  getState: () => ipcRenderer.invoke('state:get'),
  login: () => ipcRenderer.invoke('account:login'),
  logout: () => ipcRenderer.invoke('account:logout'),
  refresh: () => ipcRenderer.invoke('usage:refresh'),
  openOfficial: () => ipcRenderer.invoke('usage:official'),
  onState: (callback) => ipcRenderer.on('state', (_event, state) => callback(state))
});
