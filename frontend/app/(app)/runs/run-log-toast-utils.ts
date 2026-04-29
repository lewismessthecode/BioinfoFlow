const CONTAINER_IMAGE_PREP_PREFIX = "Preparing required container images:"

export function parseContainerImagePreparationMessage(message: string): string | null {
  const trimmed = message.trim()
  if (!trimmed.startsWith(CONTAINER_IMAGE_PREP_PREFIX)) return null
  const images = trimmed.slice(CONTAINER_IMAGE_PREP_PREFIX.length).trim()
  return images || null
}
