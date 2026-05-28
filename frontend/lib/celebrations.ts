"use client"

export type CelebrationMilestone =
  | "provider-key"
  | "first-project"
  | "first-workflow"

type ReadinessSummary = {
  provider_key_configured?: boolean
  projects?: number
  workflows?: number
}

const STORAGE_PREFIX = "bioinfoflow:celebrated:"
const COLORS = ["#15b8a6", "#f4b740", "#ec5b56", "#5c8df6", "#f7f3e8"]

export function readinessMilestonesFromSummary(
  summary?: ReadinessSummary | null,
): CelebrationMilestone[] {
  if (!summary) {
    return []
  }

  const milestones: CelebrationMilestone[] = []
  if (summary.provider_key_configured) {
    milestones.push("provider-key")
  }
  if ((summary.projects ?? 0) > 0) {
    milestones.push("first-project")
  }
  if ((summary.workflows ?? 0) > 0) {
    milestones.push("first-workflow")
  }
  return milestones
}

export function celebrateOnce(milestone: CelebrationMilestone) {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return
  }

  const key = `${STORAGE_PREFIX}${milestone}`
  if (window.localStorage.getItem(key) === "1") {
    return
  }
  window.localStorage.setItem(key, "1")

  if (
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  ) {
    return
  }

  launchCanvasConfetti()
}

function launchCanvasConfetti() {
  const canvas = document.createElement("canvas")
  canvas.setAttribute("aria-hidden", "true")
  canvas.style.position = "fixed"
  canvas.style.inset = "0"
  canvas.style.width = "100vw"
  canvas.style.height = "100vh"
  canvas.style.pointerEvents = "none"
  canvas.style.zIndex = "2147483647"
  document.body.appendChild(canvas)

  const context = canvas.getContext("2d")
  if (!context) {
    canvas.remove()
    return
  }

  const scale = window.devicePixelRatio || 1
  canvas.width = Math.floor(window.innerWidth * scale)
  canvas.height = Math.floor(window.innerHeight * scale)
  context.scale(scale, scale)

  const particles = Array.from({ length: 64 }, (_, index) => ({
    x: window.innerWidth * (0.38 + Math.random() * 0.24),
    y: window.innerHeight * 0.22,
    vx: (Math.random() - 0.5) * 7,
    vy: -6 - Math.random() * 6,
    gravity: 0.28 + Math.random() * 0.08,
    size: 5 + Math.random() * 5,
    rotation: Math.random() * Math.PI,
    color: COLORS[index % COLORS.length],
  }))

  let frame = 0
  const maxFrames = 80

  function draw() {
    if (typeof window === "undefined") {
      canvas.remove()
      return
    }

    frame += 1
    context.clearRect(0, 0, window.innerWidth, window.innerHeight)

    for (const particle of particles) {
      particle.x += particle.vx
      particle.y += particle.vy
      particle.vy += particle.gravity
      particle.rotation += 0.16

      context.save()
      context.translate(particle.x, particle.y)
      context.rotate(particle.rotation)
      context.fillStyle = particle.color
      context.fillRect(
        -particle.size / 2,
        -particle.size / 2,
        particle.size,
        particle.size * 0.62,
      )
      context.restore()
    }

    if (frame < maxFrames) {
      requestAnimationFrame(draw)
    } else {
      canvas.remove()
    }
  }

  requestAnimationFrame(draw)
}
