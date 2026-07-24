import { apiRequest, buildWebSocketUrl } from "@/lib/api"

export type RemoteConnectionStatus = "online" | "offline" | "error" | "unknown"

export type RemoteConnectionAuthMethod =
  | "password"
  | "private_key"
  | "ssh_config"
  | "key_file"
  | "agent"
  | "jump"

export type RemoteConnection = {
  id: string
  name: string
  host: string
  port: number
  username: string
  auth_method: RemoteConnectionAuthMethod
  jump_connection_id?: string | null
  ssh_alias: string
  key_path: string
  status: RemoteConnectionStatus
  last_status?: RemoteConnectionStatus
  skill_instructions: string
  status_message?: string
  last_error?: string | null
  last_checked_at?: string
}

export type RemoteConnectionTestResult = {
  status: RemoteConnectionStatus
  error: string | null
  checked_at: string
  connection: RemoteConnection
}

export type RemoteCommandFrame = {
  type: "stdout" | "stderr" | "truncated" | "error" | "exit"
  data?: string
  message?: string
  exit_code?: number
  timed_out?: boolean
}

export type RemoteCommandResult = {
  frames: RemoteCommandFrame[]
  output: string
  exitCode: number | null
  timedOut: boolean
}

type RemoteDirectoryEntry = {
  name: string
  path: string
  type: "dir" | "file"
  kind?: "directory" | "file" | "symlink" | "other"
  size?: number | null
}

export type RemoteDirectoryList = {
  path: string
  entries: RemoteDirectoryEntry[]
  truncated?: boolean
}

type RemoteConnectionListResponse =
  | RemoteConnection[]
  | {
      connections?: RemoteConnection[]
      data?: RemoteConnection[]
    }

export const remoteConnectionsApiPath = "/connections"

export type RemoteConnectionCreateInput = {
  name: string
  host: string
  port: number
  username: string
  auth_method: RemoteConnectionAuthMethod
  jump_connection_id?: string | null
  ssh_alias?: string | null
  key_path?: string | null
  password?: string | null
  private_key?: string | null
  passphrase?: string | null
  skill_instructions?: string | null
}

export type RemoteConnectionUpdateInput = Partial<RemoteConnectionCreateInput>

export async function fetchRemoteConnections(): Promise<RemoteConnection[]> {
  const response = await apiRequest<RemoteConnectionListResponse>(remoteConnectionsApiPath)
  const payload = response.data

  if (Array.isArray(payload)) {
    return payload.map(normalizeRemoteConnection)
  }

  return (payload.connections ?? payload.data ?? []).map(normalizeRemoteConnection)
}

export async function browseRemoteConnectionDirectory(
  connectionId: string,
  path: string,
): Promise<RemoteDirectoryList> {
  const response = await apiRequest<RemoteDirectoryList>(
    `${remoteConnectionsApiPath}/${connectionId}/directories`,
    { params: { path } },
  )
  return response.data
}

export async function createRemoteConnection(
  input: RemoteConnectionCreateInput,
): Promise<RemoteConnection> {
  const response = await apiRequest<RemoteConnection>(remoteConnectionsApiPath, {
    method: "POST",
    body: JSON.stringify(input),
  })
  return normalizeRemoteConnection(response.data)
}

export async function updateRemoteConnection(
  connectionId: string,
  input: RemoteConnectionUpdateInput,
): Promise<RemoteConnection> {
  const response = await apiRequest<RemoteConnection>(`${remoteConnectionsApiPath}/${connectionId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  })
  return normalizeRemoteConnection(response.data)
}

export async function deleteRemoteConnection(connectionId: string): Promise<void> {
  await apiRequest<null>(`${remoteConnectionsApiPath}/${connectionId}`, {
    method: "DELETE",
  })
}

export async function testRemoteConnection(
  connectionId: string,
): Promise<RemoteConnectionTestResult> {
  const response = await apiRequest<{
    status: RemoteConnectionStatus
    error: string | null
    checked_at: string
    connection: RemoteConnection
  }>(`${remoteConnectionsApiPath}/${connectionId}/test`, {
    method: "POST",
  })

  return {
    ...response.data,
    connection: normalizeRemoteConnection(response.data.connection),
  }
}

export async function runRemoteConnectionCommand(
  connectionId: string,
  options: {
    command: string
    timeout_seconds?: number
    onFrame?: (frame: RemoteCommandFrame) => void
  },
): Promise<RemoteCommandResult> {
  const frames: RemoteCommandFrame[] = []
  let output = ""
  let exitCode: number | null = null
  let timedOut = false

  return new Promise((resolve, reject) => {
    const socket = new WebSocket(
      buildWebSocketUrl(`${remoteConnectionsApiPath}/${connectionId}/exec/ws`),
    )
    let settled = false

    const finish = () => {
      if (settled) return
      settled = true
      cleanup()
      resolve({ frames, output, exitCode, timedOut })
    }

    const fail = (error: Error) => {
      if (settled) return
      settled = true
      cleanup()
      reject(error)
    }

    const cleanup = () => {
      socket.onopen = null
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
    }

    const closeSocket = () => {
      try {
        socket.close()
      } catch {
        // The promise has already settled; close errors should not mask the real result.
      }
    }

    const addFrame = (frame: RemoteCommandFrame) => {
      frames.push(frame)
      if ((frame.type === "stdout" || frame.type === "stderr") && frame.data) {
        output += frame.data
      }
      if (frame.type === "error") {
        output += frame.message ? `${frame.message}\n` : ""
      }
      if (frame.type === "exit") {
        exitCode = frame.exit_code ?? null
        timedOut = Boolean(frame.timed_out)
      }
      options.onFrame?.(frame)
    }

    socket.onopen = () => {
      try {
        socket.send(
          JSON.stringify({
            command: options.command,
            timeout_seconds: options.timeout_seconds ?? 15,
          }),
        )
      } catch {
        fail(new Error("Remote command stream failed"))
        closeSocket()
      }
    }

    socket.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data) as RemoteCommandFrame
        addFrame(frame)
        if (frame.type === "error") {
          fail(new Error(frame.message || "Remote command failed"))
          closeSocket()
          return
        }
        if (frame.type === "exit") {
          finish()
          closeSocket()
        }
      } catch {
        fail(new Error("Failed to parse remote command output"))
        closeSocket()
      }
    }

    socket.onerror = () => {
      fail(new Error("Remote command stream failed"))
      closeSocket()
    }

    socket.onclose = () => {
      fail(new Error("Remote command stream closed before completion"))
    }
  })
}

function normalizeRemoteConnection(connection: RemoteConnection): RemoteConnection {
  const status = connection.last_status ?? connection.status ?? "unknown"
  const authMethod = connection.auth_method
  return {
    ...connection,
    status,
    jump_connection_id: authMethod === "jump" ? connection.jump_connection_id ?? null : null,
    ssh_alias: authMethod === "ssh_config" ? connection.ssh_alias ?? "" : "",
    key_path: authMethod === "key_file" ? connection.key_path ?? "" : "",
    skill_instructions: connection.skill_instructions ?? "",
    status_message: connection.status_message ?? connection.last_error ?? undefined,
  }
}

export const demoConnectionNodes: RemoteConnection[] = [
  {
    id: "connection-sim-224",
    name: "Simulation host sz01",
    host: "10.227.5.224",
    port: 22,
    username: "bioflow",
    auth_method: "key_file",
    jump_connection_id: null,
    ssh_alias: "",
    key_path: "~/.ssh/bioflow_sim_ed25519",
    status: "online",
    skill_instructions:
      "Use this host for Phoenix simulation runs. Phoenix outputs usually live under /mnt/nas/phoenix-output, and failed tasks should be checked in logs/current_step.log before reruns. Load the Nextflow environment with the site profile before submitting long jobs.",
  },
  {
    id: "connection-test-231",
    name: "Test host sz03",
    host: "10.227.5.231",
    port: 22,
    username: "bioflow",
    auth_method: "ssh_config",
    jump_connection_id: null,
    ssh_alias: "bioflow-test-sz03",
    key_path: "~/.ssh/bioflow_test-cert.pub",
    status: "online",
    skill_instructions:
      "Use this host for FASTQ validation and container-backed test runs. Inputs are mounted at /mnt/nas/fastq, results are grouped by project under /mnt/nas/results, and the local registry endpoint is available from the host network.",
  },
  {
    id: "connection-uat-245",
    name: "Acceptance host sz02",
    host: "10.227.5.245",
    port: 22,
    username: "odp-user",
    auth_method: "agent",
    jump_connection_id: null,
    ssh_alias: "",
    key_path: "",
    status: "offline",
    status_message: "The last connection test failed.",
    skill_instructions:
      "Use this host for ODP acceptance checks after confirming availability. ODP outputs are staged under /mnt/nas/odp-output, and the latest delivery folder should be confirmed before reading results.",
  },
]
