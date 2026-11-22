const { app, BrowserWindow, dialog, session, shell } = require("electron");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const { externalUrl, assetPath, sameOrigin, clipboardPermission, csp } = require("./security.cjs");

const origin = "http://127.0.0.1:5174";
let server;
const mime = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
  ".woff2": "font/woff2"
};

async function serveAssets() {
  const root = app.isPackaged ? path.join(process.resourcesPath, "web")
    : path.resolve(__dirname, "..", "web", "dist");
  if (!fs.existsSync(path.join(root, "index.html"))) {
    throw new Error("Web assets are missing. Run npm run build before starting or packaging the desktop client.");
  }
  server = http.createServer((req, res) => {
    res.setHeader("Content-Security-Policy", csp);
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Referrer-Policy", "no-referrer");
    res.setHeader("Cache-Control", "no-store");
    if (req.headers.host !== "127.0.0.1:5174" || !["GET", "HEAD"].includes(req.method)) {
      res.writeHead(403); res.end(); return;
    }
    let pathname;
    try { pathname = new URL(req.url, origin).pathname; } catch {
      res.writeHead(400); res.end(); return;
    }
    const requested = assetPath(root, pathname === "/" ? "/index.html" : pathname);
    if (!requested) { res.writeHead(403); res.end(); return; }
    const file = fs.existsSync(requested) && fs.statSync(requested).isFile() ? requested
      : !path.extname(pathname) ? path.join(root, "index.html") : null;
    if (!file) { res.writeHead(404); res.end(); return; }
    res.setHeader("Content-Type", mime[path.extname(file)] || "application/octet-stream");
    if (req.method === "HEAD") { res.end(); return; }
    const stream = fs.createReadStream(file);
    stream.on("error", () => { if (!res.headersSent) res.writeHead(500); res.end(); });
    stream.pipe(res);
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(5174, "127.0.0.1", resolve);
  });
}

function openWindow() {
  const window = new BrowserWindow({
    width: 1200, height: 850, minWidth: 700, minHeight: 500,
    webPreferences: {
      nodeIntegration: false, contextIsolation: true, sandbox: true,
      webSecurity: true, allowRunningInsecureContent: false,
      partition: "jobhunt-session"
    }
  });
  window.webContents.on("will-navigate", (event, url) => {
    if (!sameOrigin(url, origin)) {
      event.preventDefault();
      const safe = externalUrl(url);
      if (safe) void shell.openExternal(safe);
    }
  });
  window.webContents.on("will-redirect", (event, url) => {
    if (!sameOrigin(url, origin)) event.preventDefault();
  });
  window.webContents.on("will-attach-webview", event => event.preventDefault());
  window.webContents.setWindowOpenHandler(({ url }) => {
    const safe = externalUrl(url);
    if (safe) void shell.openExternal(safe);
    return { action: "deny" };
  });
  void window.loadURL(origin);
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => {
    const window = BrowserWindow.getAllWindows()[0];
    if (window) { if (window.isMinimized()) window.restore(); window.focus(); }
  });
  app.whenReady().then(async () => {
    const uiSession = session.fromPartition("jobhunt-session");
    uiSession.setPermissionRequestHandler((contents, permission, callback, details) => {
      callback(clipboardPermission(permission, contents.getURL(), details.requestingUrl, origin));
    });
    uiSession.setPermissionCheckHandler((contents, permission, requestingOrigin) =>
      clipboardPermission(permission, contents?.getURL() ?? "", requestingOrigin, origin));
    await serveAssets();
    openWindow();
    app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) openWindow(); });
  }).catch(error => {
    dialog.showErrorBox("Job Hunt cannot start", error.code === "EADDRINUSE"
      ? "Loopback port 5174 is already in use. Close the conflicting local service and restart Job Hunt."
      : error.message);
    app.quit();
  });
  app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
  app.on("before-quit", () => { if (server) server.close(); });
}
