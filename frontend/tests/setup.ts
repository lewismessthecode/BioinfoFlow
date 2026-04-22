import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

type StorageMap = Map<string, string>

function createMemoryStorage(seed?: StorageMap): Storage {
  const store = seed ?? new Map<string, string>()

  return {
    get length() {
      return store.size
    },
    clear() {
      store.clear()
    },
    getItem(key: string) {
      return store.has(key) ? store.get(key)! : null
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null
    },
    removeItem(key: string) {
      store.delete(key)
    },
    setItem(key: string, value: string) {
      store.set(String(key), String(value))
    },
  }
}

function ensureStorage(name: "localStorage" | "sessionStorage") {
  const existing = globalThis[name]
  const hasWorkingApi =
    typeof existing?.getItem === "function" &&
    typeof existing?.setItem === "function" &&
    typeof existing?.removeItem === "function" &&
    typeof existing?.clear === "function"

  if (hasWorkingApi) {
    return
  }

  const storage = createMemoryStorage()
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: storage,
  })
  Object.defineProperty(window, name, {
    configurable: true,
    value: storage,
  })
}

ensureStorage("localStorage")
ensureStorage("sessionStorage")

afterEach(() => {
  cleanup()
})
