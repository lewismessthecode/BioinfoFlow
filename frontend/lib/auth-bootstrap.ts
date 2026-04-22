type ExistingBootstrapUser = {
  id: string
  hasCredentialAccount: boolean
}

type BootstrapOwnerInput = {
  email: string
  existingUser: ExistingBootstrapUser | null
}

type BootstrapOwnerPlan =
  | {
      type: "create"
      email: string
    }
  | {
      type: "recover"
      userId: string
      hasCredentialAccount: boolean
    }

export function planBootstrapOwner({
  email,
  existingUser,
}: BootstrapOwnerInput): BootstrapOwnerPlan {
  if (!existingUser) {
    return {
      type: "create",
      email,
    }
  }

  return {
    type: "recover",
    userId: existingUser.id,
    hasCredentialAccount: existingUser.hasCredentialAccount,
  }
}
