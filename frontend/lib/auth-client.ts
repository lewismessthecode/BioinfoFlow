import { createAuthClient } from "better-auth/react"
import { adminClient, inferAdditionalFields } from "better-auth/client/plugins"

export const authClient = createAuthClient({
  plugins: [
    adminClient(),
    inferAdditionalFields({
      user: {
        teamRole: {
          type: "string",
          required: false,
        },
      },
    }),
  ],
})
