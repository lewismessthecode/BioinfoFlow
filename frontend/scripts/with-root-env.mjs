import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const VALID_COMMANDS = new Set(["dev", "build", "start"]);

function parseEnvFile(filePath) {
  const parsed = {};
  if (!fs.existsSync(filePath)) return parsed;

  const content = fs.readFileSync(filePath, "utf8");

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const match = rawLine.match(
      /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/,
    );
    if (!match) continue;

    const [, key, rawValue] = match;
    let value = rawValue.trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      const quote = value[0];
      value = value.slice(1, -1);
      if (quote === '"') {
        value = value
          .replace(/\\n/g, "\n")
          .replace(/\\r/g, "\r")
          .replace(/\\t/g, "\t")
          .replace(/\\"/g, '"')
          .replace(/\\\\/g, "\\");
      }
    } else {
      value = value.replace(/\s+#.*$/, "").trim();
    }

    parsed[key] = value;
  }

  return parsed;
}

function applyFileEnv(targetEnv, shellKeys, filePath) {
  const parsed = parseEnvFile(filePath);
  for (const [key, value] of Object.entries(parsed)) {
    if (shellKeys.has(key)) continue;
    targetEnv[key] = value;
  }
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(frontendDir, "..");
const nextBin = path.join(frontendDir, "node_modules", "next", "dist", "bin", "next");

const [command, ...args] = process.argv.slice(2);
if (!VALID_COMMANDS.has(command)) {
  console.error("Usage: node scripts/with-root-env.mjs <dev|build|start> [...args]");
  process.exit(1);
}

if (!fs.existsSync(nextBin)) {
  console.error("Next.js is not installed yet. Run `bun install` in frontend/ first.");
  process.exit(1);
}

const shellKeys = new Set(Object.keys(process.env));
const env = { ...process.env };

applyFileEnv(env, shellKeys, path.join(repoRoot, ".env"));
applyFileEnv(env, shellKeys, path.join(frontendDir, ".env.local"));

const child = spawn(process.execPath, [nextBin, command, ...args], {
  cwd: frontendDir,
  env,
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
