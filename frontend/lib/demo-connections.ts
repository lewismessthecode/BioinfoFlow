export type DemoConnectionStatus = "online" | "offline" | "partial" | "unknown"

export type LocalizedDemoText = {
  en: string
  zhCN: string
}

export type DemoConnectionApi = {
  name: string
  baseUrl: string
}

export type DemoConnectionNode = {
  id: string
  address: string
  label: LocalizedDemoText
  group: LocalizedDemoText
  status: DemoConnectionStatus
  tags: string[]
  ssh: {
    port: number
    username: string
    auth: "password" | "key" | "certificate" | "fido2"
  }
  skills: string[]
  prompts: LocalizedDemoText[]
  paths: string[]
  apis: DemoConnectionApi[]
  environmentVariables: string[]
  startupSnippet: string
  issue?: LocalizedDemoText
}

export const demoConnectionNodes: DemoConnectionNode[] = [
  {
    id: "node-sim-224",
    address: "10.227.5.224",
    label: { en: "Simulation host sz01", zhCN: "仿真环境 sz01" },
    group: { en: "Bioinformatics analysis", zhCN: "生信分析" },
    status: "online",
    tags: ["Phoenix", "FASTQ", "Logs"],
    ssh: {
      port: 22,
      username: "bioflow",
      auth: "key",
    },
    skills: ["phoenix"],
    prompts: [
      {
        en: "Phoenix outputs are usually under /mnt/nas/phoenix-output. Check logs/current_step.log first when a task fails.",
        zhCN: "Phoenix 输出目录通常在 /mnt/nas/phoenix-output。任务失败时优先查看 logs/current_step.log。",
      },
    ],
    paths: ["/mnt/nas/pipelines", "/mnt/nas/phoenix-output", "/mnt/nas/fastq"],
    apis: [{ name: "Phoenix API", baseUrl: "http://10.227.5.224:8080" }],
    environmentVariables: ["PHOENIX_HOME=/opt/phoenix", "BIOFLOW_DATA=/mnt/nas"],
    startupSnippet: "source /etc/profile\nmodule load nextflow",
  },
  {
    id: "node-test-231",
    address: "10.227.5.231",
    label: { en: "Test host sz03", zhCN: "测试环境 sz03" },
    group: { en: "Bioinformatics analysis", zhCN: "生信分析" },
    status: "online",
    tags: ["Phoenix", "Harbor", "Omics One"],
    ssh: {
      port: 22,
      username: "bioflow",
      auth: "certificate",
    },
    skills: ["phoenix", "harbor"],
    prompts: [
      {
        en: "FASTQ inputs are mounted at /mnt/nas/fastq. Container images and run artifacts are grouped by project name.",
        zhCN: "FASTQ 输入挂载在 /mnt/nas/fastq。镜像和运行结果按项目名归档。",
      },
    ],
    paths: ["/mnt/nas/fastq", "/mnt/nas/results"],
    apis: [{ name: "Harbor", baseUrl: "https://10.227.5.231:8443" }],
    environmentVariables: ["BIOFLOW_DATA=/mnt/nas", "CONTAINER_REGISTRY=10.227.5.231:8443"],
    startupSnippet: "source /etc/profile\nmodule load singularity",
  },
  {
    id: "node-uat-245",
    address: "10.227.5.245",
    label: { en: "Acceptance host sz02", zhCN: "验收环境 sz02" },
    group: { en: "Acceptance", zhCN: "验收" },
    status: "offline",
    tags: ["ODP", "Results"],
    ssh: {
      port: 22,
      username: "odp-user",
      auth: "password",
    },
    skills: ["odp"],
    prompts: [
      {
        en: "ODP outputs are staged under /mnt/nas/odp-output. Confirm the latest delivery folder before reading results.",
        zhCN: "ODP 输出会暂存在 /mnt/nas/odp-output。读取结果前先确认最新交付目录。",
      },
    ],
    paths: ["/mnt/nas/odp-output"],
    apis: [],
    environmentVariables: ["ODP_HOME=/opt/odp"],
    startupSnippet: "source /etc/profile",
    issue: {
      en: "The last connection test failed.",
      zhCN: "最近一次连接测试失败。",
    },
  },
]

export const demoConnectionTagStyles: Record<string, string> = {
  Phoenix: "border-orange-400/25 bg-orange-500/10 text-orange-700 dark:text-orange-300",
  ODP: "border-sky-400/25 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  Harbor: "border-blue-400/25 bg-blue-500/10 text-blue-700 dark:text-blue-300",
  "Omics One": "border-fuchsia-400/25 bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300",
  FASTQ: "border-emerald-400/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  Logs: "border-amber-400/25 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  Results: "border-violet-400/25 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  WDL: "border-purple-400/25 bg-purple-500/10 text-purple-700 dark:text-purple-300",
  Nextflow: "border-teal-400/25 bg-teal-500/10 text-teal-700 dark:text-teal-300",
  Slurm: "border-lime-400/25 bg-lime-500/10 text-lime-700 dark:text-lime-300",
  GPU: "border-rose-400/25 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  Test: "border-slate-400/25 bg-slate-500/10 text-slate-700 dark:text-slate-300",
  UAT: "border-cyan-400/25 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
}

export const defaultDemoConnectionTags = [
  "Phoenix",
  "ODP",
  "Harbor",
  "Omics One",
  "FASTQ",
  "WDL",
  "Nextflow",
  "Slurm",
  "GPU",
  "Test",
  "UAT",
]

export function getDemoConnectionText(text: LocalizedDemoText, locale: string) {
  return locale.startsWith("zh") ? text.zhCN : text.en
}

export function createLocalizedDemoText(value: string): LocalizedDemoText {
  return { en: value, zhCN: value }
}
