import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const windows = process.platform === "win32";
const available = command => spawnSync(command, ["--version"], {
  stdio: "ignore", shell: false
}).status === 0;
const venv = path.join(root, ".venv", windows ? "Scripts" : "bin", windows ? "python.exe" : "python");
let command;
let prefix;
if (process.env.JOBHUNT_PYTHON) {
  command = process.env.JOBHUNT_PYTHON; prefix = ["-m", "jobhunt.web"];
} else if (existsSync(venv)) {
  command = venv; prefix = ["-m", "jobhunt.web"];
} else if (available("uv")) {
  command = "uv"; prefix = ["run", "--extra", "web", "--extra", "docs", "python", "-m", "jobhunt.web"];
} else {
  command = ["python3", "python"].find(available);
  if (!command) throw new Error("Install uv or Python, then install this project with its web and docs extras.");
  prefix = ["-m", "jobhunt.web"];
}
const child = spawn(command, [...prefix, ...args], { cwd: root, stdio: "inherit", shell: false });
child.on("error", error => { console.error(`Backend launch failed: ${error.message}`); process.exitCode = 1; });
child.on("exit", (code, signal) => { process.exitCode = signal ? 1 : code ?? 1; });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
