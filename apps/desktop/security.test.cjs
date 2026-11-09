const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { externalUrl, assetPath, clipboardPermission } = require("./security.cjs");

test("external links reject executable schemes and embedded credentials", () => {
  for (const url of ["javascript:alert(1)", "file:///etc/passwd", "https://user:pass@example.org", "not a url"])
    assert.equal(externalUrl(url), null);
  assert.equal(externalUrl("https://example.org/job"), "https://example.org/job");
});
test("asset requests cannot escape packaged directory", () => {
  const root = path.resolve("assets");
  for (const pathname of ["/../secret", "/%2e%2e/secret", "/..%5csecret", "/%00", "/%zz"])
    assert.equal(assetPath(root, pathname), null);
  assert.equal(assetPath(root, "/index.html"), path.join(root, "index.html"));
});
test("only the packaged UI can write sanitized clipboard text; reads and other permissions stay denied", () => {
  const origin = "http://127.0.0.1:5174";
  assert.equal(clipboardPermission("clipboard-sanitized-write", `${origin}/tasks`, origin, origin), true);
  for (const permission of ["clipboard-read", "clipboard-write", "media", "notifications"])
    assert.equal(clipboardPermission(permission, origin, origin, origin), false);
  assert.equal(clipboardPermission("clipboard-sanitized-write", "https://example.org", origin, origin), false);
  assert.equal(clipboardPermission("clipboard-sanitized-write", origin, "https://example.org", origin), false);
});
