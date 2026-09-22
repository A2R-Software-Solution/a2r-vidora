// Run against a local Vite server. Uses an isolated headless Chrome profile and
// blocks all non-local network requests, including analytics and backend calls.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const origin = process.env.FRONTEND_TEST_URL || "http://127.0.0.1:5175";
assert(["127.0.0.1", "localhost"].includes(new URL(origin).hostname), "Use a local frontend server");
const profile = await mkdtemp(join(tmpdir(), "vidora-public-pages-"));
const browser = spawn(process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank",
], { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] });

let socket;
let browserLog = "";
browser.stderr.on("data", (chunk) => { browserLog = (browserLog + chunk.toString()).slice(-2000); });
try {
  const endpoint = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("Chrome did not start")), 15000);
    browser.once("error", reject);
    browser.stderr.on("data", (chunk) => {
      const match = chunk.toString().match(/DevTools listening on (ws:\/\/\S+)/);
      if (match) { clearTimeout(timeout); resolve(match[1]); }
    });
  });
  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  let sequence = 0;
  let sessionId;
  const pending = new Map();
  const runtimeErrors = [];
  const call = (method, params = {}, session = sessionId) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`Chrome timed out: ${method}\n${browserLog}`)); }, 15000);
    pending.set(id, {
      resolve: (value) => { clearTimeout(timeout); resolve(value); },
      reject: (error) => { clearTimeout(timeout); reject(error); },
    });
    socket.send(JSON.stringify({ id, method, params, ...(session ? { sessionId: session } : {}) }));
  });
  socket.addEventListener("close", () => {
    for (const waiter of pending.values()) waiter.reject(new Error(`Chrome disconnected\n${browserLog}`));
    pending.clear();
  });
  socket.addEventListener("message", ({ data }) => {
    const message = JSON.parse(data);
    if (message.id) {
      const waiter = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) waiter?.reject(new Error(message.error.message));
      else waiter?.resolve(message.result);
    } else if (message.method === "Fetch.requestPaused") {
      const { request, requestId } = message.params;
      const local = request.url.startsWith(`${origin}/`);
      void call(local ? "Fetch.continueRequest" : "Fetch.failRequest",
        local ? { requestId } : { requestId, errorReason: "BlockedByClient" });
    } else if (message.method === "Runtime.exceptionThrown") {
      runtimeErrors.push(message.params.exceptionDetails.text);
    }
  });
  const target = await call("Target.createTarget", { url: "about:blank" }, null);
  ({ sessionId } = await call("Target.attachToTarget", { targetId: target.targetId, flatten: true }, null));
  await call("Page.enable");
  await call("Runtime.enable");
  await call("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
  const evaluate = async (expression) => {
    const result = await call("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  const waitFor = async (expression) => {
    const deadline = Date.now() + 10000;
    while (Date.now() < deadline) {
      if (await evaluate(expression)) return;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error(`Timed out: ${expression}`);
  };
  const navigate = async (path) => {
    await call("Page.navigate", { url: `${origin}${path}` });
    await waitFor('!!document.querySelector(".site-footer")');
  };
  const viewport = (width, height = 900) => call("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
  const screenshot = async (name) => {
    const { data } = await call("Page.captureScreenshot", { format: "png" });
    const path = join(profile, `${name}.png`);
    await writeFile(path, Buffer.from(data, "base64"));
    console.log(`Screenshot: ${path}`);
  };

  await viewport(1440);
  for (const path of ["/about", "/how-it-works", "/privacy", "/terms", "/contact"]) {
    await navigate(path);
    assert.equal(await evaluate("location.pathname"), path);
    assert.equal(await evaluate('document.querySelectorAll("main h1").length'), 1);
    assert.equal(await evaluate('getComputedStyle(document.querySelector(".public-toc")).position'), "static");
    assert.equal(await evaluate('document.querySelector(".site-footer [aria-current=page]").getAttribute("href")'), path);
    assert(await evaluate('document.title.endsWith("| Vidora AI")'));
    assert(await evaluate(`!!document.querySelector('a[href="mailto:hr@a2rsoftwaresolution.com"]')`));
  }
  await navigate("/privacy/");
  assert(await evaluate('document.title.startsWith("Privacy Policy")'));
  await evaluate(`window.__navigationSentinel = 123; document.querySelector('.site-footer a[href="/terms"]').click()`);
  await waitFor('document.title.startsWith("Terms of Use")');
  assert.equal(await evaluate("window.__navigationSentinel"), 123, "Internal links should preserve the app session");
  await evaluate("history.back()");
  await waitFor('document.title.startsWith("Privacy Policy")');
  await evaluate(`document.querySelector('.public-toc a[href="#cookies"]').click()`);
  await waitFor('location.hash === "#cookies"');
  assert(await evaluate('document.getElementById("cookies").getBoundingClientRect().top >= 72'));
  await navigate("/privacy");
  await screenshot("privacy-desktop");

  await navigate("/");
  await evaluate("window.scrollTo(0, 380)");
  await new Promise((resolve) => setTimeout(resolve, 850));
  assert(await evaluate('document.querySelector(".input-wrap").getBoundingClientRect().top > 72'));
  await screenshot("home-form-desktop");
  await evaluate(`
    const field = document.querySelector('.input-wrap input');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(field, 'https://youtu.be/draft-link');
    field.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('.site-footer a[href="/privacy"]').click();
  `);
  await waitFor('document.title.startsWith("Privacy Policy")');
  assert(await evaluate('document.querySelector(".home-content").hidden'));
  await evaluate('document.querySelector(".public-back").click()');
  await waitFor('location.pathname === "/" && !document.querySelector(".home-content").hidden');
  assert.equal(await evaluate('document.querySelector(".input-wrap input").value'), "https://youtu.be/draft-link", "Keep the video-link draft while reading policies");
  await evaluate('document.querySelector(".site-footer").scrollIntoView()');
  await new Promise((resolve) => setTimeout(resolve, 250));
  assert(await evaluate('document.querySelector(".hero-scene").getBoundingClientRect().bottom <= document.querySelector(".site-footer").getBoundingClientRect().top + 1'));
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".site-footer nav")).position'), "static");
  await screenshot("footer-desktop");

  for (const width of [320, 375, 768]) {
    await viewport(width, 812);
    for (const path of ["/", "/privacy", "/contact"]) {
      await navigate(path);
      assert(await evaluate("document.documentElement.scrollWidth <= innerWidth"), `Horizontal overflow at ${width} on ${path}`);
      await evaluate('document.querySelector(".site-footer").scrollIntoView()');
      assert(await evaluate('document.querySelector(".site-footer").getBoundingClientRect().bottom <= innerHeight + 1'));
    }
    if (width === 375) {
      await screenshot("footer-mobile");
      await navigate("/privacy");
      await screenshot("privacy-mobile");
    }
  }
  await viewport(1440);
  await call("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await navigate("/");
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".hero-stage")).position'), "relative");
  await navigate("/this-page-does-not-exist");
  assert(await evaluate('document.querySelector(".public-not-found") !== null'));
  assert.deepEqual(runtimeErrors, [], "No uncaught browser exceptions");
  console.log("PASS: public deep links, SPA/back navigation, anchors, desktop/mobile footer, reduced motion, and 404 page.");
} finally {
  socket?.close();
  browser.kill();
}
