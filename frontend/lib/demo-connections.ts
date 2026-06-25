import { apiRequest } from "@/lib/api"

export type RemoteConnectionStatus = "online" | "offline" | "error" | "unknown"

export type RemoteConnectionAuthMethod = "ssh_config" | "key_file" | "agent"

export type RemoteConnection = {
  id: string
  name: string
  host: string
  port: number
  username: string
  auth_method: RemoteConnectionAuthMethod
  ssh_alias: string
  key_path: string
  status: RemoteConnectionStatus
  last_status?: RemoteConnectionStatus
  skill_instructions: string
  status_message?: string
  last_error?: string | null
  last_checked_at?: string
}

type RemoteConnectionListResponse =
  | RemoteConnection[]
  | {
      connections?: RemoteConnection[]
      data?: RemoteConnection[]
    }

export const remoteConnectionsApiPath = "/connections"

export async function fetchRemoteConnections(): Promise<RemoteConnection[]> {
  const response = await apiRequest<RemoteConnectionListResponse>(remoteConnectionsApiPath)
  const payload = response.data

  if (Array.isArray(payload)) {
    return payload.map(normalizeRemoteConnection)
  }

  return (payload.connections ?? payload.data ?? []).map(normalizeRemoteConnection)
}

function normalizeRemoteConnection(connection: RemoteConnection): RemoteConnection {
  const status = connection.status ?? connection.last_status ?? "unknown"
  return {
    ...connection,
    status,
    ssh_alias: connection.ssh_alias ?? "",
    key_path: connection.key_path ?? "",
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
    ssh_alias: "bioflow-sim-sz01",
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
    ssh_alias: "odp-uat-sz02",
    key_path: "",
    status: "offline",
    status_message: "The last connection test failed.",
    skill_instructions:
      "Use this host for ODP acceptance checks after confirming availability. ODP outputs are staged under /mnt/nas/odp-output, and the latest delivery folder should be confirmed before reading results.",
  },
]
