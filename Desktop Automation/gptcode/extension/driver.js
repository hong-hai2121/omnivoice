import { pageTask } from "./dom.js";
import { isTikTok } from "./model.js";

const autoAttach = { autoAttach: true, waitForDebuggerOnStart: false, flatten: true, filter: [{ type: "iframe", exclude: false }] };

export class TabDriver {
  constructor(tabId, check, selectors = {}) {
    this.tabId = tabId; this.check = check; this.selectors = selectors;
    this.contexts = new Map(); this.sessions = new Set([""]); this.current = null;
    this.focusSessions = new Set(); this.keepFocus = false;
    this.listener = (source, method, params) => {
      if (source.tabId !== this.tabId) return;
      const sessionId = source.sessionId || "";
      if (method === "Target.attachedToTarget") {
        this.sessions.add(params.sessionId);
        const target = { tabId, sessionId: params.sessionId };
        chrome.debugger.sendCommand(target, "Runtime.enable").catch(() => {});
        chrome.debugger.sendCommand(target, "Target.setAutoAttach", autoAttach).catch(() => {});
      } else if (method === "Runtime.executionContextCreated" && params.context.auxData?.isDefault) {
        const ctx = params.context;
        this.contexts.set(`${sessionId}:${ctx.id}`, { sessionId, contextId: ctx.id, origin: ctx.origin });
      } else if (method === "Runtime.executionContextDestroyed") {
        this.contexts.delete(`${sessionId}:${params.executionContextId}`);
      } else if (method === "Runtime.executionContextsCleared") {
        for (const [key, ctx] of this.contexts) if (ctx.sessionId === sessionId) this.contexts.delete(key);
      } else if (method === "Target.detachedFromTarget") {
        this.sessions.delete(params.sessionId);
        for (const [key, ctx] of this.contexts) if (ctx.sessionId === params.sessionId) this.contexts.delete(key);
      } else if (method === "Page.fileChooserOpened") {
        this.chooser = { sessionId, backendNodeId: params.backendNodeId };
      }
    };
  }
  async attach() {
    chrome.debugger.onEvent.addListener(this.listener);
    try {
      await chrome.debugger.attach({ tabId: this.tabId }, "1.3"); this.attached = true;
      await this.command("Runtime.enable");
      await this.command("Target.setAutoAttach", autoAttach);
      await this.command("Page.enable");
    } catch (error) { await this.close(); throw error; }
  }
  async close() {
    chrome.debugger.onEvent.removeListener(this.listener);
    // Cleanup must bypass command()/check(): Stop and navigation also release focus.
    for (const sessionId of this.focusSessions) {
      await chrome.debugger.sendCommand({ tabId: this.tabId, ...(sessionId ? { sessionId } : {}) },
        "Emulation.setFocusEmulationEnabled", { enabled: false }).catch(() => {});
    }
    this.focusSessions.clear(); this.keepFocus = false;
    if (this.attached) await chrome.debugger.detach({ tabId: this.tabId }).catch(() => {});
    this.attached = false;
  }
  async emulateFocus(sessionId = "") {
    if (this.focusSessions.has(sessionId)) return;
    await this.command("Emulation.setFocusEmulationEnabled", { enabled: true }, sessionId);
    this.focusSessions.add(sessionId);
  }
  async keepPageActive() {
    // Virtual page focus; never activate a Chrome tab/window or move the OS focus.
    this.keepFocus = true;
    await this.emulateFocus();
    if (this.current?.sessionId) await this.emulateFocus(this.current.sessionId);
  }
  async command(method, params = {}, sessionId = "") {
    await this.check();
    return chrome.debugger.sendCommand({ tabId: this.tabId, ...(sessionId ? { sessionId } : {}) }, method, params);
  }
  async evaluate(context, action, data = {}, object = false) {
    const result = await this.command("Runtime.evaluate", {
      expression: `(${pageTask.toString()})(${JSON.stringify(action)},${JSON.stringify({ ...data, selectors: this.selectors })})`,
      returnByValue: !object, userGesture: true,
      ...(context?.contextId ? { contextId: context.contextId } : {}),
    }, context?.sessionId);
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return object ? result.result : result.result.value;
  }
  async dom(action, data = {}, object = false) {
    return this.evaluate(this.current, action, data, object);
  }
  async publicationState() {
    // A redirect may destroy the upload iframe; inspect the new top-level document first.
    const content = await this.evaluate(null, 'contentPosts');
    if (content.page) { this.current = null; return { state: 'content', content }; }
    return this.dom('publishOutcome');
  }
  async probes() {
    const found = [];
    for (const context of this.contexts.size ? this.contexts.values() : [{}]) {
      // Do not inspect unrelated advertising/account-provider frames.
      if (context.origin && context.origin !== "://" && context.origin !== "null" && !isTikTok(context.origin)) continue;
      try { found.push({ context, info: await this.evaluate(context, "probe") }); } catch { /* Navigation replaces execution contexts. */ }
    }
    return found;
  }
  async findEditor() {
    const candidates = (await this.probes()).filter(item => item.info.caption);
    if (candidates.length > 1) throw new Error("Có nhiều khung mô tả. Chỉ giữ một bản nháp TikTok đang mở.");
    if (!candidates.length) return false;
    this.current = candidates[0].context;
    if (this.keepFocus) await this.emulateFocus(this.current.sessionId);
    return true;
  }
  async fileInput() {
    const probes = await this.probes();
    const candidates = probes.filter(item => item.info.fileCount > 0);
    if (candidates.length > 1) throw new Error("Có ô tải video ở nhiều iframe. Xuất chẩn đoán để xác định đúng khung tải lên.");
    if (candidates.length === 1) {
      this.current = candidates[0].context;
      const input = await this.dom("file", {}, true);
      return { objectId: input.objectId, sessionId: this.current.sessionId };
    }
    if (this.chooser?.backendNodeId) {
      const { object } = await this.command("DOM.resolveNode", { backendNodeId: this.chooser.backendNodeId }, this.chooser.sessionId);
      return { objectId: object.objectId, sessionId: this.chooser.sessionId };
    }
    return null;
  }
  async openFileControl() {
    const candidates = (await this.probes()).filter(item => item.info.uploadTrigger);
    if (candidates.length !== 1) return false;
    const ctx = candidates[0].context;
    await this.command("Page.enable", {}, ctx.sessionId);
    await this.command("Page.setInterceptFileChooserDialog", { enabled: true }, ctx.sessionId);
    await this.evaluate(ctx, "openUpload");
    return true;
  }
  async inspect(withScreenshot = false) {
    const frames = [];
    for (const { context } of await this.probes()) {
      try { frames.push(await this.evaluate(context, "inspect")); } catch { /* Frame navigated. */ }
    }
    const result = { tabId: this.tabId, frames };
    if (withScreenshot) {
      try {
        const screenshot = await this.command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false }, "");
        result.screenshot = "data:image/png;base64," + screenshot.data;
      } catch (error) { result.screenshotError = error.message; }
    }
    return result;
  }
}
