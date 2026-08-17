import assert from "node:assert/strict";
import { mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { executeRequest, normalizeExecutionRequest } from "./executor.mjs";


test("danger-full-access execution is still bounded and structured", async () => {
  const root = mkdtempSync(join(tmpdir(), "bif-executor-"));
  try {
    const request = normalizeExecutionRequest({
      version: 1,
      argv: ["/bin/bash", "-c", "printf ready"],
      cwd: root,
      environment: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
      mode: "danger-full-access",
      workspace_root: root,
      protected_endpoints: [],
      timeout_ms: 5000,
      capture_limit: 4096,
      cwd_inode: statSync(root, { bigint: true }).ino.toString(),
      workspace_inode: statSync(root, { bigint: true }).ino.toString(),
    });

    const result = await executeRequest(request, null);

    assert.equal(result.exit_code, 0);
    assert.equal(result.stdout, "ready");
    assert.equal(result.sandbox.mode, "danger-full-access");
    assert.equal(result.sandbox.enforcement, null);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});


test("execution request rejects a changed mounted directory identity", () => {
  const root = mkdtempSync(join(tmpdir(), "bif-executor-"));
  try {
    assert.throws(() => normalizeExecutionRequest({
      version: 1,
      argv: ["true"],
      cwd: root,
      environment: {},
      mode: "read-only",
      workspace_root: root,
      protected_endpoints: [],
      timeout_ms: 1000,
      capture_limit: 1000,
      cwd_inode: "1",
      workspace_inode: "1",
    }), /identity changed/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});


test("execution kills commands that exceed the shared output bound", async () => {
  const root = mkdtempSync(join(tmpdir(), "bif-executor-"));
  try {
    const request = normalizeExecutionRequest({
      version: 1,
      argv: [process.execPath, "-e", "process.stdout.write('x'.repeat(10000))"],
      cwd: root,
      environment: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
      mode: "danger-full-access",
      workspace_root: root,
      protected_endpoints: [],
      timeout_ms: 5000,
      capture_limit: 128,
      cwd_inode: statSync(root, { bigint: true }).ino.toString(),
      workspace_inode: statSync(root, { bigint: true }).ino.toString(),
    });

    const result = await executeRequest(request, null);

    assert.equal(result.output_limit_exceeded, true);
    assert.equal(Buffer.byteLength(result.stdout) + Buffer.byteLength(result.stderr), 128);
    assert.notEqual(result.exit_code, 0);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});


test("execution kills commands that exceed their timeout", async () => {
  const root = mkdtempSync(join(tmpdir(), "bif-executor-"));
  try {
    const request = normalizeExecutionRequest({
      version: 1,
      argv: [process.execPath, "-e", "setTimeout(() => {}, 60000)"],
      cwd: root,
      environment: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
      mode: "danger-full-access",
      workspace_root: root,
      protected_endpoints: [],
      timeout_ms: 20,
      capture_limit: 4096,
      cwd_inode: statSync(root, { bigint: true }).ino.toString(),
      workspace_inode: statSync(root, { bigint: true }).ino.toString(),
    });

    const result = await executeRequest(request, null);

    assert.equal(result.timed_out, true);
    assert.notEqual(result.exit_code, 0);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
