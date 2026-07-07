const SETTINGS_RETURN_PATH_STORAGE_KEY = "bif:settings-return-path"
const DEFAULT_SETTINGS_RETURN_PATH = "/agent"

export function readSettingsReturnPath(): string {
  if (typeof window === "undefined") return DEFAULT_SETTINGS_RETURN_PATH
  try {
    const value = window.sessionStorage.getItem(SETTINGS_RETURN_PATH_STORAGE_KEY)
    if (value && value.startsWith("/") && !value.startsWith("/settings")) {
      return value
    }
  } catch {
    return DEFAULT_SETTINGS_RETURN_PATH
  }
  return DEFAULT_SETTINGS_RETURN_PATH
}

export function writeSettingsReturnPath(path: string): void {
  if (typeof window === "undefined") return
  if (!path.startsWith("/") || path.startsWith("/settings")) return
  try {
    window.sessionStorage.setItem(SETTINGS_RETURN_PATH_STORAGE_KEY, path)
  } catch {
    return
  }
}
