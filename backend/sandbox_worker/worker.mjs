import { Context } from "@deepseek-ai/cordis";
import { LocalSandboxProvider } from "@deepseek-ai/dsh-sandbox-local";
import { existsSync, realpathSync, statSync } from "node:fs";
import { basename, isAbsolute, relative, sep } from "node:path";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";


const REQUEST_FIELDS = new Set([
  "version",
  "id",
  "method",
  "argv",
  "mode",
  "workspace_root",
  "protected_endpoints",
]);


export function normalizeRequest(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("request must be a JSON object");
  }
  for (const key of Object.keys(value)) {
    if (!REQUEST_FIELDS.has(key)) {
      throw new Error(`request contains unknown field: ${key}`);
    }
  }
  if (value.version !== 1) throw new Error("unsupported protocol version");
  if (typeof value.id !== "string" || value.id.length === 0) {
    throw new Error("request id must be non-empty text");
  }
  if (value.method !== "confine") throw new Error("unsupported worker method");
  if (!Array.isArray(value.argv) || value.argv.length === 0
      || value.argv.some((item) => typeof item !== "string" || item.length === 0)) {
    throw new Error("argv must contain non-empty strings");
  }
  if (value.mode !== "read-only" && value.mode !== "workspace-write") {
    throw new Error("mode must be read-only or workspace-write");
  }
  if (typeof value.workspace_root !== "string" || value.workspace_root.length === 0) {
    throw new Error("workspace_root must be non-empty text");
  }
  const workspaceRoot = realpathSync.native(value.workspace_root);
  if (!statSync(workspaceRoot).isDirectory()) {
    throw new Error("workspace_root must be an existing directory");
  }
  if (!Array.isArray(value.protected_endpoints)
      || value.protected_endpoints.some(
        (item) => typeof item !== "string" || item.length === 0,
      )) {
    throw new Error("protected_endpoints must contain non-empty paths");
  }
  return {
    id: value.id,
    argv: [...value.argv],
    mode: value.mode,
    workspaceRoot,
    protectedEndpoints: [...new Set(value.protected_endpoints)],
  };
}


export function hardenConfinement(confined, protectedEndpoints, options = {}) {
  if (confined.enforcement !== "full") {
    throw new Error("BioinfoFlow requires full enforcement from the sandbox provider");
  }
  const inspectEndpoint = options.inspectEndpoint ?? protectedPathKind;
  const endpoints = protectedEndpoints
    .map((endpoint) => [endpoint, inspectEndpoint(endpoint)])
    .filter(([, kind]) => kind !== null);
  const argv = [...confined.argv];
  const program = basename(argv[0] ?? "");
  if (program === "bwrap") {
    const separator = argv.indexOf("--");
    if (separator < 0) throw new Error("upstream bubblewrap argv has no separator");
    const masks = collapseProtectedEndpoints(endpoints)
      .flatMap(([endpoint, kind]) => kind === "directory"
        ? ["--tmpfs", endpoint]
        : ["--ro-bind", "/dev/null", endpoint]);
    argv.splice(separator, 0, ...masks);
    return { ...confined, argv, adapter: "bubblewrap" };
  }
  if (program === "sandbox-exec") {
    const profileIndex = argv.indexOf("-p");
    if (profileIndex < 0 || typeof argv[profileIndex + 1] !== "string") {
      throw new Error("upstream Seatbelt argv has no inline profile");
    }
    const denies = endpoints.flatMap(([endpoint, kind]) => {
      const selector = kind === "directory" ? "subpath" : "literal";
      const rules = [
        `(deny file-read* (${selector} ${sbplString(endpoint)}))`,
        `(deny file-write* (${selector} ${sbplString(endpoint)}))`,
      ];
      if (kind === "socket") {
        rules.push(`(deny network-outbound (literal ${sbplString(endpoint)}))`);
      }
      return rules;
    });
    argv[profileIndex + 1] = `${argv[profileIndex + 1]} ${denies.join(" ")}`.trim();
    return { ...confined, argv, adapter: "seatbelt" };
  }
  if (endpoints.length > 0) {
    throw new Error(
      `selected sandbox runner cannot protect privileged endpoint: ${endpoints[0][0]}`,
    );
  }
  return { ...confined, argv, adapter: program || "unknown" };
}


function collapseProtectedEndpoints(endpoints) {
  const ordered = [...endpoints].sort(([left], [right]) => left.length - right.length);
  const result = [];
  for (const endpoint of ordered) {
    if (result.some(
      ([root, kind]) => kind === "directory" && pathIsWithin(endpoint[0], root),
    )) {
      continue;
    }
    result.push(endpoint);
  }
  return result;
}


function pathIsWithin(path, root) {
  const remainder = relative(root, path);
  return remainder === ""
    || (!isAbsolute(remainder) && remainder !== ".." && !remainder.startsWith(`..${sep}`));
}


export function serializeConfinement(value) {
  return {
    argv: [...value.argv],
    adapter: value.adapter,
    enforcement: value.enforcement,
    denial_signatures: [...value.denialSignatures],
    runner_failure_rules: value.runnerFailureRules.map((rule) => {
      const result = { fatal_signatures: [...rule.fatalSignatures] };
      if (rule.allowedExitCodes !== undefined) {
        result.allowed_exit_codes = [...rule.allowedExitCodes];
      }
      if (rule.informationalLines !== undefined) {
        result.informational_lines = [...rule.informationalLines];
      }
      return result;
    }),
  };
}


function protectedPathKind(path) {
  if (!existsSync(path)) return null;
  try {
    const metadata = statSync(realpathSync.native(path));
    if (metadata.isDirectory()) return "directory";
    if (metadata.isSocket()) return "socket";
    return "file";
  } catch {
    return null;
  }
}


function sbplString(value) {
  return `"${value.replaceAll("\\", String.raw`\\`).replaceAll("\"", String.raw`\"`)}"`;
}


async function main() {
  const root = new Context();
  await root.plugin(LocalSandboxProvider);
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of input) {
    let id = null;
    try {
      const parsed = JSON.parse(line);
      id = typeof parsed?.id === "string" ? parsed.id : null;
      const request = normalizeRequest(parsed);
      const confined = root.sandbox.confine(request.argv, {
        mode: request.mode,
        workspaceRoot: request.workspaceRoot,
      });
      const hardened = hardenConfinement(confined, request.protectedEndpoints);
      writeResponse({
        version: 1,
        id: request.id,
        ok: true,
        result: serializeConfinement(hardened),
      });
    } catch (error) {
      writeResponse({
        version: 1,
        id,
        ok: false,
        error: {
          code: error?.code === "SANDBOX_UNAVAILABLE"
            ? "SANDBOX_UNAVAILABLE"
            : "INVALID_REQUEST",
          message: String(error?.message ?? error),
        },
      });
    }
  }
  await root.fiber.dispose();
}


function writeResponse(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}


if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main().catch((error) => {
    process.stderr.write(`bioinfoflow-sandbox-worker: ${String(error?.stack ?? error)}\n`);
    process.exitCode = 1;
  });
}
