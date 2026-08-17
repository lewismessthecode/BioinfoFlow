import { Context } from "@deepseek-ai/cordis";
import { LocalSandboxProvider } from "@deepseek-ai/dsh-sandbox-local";
import { readFileSync, realpathSync, statSync } from "node:fs";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";

import { hardenConfinement, serializeConfinement } from "./worker.mjs";


export function normalizeExecutionRequest(value) {
  const allowed = new Set([
    "version", "argv", "cwd", "environment", "mode", "workspace_root",
    "protected_endpoints", "timeout_ms", "capture_limit", "cwd_inode",
    "workspace_inode",
  ]);
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("execution request must be a JSON object");
  }
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new Error(`execution request contains unknown field: ${key}`);
  }
  if (value.version !== 1) throw new Error("unsupported execution protocol version");
  if (!Array.isArray(value.argv) || value.argv.length === 0
      || value.argv.some((item) => typeof item !== "string" || item.length === 0)) {
    throw new Error("argv must contain non-empty strings");
  }
  if (!["read-only", "workspace-write", "danger-full-access"].includes(value.mode)) {
    throw new Error("invalid sandbox mode");
  }
  if (value.environment === null || typeof value.environment !== "object"
      || Array.isArray(value.environment)
      || Object.entries(value.environment).some(
        ([key, item]) => key.length === 0 || typeof item !== "string",
      )) {
    throw new Error("environment must map names to strings");
  }
  const cwd = realpathSync.native(value.cwd);
  const workspaceRoot = realpathSync.native(value.workspace_root);
  if (!statSync(cwd).isDirectory() || !statSync(workspaceRoot).isDirectory()) {
    throw new Error("cwd and workspace_root must be existing directories");
  }
  for (const [path, expected] of [
    [cwd, value.cwd_inode],
    [workspaceRoot, value.workspace_inode],
  ]) {
    if (expected !== null && expected !== undefined
        && statSync(path, { bigint: true }).ino.toString() !== String(expected)) {
      throw new Error("mounted execution directory identity changed");
    }
  }
  if (!Number.isSafeInteger(value.timeout_ms) || value.timeout_ms < 1) {
    throw new Error("timeout_ms must be a positive integer");
  }
  if (!Number.isSafeInteger(value.capture_limit) || value.capture_limit < 1) {
    throw new Error("capture_limit must be a positive integer");
  }
  if (!Array.isArray(value.protected_endpoints)
      || value.protected_endpoints.some((item) => typeof item !== "string")) {
    throw new Error("protected_endpoints must contain paths");
  }
  return {
    argv: [...value.argv],
    cwd,
    environment: { ...value.environment },
    mode: value.mode,
    workspaceRoot,
    protectedEndpoints: [...new Set(value.protected_endpoints)],
    timeoutMs: value.timeout_ms,
    captureLimit: value.capture_limit,
  };
}


export async function executeRequest(request, provider) {
  let confinement;
  if (request.mode === "danger-full-access") {
    confinement = {
      argv: request.argv,
      adapter: "danger-full-access",
      enforcement: null,
      denialSignatures: [],
      runnerFailureRules: [],
    };
  } else {
    confinement = hardenConfinement(
      provider.confine(request.argv, {
        mode: request.mode,
        workspaceRoot: request.workspaceRoot,
      }),
      request.protectedEndpoints,
    );
  }
  const execution = await spawnCaptured(confinement.argv, request);
  return {
    version: 1,
    status: "completed",
    ...execution,
    sandbox: request.mode === "danger-full-access"
      ? {
        mode: request.mode,
        adapter: confinement.adapter,
        enforcement: null,
        denial_signatures: [],
        runner_failure_rules: [],
      }
      : { mode: request.mode, ...serializeConfinement(confinement), argv: undefined },
  };
}


async function spawnCaptured(argv, request) {
  return await new Promise((resolve, reject) => {
    const child = spawn(argv[0], argv.slice(1), {
      cwd: request.cwd,
      env: request.environment,
      stdio: ["ignore", "pipe", "pipe"],
      detached: process.platform !== "win32",
    });
    const stdout = [];
    const stderr = [];
    let captured = 0;
    let outputLimitExceeded = false;
    let timedOut = false;
    const collect = (target) => (chunk) => {
      const remaining = request.captureLimit - captured;
      if (remaining > 0) {
        target.push(chunk.subarray(0, remaining));
        captured += Math.min(chunk.length, remaining);
      }
      if (chunk.length > remaining && !outputLimitExceeded) {
        outputLimitExceeded = true;
        killTree(child);
      }
    };
    child.stdout.on("data", collect(stdout));
    child.stderr.on("data", collect(stderr));
    child.once("error", reject);
    const timer = setTimeout(() => {
      timedOut = true;
      killTree(child);
    }, request.timeoutMs);
    child.once("close", (code, signal) => {
      clearTimeout(timer);
      resolve({
        exit_code: code ?? 128,
        signal,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
        output_limit_exceeded: outputLimitExceeded,
        timed_out: timedOut,
      });
    });
  });
}


function killTree(child) {
  try {
    if (process.platform !== "win32" && child.pid !== undefined) {
      process.kill(-child.pid, "SIGKILL");
    } else {
      child.kill("SIGKILL");
    }
  } catch {
    child.kill("SIGKILL");
  }
}


async function main() {
  const requestPath = process.argv[2];
  if (!requestPath) throw new Error("request path is required");
  const request = normalizeExecutionRequest(
    JSON.parse(readFileSync(requestPath, "utf8")),
  );
  const root = new Context();
  await root.plugin(LocalSandboxProvider);
  try {
    process.stdout.write(`${JSON.stringify(await executeRequest(request, root.sandbox))}\n`);
  } finally {
    await root.fiber.dispose();
  }
}


if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main().catch((error) => {
    process.stderr.write(`bioinfoflow-sandbox-executor: ${String(error?.stack ?? error)}\n`);
    process.exitCode = 1;
  });
}
