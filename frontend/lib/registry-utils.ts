import type { ContainerRegistryConfig } from "@/lib/types"

export const AUTOMATIC_REGISTRY_VALUE = ""

export function getContainerRegistryValue(registry: ContainerRegistryConfig) {
  const rawValue = registry.endpoint ?? registry.registry ?? registry.host ?? registry.url ?? ""
  const value = rawValue.trim()
  if (!value) return ""

  if (/^[a-z][a-z\d+.-]*:\/\//i.test(value)) {
    try {
      const parsed = new URL(value)
      return parsed.host
    } catch {
      return ""
    }
  }

  return value.replace(/\/.*$/, "").trim()
}

export function getContainerRegistryLabel(registry: ContainerRegistryConfig) {
  const value = getContainerRegistryValue(registry)
  const name = registry.name?.trim() ?? ""
  if (name && value && name !== value) return `${name} (${value})`
  return name || value
}

export function getContainerRegistrySelectValue(registry: ContainerRegistryConfig) {
  return registry.id?.trim() || getContainerRegistryValue(registry)
}

export function normalizeContainerRegistries(value: unknown): ContainerRegistryConfig[] {
  if (!Array.isArray(value)) return []

  return value
    .filter((item): item is ContainerRegistryConfig => {
      return typeof item === "object" && item !== null
    })
    .filter((registry) => getContainerRegistrySelectValue(registry).length > 0)
}
