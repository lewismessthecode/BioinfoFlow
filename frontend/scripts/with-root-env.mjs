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

export function redactSecret(value) {
  return value ? "set" : "unset";
}

export function collectStartupSummaryEnv(env, command, args) {
  return {
    nodeEnv: env.NODE_ENV || (command === "dev" ? "development" : "production"),
    hostname: valueAfterFlag(args, "--hostname") || env.HOSTNAME || "0.0.0.0",
    port: valueAfterFlag(args, "--port") || env.PORT || (command === "dev" ? "3000" : "3000"),
    apiBaseUrl: env.NEXT_PUBLIC_API_BASE_URL || "",
    betterAuthUrl: env.BETTER_AUTH_URL || "",
    authMode: env.NEXT_PUBLIC_AUTH_MODE || env.AUTH_MODE || "",
    localAuthEnabled:
      env.NEXT_PUBLIC_AUTH_LOCAL_ENABLED || env.AUTH_LOCAL_ENABLED || "",
    selfSignupEnabled:
      env.NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED
      || env.AUTH_SELF_SIGNUP_ENABLED
      || "",
    betterAuthSecret: redactSecret(env.BETTER_AUTH_SECRET),
    bioinfoflowHome: env.BIOINFOFLOW_HOME || "",
    bioinfoflowHomeHost: env.BIOINFOFLOW_HOME_HOST || "",
    betterAuthDbPath: env.BETTER_AUTH_DB_PATH || "",
  };
}

export function buildStartupSummary({
  command,
  args,
  frontendDir,
  repoRoot,
  nextBin,
  serverJs,
  loadedEnvFiles,
  env,
  startupEnv = env ? collectStartupSummaryEnv(env, command, args) : {},
  versions = { node: process.version },
}) {
  return {
    service: "frontend",
    command,
    args,
    cwd: frontendDir,
    repo_root: repoRoot,
    node: versions.node,
    runtime: {
      node_env: startupEnv.nodeEnv || "",
      next_bin: nextBin,
      standalone_server: serverJs || null,
    },
    env_files: loadedEnvFiles,
    network: {
      hostname: startupEnv.hostname || "",
      port: startupEnv.port || "",
      api_base_url: startupEnv.apiBaseUrl || "",
      better_auth_url: startupEnv.betterAuthUrl || "",
    },
    auth: {
      mode: startupEnv.authMode || "",
      local_enabled: startupEnv.localAuthEnabled || "",
      self_signup_enabled: startupEnv.selfSignupEnabled || "",
      better_auth_secret: startupEnv.betterAuthSecret || "unset",
    },
    storage: {
      bioinfoflow_home: startupEnv.bioinfoflowHome || "",
      bioinfoflow_home_host: startupEnv.bioinfoflowHomeHost || "",
      better_auth_db_path: startupEnv.betterAuthDbPath || "",
    },
  };
}

export function formatStartupSummary(summary) {
  return [
    "Bioinfoflow frontend startup",
    JSON.stringify(summary, null, 2),
  ].join("\n");
}

function valueAfterFlag(args, flag) {
  const index = args.indexOf(flag);
  if (index === -1) return "";
  return args[index + 1] || "";
}

function isCliEntrypoint() {
  const thisFile = fileURLToPath(import.meta.url);
  const invoked = process.argv[1] ? path.resolve(process.argv[1]) : "";
  return thisFile === invoked;
}

function runCli() {
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const frontendDir = path.resolve(scriptDir, "..");
  const repoRoot = path.resolve(frontendDir, "..");
  const nextBin = path.join(frontendDir, "node_modules", "next", "dist", "bin", "next");
  const serverJs = path.join(frontendDir, "server.js");

  const [command, ...args] = process.argv.slice(2);
  if (!VALID_COMMANDS.has(command)) {
    console.error("Usage: node scripts/with-root-env.mjs <dev|build|start> [...args]");
    process.exit(1);
  }

  const useStandaloneServer = command === "start" && fs.existsSync(serverJs);
  if (!useStandaloneServer && !fs.existsSync(nextBin)) {
    console.error("Next.js is not installed yet. Run `bun install` in frontend/ first.");
    process.exit(1);
  }

  const shellKeys = new Set(Object.keys(process.env));
  const env = { ...process.env };
  const envFiles = [
    path.join(repoRoot, ".env"),
    path.join(frontendDir, ".env.local"),
  ];

  for (const envFile of envFiles) {
    applyFileEnv(env, shellKeys, envFile);
  }

  console.info(
    formatStartupSummary(
      buildStartupSummary({
        command,
        args,
        frontendDir,
        repoRoot,
        nextBin: useStandaloneServer ? "" : nextBin,
        serverJs: useStandaloneServer ? serverJs : "",
        loadedEnvFiles: envFiles.map((filePath) => ({
          path: filePath,
          exists: fs.existsSync(filePath),
        })),
        startupEnv: collectStartupSummaryEnv(env, command, args),
      }),
    ),
  );

  const childArgs = useStandaloneServer
    ? [serverJs, ...args]
    : [nextBin, command, ...args];
  const child = spawn(process.execPath, childArgs, {
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
}

if (isCliEntrypoint()) {
  runCli();
}
