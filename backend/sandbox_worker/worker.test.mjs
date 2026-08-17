import assert from "node:assert/strict";
import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  hardenConfinement,
  normalizeRequest,
  serializeConfinement,
} from "./worker.mjs";


test("normalizes one exact versioned confine request", () => {
  const workspace = mkdtempSync(join(tmpdir(), "bif-worker-"));
  try {
    const request = normalizeRequest({
      version: 1,
      id: "request-1",
      method: "confine",
      argv: ["/bin/bash", "-c", "pwd"],
      mode: "workspace-write",
      workspace_root: workspace,
      protected_endpoints: [],
    });

    assert.equal(request.workspaceRoot, realpathSync.native(workspace));
    assert.equal(request.mode, "workspace-write");
    assert.deepEqual(request.argv, ["/bin/bash", "-c", "pwd"]);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});


test("rejects unknown request fields", () => {
  assert.throws(
    () => normalizeRequest({
      version: 1,
      id: "request-1",
      method: "confine",
      argv: ["true"],
      mode: "read-only",
      workspace_root: "/",
      protected_endpoints: [],
      surprise: true,
    }),
    /unknown field/,
  );
});


test("masks protected endpoints in the upstream bubblewrap argv", () => {
  const result = hardenConfinement({
    argv: ["bwrap", "--ro-bind", "/", "/", "--", "true"],
    enforcement: "full",
    denialSignatures: ["read-only file system"],
    runnerFailureRules: [{ fatalSignatures: ["bwrap: "] }],
  }, ["/var/run/docker.sock"], { inspectEndpoint: () => "socket" });

  assert.deepEqual(result.argv, [
    "bwrap",
    "--ro-bind",
    "/",
    "/",
    "--ro-bind",
    "/dev/null",
    "/var/run/docker.sock",
    "--",
    "true",
  ]);
  assert.equal(result.adapter, "bubblewrap");
});


test("adds exact Seatbelt network denies for protected Unix sockets", () => {
  const result = hardenConfinement({
    argv: ["sandbox-exec", "-p", "(version 1) (allow default)", "--", "true"],
    enforcement: "full",
    denialSignatures: ["operation not permitted"],
    runnerFailureRules: [{ fatalSignatures: ["sandbox-exec: "] }],
  }, ["/Users/demo/.docker/run/docker.sock"], { inspectEndpoint: () => "socket" });

  assert.match(
    result.argv[2],
    /\(deny network-outbound \(literal "\/Users\/demo\/\.docker\/run\/docker\.sock"\)\)/,
  );
  assert.match(result.argv[2], /deny file-read\*/);
  assert.equal(result.adapter, "seatbelt");
});


test("retains a nested Seatbelt socket when its parent directory is protected", () => {
  const socket = "/Users/demo/.docker/run/docker.sock";
  const result = hardenConfinement({
    argv: ["sandbox-exec", "-p", "(version 1) (allow default)", "--", "true"],
    enforcement: "full",
    denialSignatures: ["operation not permitted"],
    runnerFailureRules: [{ fatalSignatures: ["sandbox-exec: "] }],
  }, ["/Users/demo/.docker", socket], {
    inspectEndpoint: (path) => path === socket ? "socket" : "directory",
  });

  assert.match(result.argv[2], /deny file-read\* \(subpath "\/Users\/demo\/\.docker"\)/);
  assert.match(
    result.argv[2],
    /deny network-outbound \(literal "\/Users\/demo\/\.docker\/run\/docker\.sock"\)/,
  );
});


test("hides protected control-plane directories from bubblewrap", () => {
  const result = hardenConfinement({
    argv: ["bwrap", "--ro-bind", "/", "/", "--", "true"],
    enforcement: "full",
    denialSignatures: ["read-only file system"],
    runnerFailureRules: [{ fatalSignatures: ["bwrap: "] }],
  }, ["/srv/bioinfoflow/state"], { inspectEndpoint: () => "directory" });

  assert.deepEqual(result.argv.slice(4, 6), ["--tmpfs", "/srv/bioinfoflow/state"]);
});


test("collapses protected descendants before building bubblewrap masks", () => {
  const result = hardenConfinement({
    argv: ["bwrap", "--ro-bind", "/", "/", "--", "true"],
    enforcement: "full",
    denialSignatures: ["read-only file system"],
    runnerFailureRules: [{ fatalSignatures: ["bwrap: "] }],
  }, ["/proc/self/fd", "/proc"], { inspectEndpoint: () => "directory" });

  assert.deepEqual(result.argv, [
    "bwrap", "--ro-bind", "/", "/", "--tmpfs", "/proc", "--", "true",
  ]);
});


test("fails closed when the selected provider cannot hide a privileged endpoint", () => {
  assert.throws(
    () => hardenConfinement({
      argv: ["landlock-run", "--", "true"],
      enforcement: "full",
      denialSignatures: ["permission denied"],
      runnerFailureRules: [{ fatalSignatures: ["landlock-run: "] }],
    }, ["/run/docker.sock"], { inspectEndpoint: () => "socket" }),
    /cannot protect privileged endpoint/,
  );
});


test("rejects partial upstream enforcement", () => {
  assert.throws(
    () => hardenConfinement({
      argv: ["landlock-run", "--", "true"],
      enforcement: "partial",
      denialSignatures: ["permission denied"],
      runnerFailureRules: [{ fatalSignatures: ["landlock-run: "] }],
    }, [], { inspectEndpoint: () => null }),
    /full enforcement/,
  );
});


test("serializes upstream camelCase evidence into protocol snake_case", () => {
  const result = serializeConfinement({
    argv: ["bwrap", "--", "true"],
    adapter: "bubblewrap",
    enforcement: "full",
    denialSignatures: ["read-only file system"],
    runnerFailureRules: [{
      allowedExitCodes: [125],
      fatalSignatures: ["runner: "],
      informationalLines: ["runner: notice"],
    }],
  });

  assert.deepEqual(result.runner_failure_rules, [{
    allowed_exit_codes: [125],
    fatal_signatures: ["runner: "],
    informational_lines: ["runner: notice"],
  }]);
});
