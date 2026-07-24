import type { ReadinessCheck } from "./dashboard-types";

type ReadinessCounts = {
  requiredTotal: number;
  requiredCompleted: number;
  blockers: number;
  optionalWarnings: number;
  requiredProgress: number;
};

export type ReadinessGroups = {
  required: ReadinessCheck[];
  optional: ReadinessCheck[];
  completed: ReadinessCheck[];
};

export type ReadinessSummary = ReadinessCounts & {
  groups: ReadinessGroups;
  hasBlockingOpenChecks: boolean;
};

export type GpuReadinessFacts = {
  state: "ready" | "visible" | "disabled" | "dockerUnavailable" | "toolkitUnavailable" | "noGpus" | "policyInvalid" | "probeFailed" | "runtimeHidden" | "hostOnly" | "error" | "cpuOnly";
  gpuCount: number;
  names: string;
  recommendation: string;
  error: string;
};

export function summarizeReadinessChecks(checks: ReadinessCheck[]): ReadinessSummary {
  const groups: ReadinessGroups = {
    required: [],
    optional: [],
    completed: [],
  };
  let requiredTotal = 0;
  let requiredCompleted = 0;
  let blockers = 0;
  let optionalWarnings = 0;
  let hasBlockingOpenChecks = false;

  for (const check of checks) {
    const isBlocking = check.severity === "blocking";
    const isComplete = check.status === "pass";

    if (isBlocking) {
      requiredTotal += 1;
      if (isComplete) {
        requiredCompleted += 1;
      } else {
        groups.required.push(check);
        hasBlockingOpenChecks = true;
        if (check.status === "fail") {
          blockers += 1;
        }
      }
    } else if (!isComplete) {
      optionalWarnings += 1;
      groups.optional.push(check);
    }

    if (isComplete) {
      groups.completed.push(check);
    }
  }

  return {
    requiredTotal,
    requiredCompleted,
    blockers,
    optionalWarnings,
    requiredProgress:
      requiredTotal > 0 ? Math.round((requiredCompleted / requiredTotal) * 100) : 0,
    groups,
    hasBlockingOpenChecks,
  };
}

export function readBoolean(value: unknown): boolean {
  return value === true;
}

export function readNumber(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
}

export function gpuReadinessFactsFor(check: ReadinessCheck): GpuReadinessFacts {
  const facts = check.facts ?? {};
  const gpuCount = readNumber(facts.gpu_count);
  const names = readStringList(facts.gpu_names).join(", ");
  const recommendation = readString(facts.recommendation);
  const error = readString(facts.error);
  const state = readString(facts.state);

  const stableStates: Record<string, GpuReadinessFacts["state"]> = {
    disabled: "disabled",
    docker_unavailable: "dockerUnavailable",
    toolkit_unavailable: "toolkitUnavailable",
    no_gpus: "noGpus",
    policy_invalid: "policyInvalid",
    probe_failed: "probeFailed",
  };

  if (readBoolean(facts.usable_for_gpu_workflows)) {
    return { state: "ready", gpuCount, names, recommendation, error };
  }
  if (stableStates[state]) {
    return { state: stableStates[state], gpuCount, names, recommendation, error };
  }
  if (readBoolean(facts.runtime_visible_to_backend) && gpuCount > 0) {
    return { state: "visible", gpuCount, names, recommendation, error };
  }
  if (readBoolean(facts.docker_nvidia_runtime)) {
    return { state: "runtimeHidden", gpuCount, names, recommendation, error };
  }
  if (readBoolean(facts.nvidia_smi_found)) {
    return { state: "hostOnly", gpuCount, names, recommendation, error };
  }
  if (error && error !== "nvidia-smi not found") {
    return { state: "error", gpuCount, names, recommendation, error };
  }
  return { state: "cpuOnly", gpuCount, names, recommendation, error };
}
