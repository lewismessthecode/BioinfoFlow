function normalizeError(error) {
  if (error instanceof Error) {
    return error
  }

  return new Error(String(error))
}

function resolveDatabaseConstructor(moduleValue) {
  if (typeof moduleValue === "function") {
    return moduleValue
  }

  if (typeof moduleValue?.default === "function") {
    return moduleValue.default
  }

  throw new TypeError("better-sqlite3 did not export a database constructor")
}

function isRecoverableNativeBindingError(error) {
  const message = String(error?.message ?? "")
  return (
    message.includes("compiled against a different Node.js version") ||
    message.includes("NODE_MODULE_VERSION") ||
    (message.includes("Could not locate the bindings file") &&
      Array.isArray(error?.tries) &&
      error.tries.some((candidate) => String(candidate).endsWith("better_sqlite3.node")))
  )
}

function verifyBetterSqliteNodeAbi(loadModule) {
  try {
    const Database = resolveDatabaseConstructor(loadModule())
    const database = new Database(":memory:")
    database.close?.()
    return null
  } catch (error) {
    return normalizeError(error)
  }
}

export async function ensureBetterSqliteNodeAbi({
  loadModule,
  rebuild,
  log = console,
}) {
  const initialError = verifyBetterSqliteNodeAbi(loadModule)

  if (!initialError) {
    return { action: "ok" }
  }

  if (!isRecoverableNativeBindingError(initialError)) {
    throw initialError
  }

  log.warn("[better-sqlite3] Native binding issue detected. Rebuilding for current Node.js...")

  const rebuildResult = await rebuild()
  if ((rebuildResult?.status ?? 1) !== 0) {
    return { action: "rebuild-failed", status: rebuildResult?.status ?? 1 }
  }

  const verifyError = verifyBetterSqliteNodeAbi(loadModule)
  if (verifyError) {
    throw verifyError
  }

  log.log("[better-sqlite3] Rebuild successful.")
  return { action: "rebuilt" }
}
