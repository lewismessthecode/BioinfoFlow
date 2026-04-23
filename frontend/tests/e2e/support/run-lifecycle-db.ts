import fs from "node:fs"
import path from "node:path"
import { DatabaseSync } from "node:sqlite"

const frontendRoot = process.cwd()
const e2eRoot = path.resolve(frontendRoot, ".playwright-e2e", "run-lifecycle")
const bioinfoflowHome = path.join(e2eRoot, "bioinfoflow-home")
const databasePath = path.join(e2eRoot, "bioinfoflow.db")
const defaultWorkspaceId = "00000000-0000-0000-0000-000000000001"

export const runLifecycleFixture = {
  projectId: "11111111-1111-1111-1111-111111111111",
  workflowId: "22222222-2222-2222-2222-222222222222",
  bindingId: "33333333-3333-3333-3333-333333333333",
  failedRunId: "run_e2e_failed_source",
  failedRunRowId: "44444444-4444-4444-4444-444444444444",
  workflowName: "e2e/run-lifecycle",
  resumeToken: "e2e-resume-token",
} as const

function withDb<T>(callback: (db: DatabaseSync) => T): T {
  const db = new DatabaseSync(databasePath)
  db.exec("PRAGMA busy_timeout = 5000")
  db.exec("PRAGMA foreign_keys = ON")
  try {
    return callback(db)
  } finally {
    db.close()
  }
}

function clearFixtureTables(db: DatabaseSync) {
  const existingTables = new Set(
    (
      db
        .prepare("SELECT name FROM sqlite_master WHERE type = 'table'")
        .all() as { name: string }[]
    ).map((row) => row.name),
  )

  const cleanupOrder = [
    "scheduled_tasks",
    "project_workflow_pins",
    "batch_runs",
    "batches",
    "notification_configs",
    "audit_logs",
    "runs",
    "project_workflow_bindings",
    "workflows",
  ]

  for (const table of cleanupOrder) {
    if (!existingTables.has(table)) continue
    db.prepare(`DELETE FROM ${table}`).run()
  }

  if (existingTables.has("projects")) {
    db.prepare("DELETE FROM projects WHERE user_id = ?").run("dev")
  }

  if (existingTables.has("workspace_memberships")) {
    db.prepare("DELETE FROM workspace_memberships WHERE user_id = ?").run("dev")
  }
}

export function seedRunLifecycleFixture() {
  const workflowBundleDir = path.join(
    bioinfoflowHome,
    "state",
    "workflows",
    "local",
    runLifecycleFixture.workflowId,
    "bundle",
  )
  fs.mkdirSync(workflowBundleDir, { recursive: true })
  fs.writeFileSync(
    path.join(workflowBundleDir, "main.nf"),
    [
      "nextflow.enable.dsl=2",
      "",
      "process SAY_HELLO {",
      "  output:",
      "  stdout",
      "",
      "  script:",
      "  '''",
      "  echo hello",
      "  '''",
      "}",
      "",
      "workflow {",
      "  SAY_HELLO()",
      "}",
      "",
    ].join("\n"),
    "utf8",
  )

  withDb((db) => {
    clearFixtureTables(db)

    db.prepare(
      `
        INSERT OR IGNORE INTO workspaces (id, name, slug, is_default)
        VALUES (?, ?, ?, ?)
      `,
    ).run(defaultWorkspaceId, "Bioinfoflow Team", "bioinfoflow-team", 1)

    db.prepare(
      `
        INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
        VALUES (?, ?, ?, ?)
      `,
    ).run("55555555-5555-5555-5555-555555555555", defaultWorkspaceId, "dev", "owner")

    db.prepare(
      `
        INSERT INTO projects (
          id,
          name,
          description,
          storage_mode,
          external_root_path,
          user_id,
          created_by_user_id,
          workspace_id,
          is_default
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `,
    ).run(
      runLifecycleFixture.projectId,
      "Run Lifecycle Project",
      "Fixture project for browser lifecycle coverage",
      "managed",
      null,
      "dev",
      "dev",
      defaultWorkspaceId,
      0,
    )

    db.prepare(
      `
        INSERT INTO workflows (
          id,
          name,
          description,
          source,
          engine,
          source_ref,
          entrypoint_relpath,
          bundle_kind,
          version,
          estimated_time,
          schema_json,
          form_spec,
          weight
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `,
    ).run(
      runLifecycleFixture.workflowId,
      runLifecycleFixture.workflowName,
      "Fixture workflow for run lifecycle browser coverage",
      "local",
      "nextflow",
      "fixture://run-lifecycle",
      "main.nf",
      "directory",
      "1.0.0",
      "5m",
      null,
      null,
      1,
    )

    db.prepare(
      `
        INSERT INTO project_workflow_bindings (id, project_id, workflow_id)
        VALUES (?, ?, ?)
      `,
    ).run(
      runLifecycleFixture.bindingId,
      runLifecycleFixture.projectId,
      runLifecycleFixture.workflowId,
    )

    db.prepare(
      `
        INSERT INTO runs (
          id,
          run_id,
          project_id,
          workflow_id,
          status,
          config,
          samplesheet_path,
          started_at,
          completed_at,
          duration_seconds,
          samples_count,
          tasks_total,
          tasks_completed,
          current_task,
          error_message,
          error_json,
          last_heartbeat_at,
          nextflow_run_name
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `,
    ).run(
      runLifecycleFixture.failedRunRowId,
      runLifecycleFixture.failedRunId,
      runLifecycleFixture.projectId,
      runLifecycleFixture.workflowId,
      "failed",
      JSON.stringify({ request: { params: { sample_id: "demo-sample" } } }),
      null,
      "2026-04-23T08:00:00.000Z",
      "2026-04-23T08:05:00.000Z",
      300,
      1,
      4,
      2,
      "align_reads",
      "Fixture failure for resume coverage",
      null,
      null,
      runLifecycleFixture.resumeToken,
    )
  })
}

export function findLatestResumedRunId() {
  return withDb((db) => {
    const row = db
      .prepare(
        `
          SELECT run_id
          FROM runs
          WHERE project_id = ?
            AND run_id != ?
          ORDER BY created_at DESC, id DESC
          LIMIT 1
        `,
      )
      .get(runLifecycleFixture.projectId, runLifecycleFixture.failedRunId) as
      | { run_id: string }
      | undefined

    return row?.run_id ?? null
  })
}

export function readRunStatus(runId: string) {
  return withDb((db) => {
    const row = db
      .prepare("SELECT status FROM runs WHERE run_id = ?")
      .get(runId) as { status: string } | undefined
    return row?.status ?? null
  })
}
