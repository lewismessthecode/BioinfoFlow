import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

const {
  createUserMock,
  listUsersMock,
  toastSuccessMock,
  toastErrorMock,
} = vi.hoisted(() => ({
  createUserMock: vi.fn(),
  listUsersMock: vi.fn(),
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
      listUsers: (...args: unknown[]) => listUsersMock(...args),
      createUser: (...args: unknown[]) => createUserMock(...args),
      updateUser: vi.fn(),
      banUser: vi.fn(),
      unbanUser: vi.fn(),
      revokeUserSessions: vi.fn(),
      setUserPassword: vi.fn(),
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
    createUserMock.mockReset()
    listUsersMock.mockReset()
    toastSuccessMock.mockReset()
    toastErrorMock.mockReset()
  })

  it("treats Better Auth createUser errors as failures instead of silent success", async () => {
    const user = userEvent.setup()
    listUsersMock.mockResolvedValue({
      data: {
        users: [
          {
            id: "owner-1",
            name: "Owner",
            email: "owner@example.com",
            role: "admin",
            teamRole: "owner",
          },
        ],
      },
      error: null,
    })
    createUserMock.mockResolvedValue({
      data: null,
      error: { message: "Email already exists" },
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
      expect(toastErrorMock).toHaveBeenCalledWith("Could not create member")
    })
    expect(toastSuccessMock).not.toHaveBeenCalledWith("Member created")
    expect(listUsersMock).toHaveBeenCalledTimes(1)
  })
})
