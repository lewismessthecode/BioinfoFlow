import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useImagesPage } from "@/app/(app)/images/use-images-page"
import { apiRequest } from "@/lib/api"
import { createAppWrapper } from "@/tests/app-test-utils"

const {
  toastErrorMock,
  toastInfoMock,
  toastSuccessMock,
  toastWarningMock,
} = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
  toastInfoMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastWarningMock: vi.fn(),
}))

const translationMap = new Map<string, (key: string, values?: Record<string, unknown>) => string>()

function getTranslation(namespace: string) {
  if (!translationMap.has(namespace)) {
    translationMap.set(namespace, (key: string, values?: Record<string, unknown>) => {
      const suffix = values
        ? Object.values(values)
            .filter((value) => value !== undefined && value !== null)
            .join(":")
        : ""
      return suffix ? `${namespace}.${key}:${suffix}` : `${namespace}.${key}`
    })
  }
  return translationMap.get(namespace)!
}

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => getTranslation(namespace),
}))

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    info: toastInfoMock,
    success: toastSuccessMock,
    warning: toastWarningMock,
  },
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

describe("useImagesPage", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  const makeImage = (overrides: Record<string, unknown> = {}) => ({
    id: String(overrides.id ?? "img-1"),
    name: String(overrides.name ?? "ghcr.io/demo/tool"),
    tag: String(overrides.tag ?? "1.0.0"),
    full_name: String(overrides.full_name ?? "ghcr.io/demo/tool:1.0.0"),
    description: String(overrides.description ?? "demo image"),
    size_bytes: Number(overrides.size_bytes ?? 1024),
    status: String(overrides.status ?? "remote"),
    registry: String(overrides.registry ?? "ghcr.io"),
    pull_progress: overrides.pull_progress ?? null,
    error_message: overrides.error_message ?? null,
    labels: overrides.labels ?? { maintainer: "Bioinfoflow" },
    env: overrides.env ?? ["PATH=/usr/bin"],
    entrypoint: overrides.entrypoint ?? ["/bin/sh"],
    created_at: String(overrides.created_at ?? "2026-04-08T08:00:00.000Z"),
    updated_at: String(overrides.updated_at ?? "2026-04-08T08:05:00.000Z"),
  })

  const imageStatus = (overrides: Record<string, unknown> = {}) => ({
    docker: "available",
    images_stale: false,
    last_synced_at: "2026-04-08T08:05:00+00:00",
    ...overrides,
  })

  beforeEach(() => {
    apiRequestMock.mockReset()
    toastErrorMock.mockReset()
    toastInfoMock.mockReset()
    toastSuccessMock.mockReset()
    toastWarningMock.mockReset()
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  it("retries image sync when docker is unavailable and the cache is empty", async () => {
    vi.useFakeTimers()

    apiRequestMock
      .mockResolvedValueOnce({
        data: [],
        meta: { status: imageStatus({ docker: "unavailable", last_synced_at: null }) },
      })
      .mockResolvedValueOnce({
        data: [makeImage({ status: "local" })],
        meta: { status: imageStatus() },
      })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(() => useImagesPage(), { wrapper: Wrapper })

    await act(async () => {
      await Promise.resolve()
    })

    expect(result.current.dockerStatus).toBe("unavailable")
    expect(apiRequestMock).toHaveBeenNthCalledWith(1, "/images", {
      params: { limit: 100, force_sync: undefined },
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000)
    })

    expect(apiRequestMock).toHaveBeenNthCalledWith(2, "/images", {
      params: { limit: 100, force_sync: true },
    })
    expect(result.current.images).toHaveLength(1)
  })

  it("includes the active project id when pulling a registry image", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/images") {
        return {
          data: [],
          meta: { status: imageStatus() },
        }
      }
      if (path === "/images/pull" && options?.method === "POST") {
        return { data: makeImage({ status: "pulling" }), meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-123",
    })
    const { result } = renderHook(() => useImagesPage(), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      result.current.setImageName("localhost:5000/demo/tool:2.0.0")
    })

    await act(async () => {
      result.current.handlePullImage()
    })

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenCalledWith("/images/pull", {
        method: "POST",
        body: JSON.stringify({
          name: "localhost:5000/demo/tool",
          tag: "2.0.0",
          project_id: "project-123",
        }),
      }),
    )
    expect(toastSuccessMock).toHaveBeenCalled()
  })

  it("includes the active project id in tarball uploads", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/images") {
        return {
          data: [],
          meta: { status: imageStatus() },
        }
      }
      if (path === "/images/load" && options?.method === "POST") {
        return { data: [makeImage({ status: "local" })], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const tarball = new File(["tar"], "image.tar", { type: "application/x-tar" })
    const Wrapper = createAppWrapper({
      activeProjectId: "project-456",
    })
    const { result } = renderHook(() => useImagesPage(), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      result.current.setImportMethod("tarball")
      result.current.handleTarballFileChange({
        target: { files: [tarball] },
      } as React.ChangeEvent<HTMLInputElement>)
    })

    await act(async () => {
      result.current.handlePullImage()
    })

    await waitFor(() => {
      const call = apiRequestMock.mock.calls.find(
        ([path, options]) => path === "/images/load" && options?.method === "POST",
      )
      expect(call).toBeDefined()
      const form = call?.[1]?.body
      expect(form).toBeInstanceOf(FormData)
      expect((form as FormData).get("project_id")).toBe("project-456")
      expect((form as FormData).get("file")).toBe(tarball)
    })
    expect(toastSuccessMock).toHaveBeenCalled()
  })

  it("filters images by tag and full image name", async () => {
    apiRequestMock.mockResolvedValue({
      data: [
        makeImage({
          id: "img-1",
          name: "minibwa",
          tag: "1.0",
          full_name: "minibwa:1.0",
        }),
        makeImage({
          id: "img-2",
          name: "minibwa",
          tag: "1.0-FIXED",
          full_name: "minibwa:1.0-FIXED",
        }),
      ],
      meta: { status: imageStatus() },
    })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(() => useImagesPage(), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      result.current.setSearch("fixed")
    })

    await waitFor(() => {
      expect(result.current.images.map((item) => item.tag)).toEqual(["1.0-FIXED"])
    })
  })

  it("forces a silent refresh on window focus when docker is available", async () => {
    apiRequestMock
      .mockResolvedValueOnce({
        data: [makeImage({ status: "local" })],
        meta: { status: imageStatus() },
      })
      .mockResolvedValueOnce({
        data: [makeImage({ status: "local", updated_at: "2026-04-08T08:06:00.000Z" })],
        meta: { status: imageStatus({ last_synced_at: "2026-04-08T08:06:00+00:00" }) },
      })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(() => useImagesPage(), { wrapper: Wrapper })

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenNthCalledWith(1, "/images", {
        params: { limit: 100, force_sync: undefined },
      }),
    )
    await waitFor(() => expect(result.current.dockerStatus).toBe("available"))

    act(() => {
      window.dispatchEvent(new FocusEvent("focus"))
    })

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenNthCalledWith(2, "/images", {
        params: { limit: 100, force_sync: true },
      }),
    )
  })
})
