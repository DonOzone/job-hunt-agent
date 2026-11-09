const path = require("node:path");

function externalUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password
      ? url.href : null;
  } catch { return null; }
}

function sameOrigin(value, origin) {
  try { return new URL(value).origin === origin; } catch { return false; }
}

function clipboardPermission(permission, pageUrl, requestingOrigin, origin) {
  return permission === "clipboard-sanitized-write" &&
    sameOrigin(pageUrl, origin) && sameOrigin(requestingOrigin, origin);
}

function assetPath(root, pathname) {
  let decoded;
  try { decoded = decodeURIComponent(pathname); } catch { return null; }
  if (decoded.includes("\0") || decoded.includes("\\") || decoded.split("/").includes("..")) return null;
  const candidate = path.resolve(root, "." + decoded);
  return candidate.startsWith(path.resolve(root) + path.sep) ? candidate : null;
}

const csp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self' https: http://127.0.0.1:* http://localhost:*",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
  "form-action 'none'"
].join("; ");

module.exports = { externalUrl, assetPath, sameOrigin, clipboardPermission, csp };
