import type { AppIcon } from "@/lib/icons"
import {
  Bot,
  Container,
  Palette,
  Server,
  User as UserIcon,
  Users,
} from "@/lib/icons"

export type SettingsSectionKey =
  | "account"
  | "appearance"
  | "agent"
  | "providers"
  | "registries"
  | "members"

export type SettingsGroupKey = "personal" | "integrations" | "team"

export type SettingsNavItem = {
  key: SettingsSectionKey
  group: SettingsGroupKey
  icon: AppIcon
  requiresRegistryAdmin?: boolean
  requiresMembers?: boolean
}

export const SETTINGS_NAV_ITEMS: readonly SettingsNavItem[] = [
  { key: "account", group: "personal", icon: UserIcon },
  { key: "appearance", group: "personal", icon: Palette },
  { key: "agent", group: "personal", icon: Bot },
  { key: "providers", group: "integrations", icon: Server },
  {
    key: "registries",
    group: "integrations",
    icon: Container,
    requiresRegistryAdmin: true,
  },
  {
    key: "members",
    group: "team",
    icon: Users,
    requiresMembers: true,
  },
] as const

const SETTINGS_GROUP_ORDER: readonly SettingsGroupKey[] = [
  "personal",
  "integrations",
  "team",
] as const

export function filterSettingsNavItems(
  items: readonly SettingsNavItem[],
  {
    canManageMembers,
    canManageRegistries,
  }: { canManageMembers: boolean; canManageRegistries: boolean },
): SettingsNavItem[] {
  return items.filter(
    (item) =>
      (!item.requiresMembers || canManageMembers) &&
      (!item.requiresRegistryAdmin || canManageRegistries),
  )
}

export function groupSettingsNavItems(
  items: readonly SettingsNavItem[],
): { group: SettingsGroupKey; items: SettingsNavItem[] }[] {
  const buckets = new Map<SettingsGroupKey, SettingsNavItem[]>()
  for (const item of items) {
    const bucket = buckets.get(item.group) ?? []
    bucket.push(item)
    buckets.set(item.group, bucket)
  }
  return SETTINGS_GROUP_ORDER.filter((group) => buckets.has(group)).map(
    (group) => ({ group, items: buckets.get(group) ?? [] }),
  )
}

export function isSettingsSectionKey(
  value: string | null | undefined,
): value is SettingsSectionKey {
  return (
    value === "account" ||
    value === "appearance" ||
    value === "agent" ||
    value === "providers" ||
    value === "registries" ||
    value === "members"
  )
}
