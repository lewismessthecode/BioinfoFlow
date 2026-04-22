import fs from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

/**
 * Lightweight coverage guard for our i18n migration.
 *
 * This intentionally does NOT try to be a perfect "no hard-coded strings"
 * checker (that would require proper AST parsing + many false-positive rules).
 *
 * Instead, it blocks regressions by ensuring we removed a curated set of known
 * hard-coded English UI strings from key subpages/components.
 */

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..")

/** @type {Array<{file: string; forbidden: Array<string | RegExp>}>} */
const CHECKS = [
  {
    file: "frontend/app/layout.tsx",
    forbidden: [
      "Skip to content",
    ],
  },
  {
    file: "frontend/app/(app)/dashboard/page.tsx",
    forbidden: [
      "Recent Activity",
      "Run ID",
      "Current Task",
      "Docker: ",
      /\bAvailable\b/,
      /\bNot running\b/,
      "NVIDIA Runtime: ",
      /\bNot found\b/,
      "Parabricks Compatible",
      "No GPU detected",
      /Failed to load dashboard data/,
    ],
  },
  {
    file: "frontend/app/(app)/runs/page.tsx",
    forbidden: [
      "\"Filter\"",
      /\bSamples\b/,
      /\bView Details\b/,
      /\bView Logs\b/,
      /Failed to load runs/,
      /Failed to retry run/,
      /Attempting to resume from last checkpoint/,
      /This action cannot be undone/,
      /Showing \d+/,
    ],
  },
  {
    file: "frontend/app/(app)/workflows/page.tsx",
    forbidden: [
      /No workflows enabled for this project yet/,
      /Select a project to start a run/,
      /\bSelect project\b/,
      /\bAdd\b/,
      /\bRemove\b/,
      /Failed to delete workflow/,
      /Failed to switch workflow version/,
    ],
  },
  {
    file: "frontend/app/(app)/workflows/components/workflow-register-dialog.tsx",
    forbidden: [
      /Register New Workflow/,
      /Source Type/,
      /Repository URL/,
      /Workflow File/,
      /\bRegister Workflow\b/,
      /\bRegistering\.\.\./,
    ],
  },
  {
    file: "frontend/app/(app)/workflows/[id]/page.tsx",
    forbidden: [
      /Workflow not found/,
      /Back to Workflows/,
      /\bEngine\b/,
      /\bSource URL\b/,
      /\bOverview\b/,
      /\bParameters\b/,
      /Workflow ID copied to clipboard/,
    ],
  },
  {
    file: "frontend/app/(app)/workflows/[id]/components/workflow-overview-tab.tsx",
    forbidden: [
      /\bDescription\b/,
      /No schema information available/,
      /\bCreated:\b/,
      /\bUpdated:\b/,
    ],
  },
  {
    file: "frontend/app/(app)/images/page.tsx",
    forbidden: [
      /Upload Image/,
      /Docker is not running/,
      /Copy Image Name/,
      /Delete Local Copy/,
      /\bRe-pull\b/,
      /\bPulling\.\.\./,
      /\bUsed by this project\b/,
    ],
  },
  {
    file: "frontend/app/(app)/images/components/image-upload-dialog.tsx",
    forbidden: [
      /Upload Docker Image/,
      /Import Method/,
      /From Registry/,
      /Tarball \(\.tar\)/,
      /Pull Image/,
    ],
  },
  {
    file: "frontend/app/(app)/images/components/images-skeleton.tsx",
    forbidden: [
      /\bImage\b/,
      /\bVersion\b/,
      /\bSize\b/,
      /\bStatus\b/,
      /\bActions\b/,
    ],
  },
  {
    file: "frontend/app/(app)/workflows/components/workflows-skeleton.tsx",
    forbidden: [
      /\bName\b/,
      /\bSource\b/,
      /\bEngine\b/,
      /\bVersion\b/,
      /Last Modified/,
      /\bActions\b/,
    ],
  },
  {
    file: "frontend/components/bioinfoflow/command-palette.tsx",
    forbidden: [
      /Search projects, runs, workflows, or actions/,
      /No results found/,
      /\bActions\b/,
      /New Conversation/,
      /Demo Runs/,
    ],
  },
  {
    file: "frontend/components/bioinfoflow/sidebar/sidebar.tsx",
    forbidden: [
      /Project name is required/,
      /Workspace path is required/,
      /Conversation renamed/,
      /Delete this conversation\?/,
      /Quick actions feature coming soon/,
      /Select a project first/,
      /Conversation actions/,
      /Quick actions/,
      /\bClose\b/,
    ],
  },
  {
    file: "frontend/components/bioinfoflow/create-project-dialog.tsx",
    forbidden: [
      /Workspace Path/,
      /Short description/,
      /e\.g\., COVID Analysis/,
      /New project/,
    ],
  },
  {
    file: "frontend/components/bioinfoflow/monitor-panel.tsx",
    forbidden: [
      /Run Monitor/,
      /\bLive\b/,
      /Current Task/,
      /Task Status/,
      /Tasks Done/,
      /Remaining/,
    ],
  },
  {
    file: "frontend/components/bioinfoflow/dag/dag-panel.tsx",
    forbidden: [
      /\bExperience\b/,
      /Loading runs\.\.\./,
      /No runs yet/,
      /No DAG data available/,
      /Mission Map/,
      /Select run/,
    ],
  },
  {
    file: "frontend/components/bioinfoflow/chat/message-list.tsx",
    forbidden: [
      /\bYou\b/,
    ],
  },
]

function formatMatchLine(line) {
  // Keep output stable + readable
  return line.length > 180 ? `${line.slice(0, 180)}…` : line
}

/**
 * @param {string} content
 * @param {string | RegExp} needle
 */
function findMatches(content, needle) {
  const matches = []
  const lines = content.split("\n")

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (typeof needle === "string") {
      let from = 0
      while (true) {
        const idx = line.indexOf(needle, from)
        if (idx === -1) break
        matches.push({ lineNo: i + 1, colNo: idx + 1, line })
        from = idx + Math.max(1, needle.length)
      }
      continue
    }

    const regex = new RegExp(needle.source, needle.flags.includes("g") ? needle.flags : `${needle.flags}g`)
    let m
    while ((m = regex.exec(line)) !== null) {
      matches.push({ lineNo: i + 1, colNo: (m.index ?? 0) + 1, line })
      if (m.index === regex.lastIndex) regex.lastIndex++
    }
  }

  return matches
}

async function main() {
  // Guard: keep `en.json` and `zh-CN.json` keysets in sync.
  const messagesEn = JSON.parse(await fs.readFile(path.join(ROOT, "frontend/messages/en.json"), "utf8"))
  const messagesZh = JSON.parse(await fs.readFile(path.join(ROOT, "frontend/messages/zh-CN.json"), "utf8"))

  const flattenKeys = (obj, prefix = "") => {
    const keys = []
    for (const [k, v] of Object.entries(obj)) {
      const next = prefix ? `${prefix}.${k}` : k
      if (v && typeof v === "object" && !Array.isArray(v)) {
        keys.push(...flattenKeys(v, next))
      } else {
        keys.push(next)
      }
    }
    return keys
  }

  const enKeys = new Set(flattenKeys(messagesEn))
  const zhKeys = new Set(flattenKeys(messagesZh))
  const missingInZh = [...enKeys].filter((k) => !zhKeys.has(k)).sort()
  const missingInEn = [...zhKeys].filter((k) => !enKeys.has(k)).sort()

  if (missingInZh.length || missingInEn.length) {
    console.error("FAIL: Message keysets out of sync.\n")
    if (missingInZh.length) {
      console.error(`Missing in zh-CN.json (${missingInZh.length}):`)
      for (const k of missingInZh.slice(0, 80)) console.error(`  - ${k}`)
      if (missingInZh.length > 80) console.error(`  ... +${missingInZh.length - 80} more`)
      console.error("")
    }
    if (missingInEn.length) {
      console.error(`Missing in en.json (${missingInEn.length}):`)
      for (const k of missingInEn.slice(0, 80)) console.error(`  - ${k}`)
      if (missingInEn.length > 80) console.error(`  ... +${missingInEn.length - 80} more`)
      console.error("")
    }
    process.exit(1)
  }

  /** @type {Array<{file: string; needle: string; lineNo: number; colNo: number; line: string}>} */
  const problems = []

  for (const check of CHECKS) {
    const abs = path.join(ROOT, check.file)
    const content = await fs.readFile(abs, "utf8")

    for (const forbidden of check.forbidden) {
      const hits = findMatches(content, forbidden)
      for (const hit of hits) {
        problems.push({
          file: check.file,
          needle: typeof forbidden === "string" ? forbidden : forbidden.toString(),
          lineNo: hit.lineNo,
          colNo: hit.colNo,
          line: hit.line,
        })
      }
    }
  }

  if (problems.length) {
    console.error(`FAIL: Found ${problems.length} forbidden hard-coded string matches:\n`)
    for (const p of problems) {
      console.error(`${p.file}:${p.lineNo}:${p.colNo}`)
      console.error(`  needle: ${p.needle}`)
      console.error(`  ${formatMatchLine(p.line)}`)
      console.error("")
    }
    process.exit(1)
  }

  console.log("PASS: i18n coverage check clean")
}

await main()
