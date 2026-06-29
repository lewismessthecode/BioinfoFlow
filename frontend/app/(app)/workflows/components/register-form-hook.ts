import { type ChangeEvent, useState } from "react"

export type SourceType = "nf-core" | "github" | "local"
export type EngineType = "nextflow" | "wdl"
export type LocalImportMode = "bundle" | "single-file"
export type RegistrationStep = "reading" | "validating" | "parsing" | "registering"
export type LocalBundleFile = {
  file: File
  relpath: string
}

export const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50 MB
export const ALLOWED_EXTENSIONS = [".wdl", ".nf"]

export function useRegisterForm() {
  const [sourceType, setSourceType] = useState<SourceType>("nf-core")
  const [engine, setEngine] = useState<EngineType>("nextflow")
  const [pipelineName, setPipelineName] = useState("")
  const [version, setVersion] = useState("")
  const [description, setDescription] = useState("")
  const [selectedRegistry, setSelectedRegistry] = useState("")
  const [localImportMode, setLocalImportMode] = useState<LocalImportMode>("bundle")
  const [localFile, setLocalFile] = useState<File | null>(null)
  const [localFileName, setLocalFileName] = useState("")
  const [bundleFiles, setBundleFiles] = useState<LocalBundleFile[]>([])
  const [bundleLabel, setBundleLabel] = useState("")
  const [entrypointCandidates, setEntrypointCandidates] = useState<string[]>([])
  const [entrypointRelpath, setEntrypointRelpath] = useState("")

  const reset = () => {
    setSourceType("nf-core")
    setEngine("nextflow")
    setPipelineName("")
    setVersion("")
    setDescription("")
    setSelectedRegistry("")
    setLocalImportMode("bundle")
    setLocalFile(null)
    setLocalFileName("")
    setBundleFiles([])
    setBundleLabel("")
    setEntrypointCandidates([])
    setEntrypointRelpath("")
  }

  const handleSourceChange = (type: SourceType) => {
    setSourceType(type)
    if (type === "nf-core") {
      setEngine("nextflow")
    }
    if (type !== "local") {
      setLocalFile(null)
      setLocalFileName("")
      setBundleFiles([])
      setBundleLabel("")
      setEntrypointCandidates([])
      setEntrypointRelpath("")
    }
  }

  const handleLocalFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setLocalFile(file)
    setLocalFileName(file.name)

    const lower = file.name.toLowerCase()
    if (lower.endsWith(".wdl")) {
      setEngine("wdl")
    } else if (lower.endsWith(".nf")) {
      setEngine("nextflow")
    }

    if (!pipelineName.trim()) {
      const baseName = file.name.replace(/\.(nf|wdl)$/i, "")
      setPipelineName(baseName)
    }
  }

  const handleBundleDirectoryChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? [])
    if (!selected.length) return

    const firstRawRelpath =
      getFileRelativePath(selected[0]) || selected[0].name
    const rootLabel = firstRawRelpath.split("/").filter(Boolean)[0] || selected[0].name
    const normalized = selected.map((file) => ({
      file,
      relpath: normalizeBundleRelativePath(file, rootLabel),
    }))
    normalized.sort((a, b) => a.relpath.localeCompare(b.relpath))

    const candidates = normalized
      .map((entry) => entry.relpath)
      .filter((relpath) => {
        const lower = relpath.toLowerCase()
        return lower.endsWith(".nf") || lower.endsWith(".wdl")
      })

    const detectedEntrypoint =
      detectBundleEntrypoint(candidates) ?? ""

    setBundleFiles(normalized)
    setBundleLabel(rootLabel)
    setEntrypointCandidates(candidates)
    setEntrypointRelpath(detectedEntrypoint)

    if (detectedEntrypoint.toLowerCase().endsWith(".wdl")) {
      setEngine("wdl")
    } else if (detectedEntrypoint.toLowerCase().endsWith(".nf")) {
      setEngine("nextflow")
    }

    if (!pipelineName.trim() && rootLabel) {
      setPipelineName(rootLabel)
    }

    event.target.value = ""
  }

  return {
    sourceType,
    engine,
    setEngine,
    pipelineName,
    setPipelineName,
    version,
    setVersion,
    description,
    setDescription,
    selectedRegistry,
    setSelectedRegistry,
    localImportMode,
    setLocalImportMode,
    localFile,
    localFileName,
    bundleFiles,
    bundleLabel,
    entrypointCandidates,
    entrypointRelpath,
    setEntrypointRelpath,
    reset,
    handleSourceChange,
    handleLocalFileChange,
    handleBundleDirectoryChange,
  }
}

function getFileRelativePath(file: File): string {
  const relpath = (file as File & { webkitRelativePath?: string }).webkitRelativePath
  return relpath && relpath.trim() ? relpath : file.name
}

function normalizeBundleRelativePath(file: File, rootLabel: string): string {
  const relpath = getFileRelativePath(file).replaceAll("\\", "/")
  const prefix = `${rootLabel}/`
  return relpath.startsWith(prefix) ? relpath.slice(prefix.length) : relpath
}

function detectBundleEntrypoint(candidates: string[]): string | null {
  for (const candidate of ["main.nf", "main.wdl", "workflow.nf", "workflow.wdl"]) {
    if (candidates.includes(candidate)) return candidate
  }
  return candidates[0] ?? null
}
