import { cp, mkdir, rm, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "apps", "web", "dist");
const target = path.join(root, "src", "jobhunt", "web", "static");
await stat(path.join(source, "index.html")).catch(() => {
  throw new Error("Build the React web workspace first: npm run build --workspace @jobhunt/web");
});
await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
console.log("Packaged web assets into src/jobhunt/web/static.");
