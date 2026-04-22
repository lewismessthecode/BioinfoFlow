/**
 * Frontend logger.
 *
 * Writes to the browser console only when NODE_ENV !== "production".
 * Production builds drop log output entirely so component errors and
 * client-side fetch failures don't leak diagnostic text into user
 * devtools or third-party log collectors.
 *
 * Kept deliberately tiny — swap for pino/winston if structured
 * telemetry is ever required. Do NOT re-add `console.log` calls
 * directly in components.
 */

type LogContext = Record<string, unknown>

const isProduction =
  typeof process !== "undefined" && process.env.NODE_ENV === "production"

function emit(level: "log" | "warn" | "error", message: string, context?: LogContext) {
  if (isProduction) return
  if (context !== undefined) {
    console[level](message, context)
  } else {
    console[level](message)
  }
}

export const logger = {
  info: (message: string, context?: LogContext) => emit("log", message, context),
  warn: (message: string, context?: LogContext) => emit("warn", message, context),
  error: (message: string, context?: LogContext) => emit("error", message, context),
}
