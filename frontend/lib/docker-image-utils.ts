import type { DockerImage } from "@/lib/types"

export function getDockerImageReference(image: DockerImage) {
  if (image.full_name) {
    return image.full_name
  }

  const name = image.name
  const registry = image.registry?.trim()
  const qualifiedName =
    registry && registry !== "docker.io" && !name.startsWith(`${registry}/`)
      ? `${registry}/${name}`
      : name

  return `${qualifiedName}:${image.tag}`
}

export function getDockerPullCommand(image: DockerImage) {
  return `docker pull ${getDockerImageReference(image)}`
}
