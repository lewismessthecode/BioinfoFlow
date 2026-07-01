"use client"

import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import { ApiError, apiRequest, getApiErrorMessage } from "@/lib/api"
import { authClient } from "@/lib/auth-client"
import {
  canManageDestructiveBusinessActions,
  clientAuthConfig,
  resolveTeamRole,
} from "@/lib/auth-config"
import { formatSize } from "@/lib/format-utils"
import { getDockerImageReference, getDockerPullCommand } from "@/lib/docker-image-utils"
import {
  getContainerRegistrySelectValue,
  getContainerRegistryValue,
  normalizeContainerRegistries,
} from "@/lib/registry-utils"
import type { ContainerRegistryConfig, DockerImage, ImageStatusMeta } from "@/lib/types"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import type { ViewMode } from "@/components/ui/view-toggle"

const RETRY_INTERVAL_MS = 15_000
const recommendedImages = [
  "biocontainers/fastqc",
  "biocontainers/bwa",
  "ubuntu",
] as const

const getImageSizeBytes = (image: DockerImage) => image.size_bytes ?? 0

export function useImagesPage() {
  const tImages = useTranslations("images")
  const tCommon = useTranslations("common")
  const { activeProjectId } = useProjectContext()
  const { data: session } = authClient.useSession()
  const canDeleteImages = canManageDestructiveBusinessActions(
    clientAuthConfig.mode,
    session?.user ? resolveTeamRole(session.user) : "member",
    clientAuthConfig.authEnabled,
  )
  const [images, setImages] = useState<DockerImage[]>([])
  const [view, setView] = useState<ViewMode>("cards")
  const [search, setSearch] = useState("")
  const [uploadOpen, setUploadOpen] = useState(false)
  const [importMethod, setImportMethod] = useState<"registry" | "tarball">("registry")
  const [imageName, setImageName] = useState("")
  const [selectedRegistry, setSelectedRegistry] = useState("")
  const [imageRegistries, setImageRegistries] = useState<ContainerRegistryConfig[]>([])
  const [registriesLoaded, setRegistriesLoaded] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [tarballFile, setTarballFile] = useState<File | null>(null)
  const [dockerStatus, setDockerStatus] = useState<"available" | "unavailable" | null>(null)
  const [imagesStale, setImagesStale] = useState(false)
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null)
  const [detailsImage, setDetailsImage] = useState<DockerImage | null>(null)
  const [recommendedOpen, setRecommendedOpen] = useState(false)
  const [selectionMode, setSelectionMode] = useState(false)
  const [selectedImageIds, setSelectedImageIds] = useState<Set<string>>(() => new Set())
  const [isBatchDeleting, setIsBatchDeleting] = useState(false)
  const deferredSearch = useDeferredValue(search)
  const retryTimerRef = useRef<number | null>(null)

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }, [])

  const fetchImages = useCallback(async ({ forceSync = false, silent = false }: { forceSync?: boolean; silent?: boolean } = {}) => {
    if (!silent) {
      setIsLoading(true)
    }
    try {
      const { data, meta } = await apiRequest<DockerImage[]>("/images", {
        params: { limit: 100, force_sync: forceSync || undefined },
      })
      const status = (meta?.status ?? {}) as ImageStatusMeta
      setImages(data)
      setDockerStatus(status.docker === "unavailable" ? "unavailable" : "available")
      setImagesStale(Boolean(status.images_stale))
      setLastSyncedAt(status.last_synced_at ?? null)
      clearRetryTimer()
      if (status.docker === "unavailable" && data.length === 0) {
        retryTimerRef.current = window.setTimeout(() => {
          fetchImages({ forceSync: true, silent: true })
        }, RETRY_INTERVAL_MS)
      }
    } catch (error) {
      clearRetryTimer()
      const message = getApiErrorMessage(error, tImages("errors.loadFailed"))
      toast.error(message)
    } finally {
      if (!silent) {
        setIsLoading(false)
      }
    }
  }, [clearRetryTimer, tImages])

  useEffect(() => {
    fetchImages()
  }, [fetchImages])

  useEffect(() => {
    if (dockerStatus !== "available") {
      return
    }
    const handleFocus = () => {
      fetchImages({ forceSync: true, silent: true })
    }
    window.addEventListener("focus", handleFocus)
    return () => window.removeEventListener("focus", handleFocus)
  }, [dockerStatus, fetchImages])

  useEffect(() => () => clearRetryTimer(), [clearRetryTimer])

  const loadImageRegistries = useCallback(async () => {
    if (registriesLoaded) {
      return
    }
    try {
      const { data } = await apiRequest<ContainerRegistryConfig[]>("/container-registries")
      setImageRegistries(normalizeContainerRegistries(data))
    } catch {
      setImageRegistries([])
    } finally {
      setRegistriesLoaded(true)
    }
  }, [registriesLoaded])

  const parseImageInput = (value: string) => {
    const trimmed = value.trim()
    if (!trimmed) return { name: "", tag: undefined }
    const lastSlashIndex = trimmed.lastIndexOf("/")
    const lastColonIndex = trimmed.lastIndexOf(":")

    if (lastColonIndex > lastSlashIndex) {
      return {
        name: trimmed.slice(0, lastColonIndex),
        tag: trimmed.slice(lastColonIndex + 1) || undefined,
      }
    }

    return { name: trimmed, tag: undefined }
  }

  const handlePullImage = useCallback(() => {
    if (dockerStatus === "unavailable") {
      toast.error(tImages("errors.dockerNotRunning"))
      return
    }
    if (importMethod === "tarball") {
      if (!tarballFile) {
        toast.error(tImages("errors.tarballRequired"))
        return
      }
      const form = new FormData()
      form.append("file", tarballFile)
      if (activeProjectId) {
        form.append("project_id", activeProjectId)
      }
      setIsSubmitting(true)
      apiRequest<DockerImage[]>("/images/load", {
        method: "POST",
        body: form,
        headers: {},
      })
        .then(() => {
          toast.success(tImages("toasts.tarballLoaded"))
          fetchImages()
        })
      .catch((error) => {
        const message = getApiErrorMessage(error, tImages("errors.tarballLoadFailed"))
        toast.error(message)
      })
      .finally(() => {
          setIsSubmitting(false)
          setUploadOpen(false)
          setTarballFile(null)
        })
      return
    }
    if (!imageName.trim()) {
      toast.error(tImages("errors.imageNameRequired"))
      return
    }

    const { name, tag } = parseImageInput(imageName)
    if (!name) {
      toast.error(tImages("errors.imageNameInvalid"))
      return
    }

    setIsSubmitting(true)
    toast.info(tImages("toasts.pullingTitle", { name: imageName }), {
      description: tImages("toasts.pullingDescription"),
    })

    const selectedRegistryValue = selectedRegistry.trim()
    const pullPayload: Record<string, unknown> = {
      name,
      tag,
      project_id: activeProjectId || undefined,
    }
    const selectedRegistryConfig = selectedRegistryValue
      ? imageRegistries.find(
          (registry) => getContainerRegistrySelectValue(registry) === selectedRegistryValue,
        )
      : undefined
    const selectedRegistryEndpoint = selectedRegistryConfig
      ? getContainerRegistryValue(selectedRegistryConfig)
      : ""
    if (selectedRegistryConfig?.id) {
      pullPayload.registry_id = selectedRegistryConfig.id
    }
    if (selectedRegistryEndpoint) {
      pullPayload.registry = selectedRegistryEndpoint
    }

    apiRequest<DockerImage>("/images/pull", {
      method: "POST",
      body: JSON.stringify(pullPayload),
    })
      .then(() => {
        toast.success(tImages("toasts.pullStartedTitle", { name: imageName }), {
          description: tImages("toasts.pullStartedDescription"),
        })
        fetchImages()
      })
      .catch((error) => {
        const message = getApiErrorMessage(error, tImages("errors.pullFailed"))
        toast.error(message)
      })
      .finally(() => {
        setIsSubmitting(false)
        setUploadOpen(false)
        setImageName("")
        setSelectedRegistry("")
      })
  }, [activeProjectId, dockerStatus, fetchImages, imageName, imageRegistries, importMethod, selectedRegistry, tarballFile, tImages])

  const handlePull = useCallback(async (image: DockerImage) => {
    if (dockerStatus === "unavailable") {
      toast.error(tImages("errors.dockerNotRunning"))
      return
    }
    try {
      toast.info(tImages("toasts.pullingTitle", { name: `${image.name}:${image.tag}` }), {
        description: tImages("toasts.sizeDescription", { size: formatSize(image.size_bytes) }),
      })
      await apiRequest<DockerImage>("/images/pull", {
        method: "POST",
        body: JSON.stringify({ name: image.name, tag: image.tag, project_id: activeProjectId || undefined }),
      })
      toast.success(tImages("toasts.pullStartedTitle", { name: image.name }), {
        description: tImages("toasts.pullStartedDescription"),
      })
      fetchImages()
    } catch (error) {
      const message = getApiErrorMessage(error, tImages("errors.pullFailed"))
      toast.error(message)
    }
  }, [activeProjectId, dockerStatus, fetchImages, tImages])

  const handleViewDetails = useCallback((image: DockerImage) => {
    setDetailsImage(image)
  }, [])

  const handleCopyName = useCallback((image: DockerImage) => {
    const fullName = getDockerImageReference(image)
    navigator.clipboard.writeText(fullName)
    toast.success(tCommon("copiedToClipboard"), {
      description: fullName,
    })
  }, [tCommon])

  const handleCopyPullCommand = useCallback((image: DockerImage) => {
    const command = getDockerPullCommand(image)
    navigator.clipboard.writeText(command)
    toast.success(tCommon("copiedToClipboard"), {
      description: command,
    })
  }, [tCommon])

  const handleDeleteLocal = useCallback((image: DockerImage) => {
    if (!canDeleteImages) {
      toast.error(tImages("errors.deleteForbidden"))
      return
    }
    if (image.status !== "local") {
      toast.error(tImages("errors.deleteFailed"))
      return
    }
    toast.warning(tImages("toasts.deleteConfirmTitle", { name: image.name }), {
      description: tImages("toasts.deleteConfirmDescription", { size: formatSize(image.size_bytes) }),
      action: {
        label: tCommon("confirm"),
        onClick: async () => {
          try {
            await apiRequest(`/images/${image.id}`, { method: "DELETE" })
            setImages((prev) => prev.filter((item) => item.id !== image.id))
            setSelectedImageIds((prev) => {
              if (!prev.has(image.id)) {
                return prev
              }
              const next = new Set(prev)
              next.delete(image.id)
              return next
            })
            setDetailsImage((current) => current?.id === image.id ? null : current)
            toast.success(tImages("toasts.removedTitle", { name: image.name }), {
              description: tImages("toasts.removedDescription"),
            })
          } catch (error) {
            const message =
              error instanceof ApiError && error.code === "IMAGE_PULLING"
                ? tImages("errors.deletePulling")
                : error instanceof ApiError && error.code === "IMAGE_IN_USE"
                  ? error.message || tImages("errors.deleteInUse")
                  : getApiErrorMessage(error, tImages("errors.deleteFailed"))
            toast.error(message)
          }
        },
      },
    })
  }, [canDeleteImages, tCommon, tImages])

  const handleStartSelection = useCallback(() => {
    setSelectionMode(true)
  }, [])

  const handleCancelSelection = useCallback(() => {
    setSelectionMode(false)
    setSelectedImageIds(new Set())
  }, [])

  const handleToggleSelection = useCallback((image: DockerImage) => {
    if (image.status !== "local") {
      return
    }
    setSelectionMode(true)
    setSelectedImageIds((prev) => {
      const next = new Set(prev)
      if (next.has(image.id)) {
        next.delete(image.id)
      } else {
        next.add(image.id)
      }
      return next
    })
  }, [])

  const handleTarballFileChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setTarballFile(event.target.files?.[0] ?? null)
  }, [])

  const handleUploadOpenChange = useCallback((open: boolean) => {
    setUploadOpen(open)
    if (!open) {
      setImageName("")
      setSelectedRegistry("")
      setImportMethod("registry")
      setTarballFile(null)
      setRecommendedOpen(false)
    }
  }, [])

  const openRegistryDialog = useCallback((value = "") => {
    setImportMethod("registry")
    setImageName(value)
    setSelectedRegistry("")
    setRecommendedOpen(false)
    setUploadOpen(true)
    void loadImageRegistries()
  }, [loadImageRegistries])

  const openTarballDialog = useCallback(() => {
    setImportMethod("tarball")
    setImageName("")
    setSelectedRegistry("")
    setRecommendedOpen(false)
    setUploadOpen(true)
  }, [])

  const handleRefresh = useCallback(() => {
    fetchImages({ forceSync: true })
  }, [fetchImages])

  const filteredImages = useMemo(() => images.filter((img) => {
    const query = deferredSearch.toLowerCase()
    const nameMatch = img.name.toLowerCase().includes(query)
    const tagMatch = img.tag.toLowerCase().includes(query)
    const fullNameMatch = img.full_name.toLowerCase().includes(query)
    const registryMatch = img.registry.toLowerCase().includes(query)
    const descriptionMatch = img.description?.toLowerCase().includes(query) ?? false
    return nameMatch || tagMatch || fullNameMatch || registryMatch || descriptionMatch
  }), [deferredSearch, images])

  const isDockerUnavailable = dockerStatus === "unavailable"
  const hasImages = filteredImages.length > 0
  const isEmpty = filteredImages.length === 0
  const hasSelectableImages = filteredImages.some((image) => image.status === "local")
  const selectedImages = useMemo(() => (
    view === "cards"
      ? filteredImages.filter((image) => selectedImageIds.has(image.id) && image.status === "local")
      : []
  ), [filteredImages, selectedImageIds, view])
  const selectedImagesSize = selectedImages.reduce((total, image) => total + getImageSizeBytes(image), 0)

  const handleBatchDeleteLocal = useCallback(() => {
    if (!canDeleteImages) {
      toast.error(tImages("errors.deleteForbidden"))
      return
    }
    if (selectedImages.length === 0) {
      return
    }

    const selectedAtConfirm = selectedImages
    const totalSize = selectedAtConfirm.reduce((total, image) => total + getImageSizeBytes(image), 0)
    toast.warning(tImages("toasts.batchDeleteConfirmTitle", { count: selectedAtConfirm.length }), {
      description: tImages("toasts.batchDeleteConfirmDescription", { size: formatSize(totalSize) }),
      action: {
        label: tCommon("confirm"),
        onClick: async () => {
          setIsBatchDeleting(true)
          const removedIds = new Set<string>()
          let failedCount = 0

          for (const image of selectedAtConfirm) {
            try {
              await apiRequest(`/images/${image.id}`, { method: "DELETE" })
              removedIds.add(image.id)
            } catch {
              failedCount += 1
            }
          }

          if (removedIds.size > 0) {
            setImages((prev) => prev.filter((image) => !removedIds.has(image.id)))
            setDetailsImage((current) => current && removedIds.has(current.id) ? null : current)
            setSelectedImageIds((prev) => {
              const next = new Set(prev)
              for (const id of removedIds) {
                next.delete(id)
              }
              return next
            })
          }

          if (failedCount === 0) {
            setSelectionMode(false)
            toast.success(tImages("toasts.batchRemovedTitle", { count: removedIds.size }), {
              description: tImages("toasts.batchRemovedDescription"),
            })
          } else if (removedIds.size > 0) {
            toast.error(tImages("toasts.batchPartialRemovedTitle", {
              removed: removedIds.size,
              failed: failedCount,
            }))
          } else {
            toast.error(tImages("errors.deleteFailed"))
          }
          setIsBatchDeleting(false)
        },
      },
    })
  }, [canDeleteImages, selectedImages, tCommon, tImages])

  return {
    tImages,
    tCommon,
    images: filteredImages,
    view,
    setView,
    search,
    setSearch,
    uploadOpen,
    setUploadOpen: handleUploadOpenChange,
    importMethod,
    setImportMethod,
    imageName,
    setImageName,
    selectedRegistry,
    setSelectedRegistry,
    imageRegistries: imageRegistries.filter((registry) => getContainerRegistryValue(registry)),
    isLoading,
    isSubmitting,
    tarballFile,
    dockerStatus,
    imagesStale,
    lastSyncedAt,
    detailsImage,
    setDetailsImage,
    recommendedOpen,
    setRecommendedOpen,
    recommendedImages,
    isDockerUnavailable,
    hasImages,
    isEmpty,
    selectionMode,
    selectedImageIds,
    selectedImages,
    selectedImagesSize,
    isBatchDeleting,
    hasSelectableImages,
    handleStartSelection,
    handleCancelSelection,
    handleToggleSelection,
    handleBatchDeleteLocal,
    openRegistryDialog,
    openTarballDialog,
    handleRefresh,
    handlePullImage,
    handlePull,
    handleViewDetails,
    handleCopyName,
    handleCopyPullCommand,
    handleDeleteLocal,
    canDeleteImages,
    handleTarballFileChange,
  }
}
