import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      directoryBrowser: "Choose Directory",
      selectDirectoryDescription: "Navigate to and select a directory for your project workspace",
      selectDirectory: "Select this directory",
      goUp: "Go up",
      browseDirectories: "Browse...",
      cancel: "Cancel",
    }
    return copy[key] ?? key
  },
}))

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
}))

vi.mock("@/lib/demo-connections", () => ({
  browseRemoteConnectionDirectory: vi.fn(),
}))

import { DirectoryBrowser } from "@/components/bioinfoflow/directory-browser"
import { apiRequest } from "@/lib/api"
import { browseRemoteConnectionDirectory } from "@/lib/demo-connections"

const mockedApiRequest = vi.mocked(apiRequest)
const mockedBrowseRemoteConnectionDirectory = vi.mocked(browseRemoteConnectionDirectory)

const makeDirResponse = (
  path: string,
  parent: string | null,
  dirs: { name: string; path: string }[]
) => ({
  data: { path, parent, directories: dirs },
  meta: undefined,
})

describe("DirectoryBrowser", () => {
  const onSelect = vi.fn()
  const onOpenChange = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders the dialog title when open", async () => {
    mockedApiRequest.mockResolvedValueOnce(
      makeDirResponse("/home/user", "/home", [])
    )

    render(
      <DirectoryBrowser
        open={true}
        onOpenChange={onOpenChange}
        onSelect={onSelect}
      />
    )

    expect(await screen.findByText("Choose Directory")).toBeInTheDocument()
  })

  it("displays directories returned by the API", async () => {
    mockedApiRequest.mockResolvedValueOnce(
      makeDirResponse("/home/user", "/home", [
        { name: "Documents", path: "/home/user/Documents" },
        { name: "Projects", path: "/home/user/Projects" },
      ])
    )

    render(
      <DirectoryBrowser
        open={true}
        onOpenChange={onOpenChange}
        onSelect={onSelect}
      />
    )

    expect(await screen.findByText("Documents")).toBeInTheDocument()
    expect(screen.getByText("Projects")).toBeInTheDocument()
  })

  it("navigates into a directory on click", async () => {
    const user = userEvent.setup()

    mockedApiRequest
      .mockResolvedValueOnce(
        makeDirResponse("/home/user", "/home", [
          { name: "Documents", path: "/home/user/Documents" },
        ])
      )
      .mockResolvedValueOnce(
        makeDirResponse("/home/user/Documents", "/home/user", [
          { name: "work", path: "/home/user/Documents/work" },
        ])
      )

    render(
      <DirectoryBrowser
        open={true}
        onOpenChange={onOpenChange}
        onSelect={onSelect}
      />
    )

    const docButton = await screen.findByText("Documents")
    await user.click(docButton)

    expect(await screen.findByText("work")).toBeInTheDocument()
  })

  it("calls onSelect with the current path when select button is clicked", async () => {
    const user = userEvent.setup()

    mockedApiRequest.mockResolvedValueOnce(
      makeDirResponse("/home/user/Projects", "/home/user", [])
    )

    render(
      <DirectoryBrowser
        open={true}
        onOpenChange={onOpenChange}
        onSelect={onSelect}
        initialPath="/home/user/Projects"
      />
    )

    const selectBtn = await screen.findByRole("button", {
      name: "Select this directory",
    })
    await user.click(selectBtn)

    expect(onSelect).toHaveBeenCalledWith("/home/user/Projects")
  })

  it("navigates up when go-up button is clicked", async () => {
    const user = userEvent.setup()

    mockedApiRequest
      .mockResolvedValueOnce(
        makeDirResponse("/home/user/Documents", "/home/user", [])
      )
      .mockResolvedValueOnce(
        makeDirResponse("/home/user", "/home", [
          { name: "Documents", path: "/home/user/Documents" },
        ])
      )

    render(
      <DirectoryBrowser
        open={true}
        onOpenChange={onOpenChange}
        onSelect={onSelect}
        initialPath="/home/user/Documents"
      />
    )

    const upButton = await screen.findByRole("button", { name: "Go up" })
    await user.click(upButton)

    expect(await screen.findByText("Documents")).toBeInTheDocument()
  })

  it("uses initialPath when provided", async () => {
    mockedApiRequest.mockResolvedValueOnce(
      makeDirResponse("/custom/path", "/custom", [])
    )

    render(
      <DirectoryBrowser
        open={true}
        onOpenChange={onOpenChange}
        onSelect={onSelect}
        initialPath="/custom/path"
      />
    )

    await screen.findByText("Choose Directory")

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/system/directories",
      expect.objectContaining({
        params: expect.objectContaining({ path: "/custom/path" }),
      })
    )
  })

  it("shows remote directories but hides non-directory symlinks", async () => {
    mockedBrowseRemoteConnectionDirectory.mockResolvedValueOnce({
      path: "/data/project",
      entries: [
        {
          name: "results",
          path: "/data/project/results",
          type: "dir",
          kind: "directory",
          size: null,
        },
        {
          name: "latest.fastq",
          path: "/data/project/latest.fastq",
          type: "file",
          kind: "symlink",
          size: 21,
        },
      ],
      truncated: false,
    })

    render(
      <DirectoryBrowser
        open={true}
        onOpenChange={onOpenChange}
        onSelect={onSelect}
        source="remote"
        remoteConnectionId="11111111-1111-1111-1111-111111111111"
        initialPath="/data/project"
      />
    )

    expect(await screen.findByText("results")).toBeInTheDocument()
    expect(screen.queryByText("latest.fastq")).not.toBeInTheDocument()
  })
})
