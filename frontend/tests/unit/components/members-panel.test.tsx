import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const {
  fetchMock,
  toastSuccessMock,
  toastErrorMock,
} = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
}))

const translate = (key: string) => {
  const labels: Record<string, string> = {
    title: "Members",
    description: "Manage members",
    createCta: "Add member",
    loading: "Loading members...",
    loadFailed: "Could not load members",
    created: "Member created",
    createFailed: "Could not create member",
    createTitle: "Create member",
    createDescription: "Create a team account.",
    createAction: "Create",
    cancel: "Cancel",
    disabledBadge: "Disabled",
    you: "You",
    disable: "Disable",
    enable: "Enable",
    resetPassword: "Reset password",
    revokeSessions: "Revoke sessions",
    "fields.name": "Name",
    "fields.email": "Email",
    "fields.password": "Password",
    "fields.role": "Role",
    "roles.owner": "Owner",
    "roles.admin": "Admin",
    "roles.member": "Member",
  }
  return labels[key] ?? key
}

vi.mock("next-intl", () => ({
  useTranslations: () => translate,
}))

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    admin: {
      revokeUserSessions: vi.fn(),
    },
  },
}))

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}))

import { MembersPanel } from "@/components/bioinfoflow/settings/members-panel"

describe("MembersPanel", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    Element.prototype.hasPointerCapture ??= vi.fn()
    Element.prototype.releasePointerCapture ??= vi.fn()
    Element.prototype.scrollIntoView ??= vi.fn()
    toastSuccessMock.mockReset()
    toastErrorMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const okJson = (data: unknown) =>
    new Response(JSON.stringify({ success: true, data }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })

  const errorJson = (message: string, status = 400) =>
    new Response(
      JSON.stringify({
        success: false,
        error: { message },
      }),
      {
        status,
        headers: { "Content-Type": "application/json" },
      },
    )

  it("treats Better Auth createUser errors as failures instead of silent success", async () => {
    const user = userEvent.setup()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === "/api/team/members" && !init?.method) {
        return okJson({
        users: [
          {
            id: "owner-1",
            name: "Owner",
            email: "owner@example.com",
            role: "admin",
            teamRole: "owner",
          },
        ],
        })
      }
      if (url === "/api/team/members" && init?.method === "POST") {
        return errorJson("Email already exists", 409)
      }
      throw new Error(`Unexpected fetch: ${url}`)
    })

    render(
      <MembersPanel
        viewerId="owner-1"
        viewerRole="owner"
        authLocalEnabled
      />,
    )

    await screen.findByText("owner@example.com")
    await user.click(screen.getByRole("button", { name: "Add member" }))
    await user.type(screen.getByLabelText("Name"), "New Member")
    await user.type(screen.getByLabelText("Email"), "new@example.com")
    await user.type(screen.getByLabelText("Password"), "secret123")
    await user.click(screen.getByRole("button", { name: "Create" }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("Email already exists")
    })
    expect(toastSuccessMock).not.toHaveBeenCalledWith("Member created")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("creates a member through the team API and refreshes the list", async () => {
    const user = userEvent.setup()
    fetchMock
      .mockResolvedValueOnce(
        okJson({
          users: [
            {
              id: "owner-1",
              name: "Owner",
              email: "owner@example.com",
              role: "admin",
              teamRole: "owner",
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        okJson({
          user: {
            id: "member-1",
            name: "New Member",
            email: "new@example.com",
            role: "user",
            teamRole: "member",
          },
        }),
      )
      .mockResolvedValueOnce(
        okJson({
          users: [
            {
              id: "owner-1",
              name: "Owner",
              email: "owner@example.com",
              role: "admin",
              teamRole: "owner",
            },
            {
              id: "member-1",
              name: "New Member",
              email: "new@example.com",
              role: "user",
              teamRole: "member",
            },
          ],
        }),
      )

    render(
      <MembersPanel
        viewerId="owner-1"
        viewerRole="owner"
        authLocalEnabled
      />,
    )

    await screen.findByText("owner@example.com")
    await user.click(screen.getByRole("button", { name: "Add member" }))
    await user.type(screen.getByLabelText("Name"), "New Member")
    await user.type(screen.getByLabelText("Email"), "new@example.com")
    await user.type(screen.getByLabelText("Password"), "secret123")
    await user.click(screen.getByRole("button", { name: "Create" }))

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalledWith("Member created")
    })
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/team/members",
      expect.objectContaining({
        method: "POST",
        body: expect.any(String),
      }),
    )
    const createCall = fetchMock.mock.calls.find(
      ([path, init]) => path === "/api/team/members" && init?.method === "POST",
    )
    expect(JSON.parse(createCall?.[1]?.body as string)).toEqual({
      name: "New Member",
      email: "new@example.com",
      password: "secret123",
      teamRole: "member",
    })
    expect(await screen.findByText("new@example.com")).toBeInTheDocument()
  })

  it("prevents admins from assigning the owner role when creating members", async () => {
    const user = userEvent.setup()
    fetchMock.mockResolvedValue(
      okJson({
        users: [
          {
            id: "admin-1",
            name: "Admin",
            email: "admin@example.com",
            role: "admin",
            teamRole: "admin",
          },
        ],
      }),
    )

    render(
      <MembersPanel
        viewerId="admin-1"
        viewerRole="admin"
        authLocalEnabled
      />,
    )

    await screen.findByText("admin@example.com")
    await user.click(screen.getByRole("button", { name: "Add member" }))
    await user.click(screen.getByRole("combobox", { name: /role/i }))

    expect(screen.getByRole("option", { name: "Owner" })).toHaveAttribute(
      "aria-disabled",
      "true",
    )
  })
})
