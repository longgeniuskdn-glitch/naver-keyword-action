'use strict';
const { EventEmitter } = require('events');
const { spawn } = require('child_process');
const readline = require('readline');

class CodexClient extends EventEmitter {
  constructor({ binaryPath, codexHome }) {
    super();
    this.binaryPath = binaryPath;
    this.codexHome = codexHome;
    this.proc = null;
    this.nextId = 1;
    this.pending = new Map();
    this.ready = false;
    this.stopping = false;
  }
  async start() {
    if (this.ready) return;
    this.stopping = false;
    this.proc = spawn(this.binaryPath, ['app-server'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, CODEX_HOME: this.codexHome }
    });
    this.proc.on('error', (error) => this._fail(error));
    this.proc.on('exit', (code, signal) => {
      this.ready = false;
      const error = new Error(`Codex 엔진 종료 (code=${code}, signal=${signal || 'none'})`);
      this._rejectAll(error);
      if (!this.stopping) this.emit('disconnected', error);
    });
    readline.createInterface({ input: this.proc.stdout }).on('line', (line) => this._onLine(line));
    this.proc.stderr.on('data', (chunk) => this.emit('stderr', chunk.toString()));
    await this.request('initialize', {
      clientInfo: { name: 'codex_usage_direct', title: 'Codex Usage', version: '0.2.0' },
      capabilities: {}
    }, 20000);
    this.notify('initialized', {});
    this.ready = true;
    this.emit('connected');
  }
  stop() {
    this.stopping = true;
    this._rejectAll(new Error('Codex engine stopped'));
    if (this.proc && !this.proc.killed) this.proc.kill('SIGTERM');
    this.proc = null;
    this.ready = false;
  }
  async ensureStarted() { if (!this.ready) await this.start(); }
  async readAccount() { await this.ensureStarted(); return this.request('account/read', { refreshToken: false }); }
  async readRateLimits() { await this.ensureStarted(); return this.request('account/rateLimits/read'); }
  async startLogin() {
    await this.ensureStarted();
    return this.request('account/login/start', {
      type: 'chatgpt',
      useHostedLoginSuccessPage: true,
      appBrand: 'codex'
    }, 20000);
  }
  async logout() { await this.ensureStarted(); return this.request('account/logout'); }
  request(method, params, timeoutMs = 15000) {
    if (!this.proc || !this.proc.stdin.writable) return Promise.reject(new Error('Codex 엔진에 연결되지 않았습니다.'));
    const id = this.nextId++;
    const payload = { method, id };
    if (params !== undefined) payload.params = params;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} 응답 시간 초과`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timeout, method });
      this.proc.stdin.write(`${JSON.stringify(payload)}\n`);
    });
  }
  notify(method, params) {
    if (!this.proc || !this.proc.stdin.writable) return;
    const payload = { method };
    if (params !== undefined) payload.params = params;
    this.proc.stdin.write(`${JSON.stringify(payload)}\n`);
  }
  _onLine(line) {
    const trimmed = line.trim();
    if (!trimmed) return;
    let msg;
    try { msg = JSON.parse(trimmed); } catch { return; }
    if (msg.id !== undefined && this.pending.has(msg.id)) {
      const pending = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      clearTimeout(pending.timeout);
      if (msg.error) pending.reject(new Error(msg.error.message || JSON.stringify(msg.error)));
      else pending.resolve(msg.result);
      return;
    }
    if (msg.method) this.emit('notification', msg);
  }
  _fail(error) {
    this.ready = false;
    this._rejectAll(error);
    this.emit('error', error);
  }
  _rejectAll(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timeout);
      pending.reject(error);
    }
    this.pending.clear();
  }
}
module.exports = { CodexClient };
