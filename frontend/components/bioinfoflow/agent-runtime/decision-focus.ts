export type DecisionFocusDestination = "next" | "composer"

const PENDING_CARD_SELECTOR = '[data-agent-decision-card="pending"]'
const COMPOSER_FOCUS_SELECTOR = [
  '[data-testid="composer-decision-jump"]',
  '[data-testid="agent-composer-control"]',
  '[data-testid="agent-composer"] textarea',
].join(",")
const DECISION_FOCUS_TARGET = [
  "button:not(:disabled)",
  "input:not(:disabled)",
  "textarea:not(:disabled)",
  "select:not(:disabled)",
  "[href]",
  '[tabindex]:not([tabindex="-1"])',
].join(",")

export function jumpToDecisionTarget(targetId: string) {
  const target = document.getElementById(targetId)
  if (!target) return
  const reducedMotion = window.matchMedia?.(
    "(prefers-reduced-motion: reduce)",
  ).matches
  target.scrollIntoView({
    block: "center",
    behavior: reducedMotion ? "auto" : "smooth",
  })
  const focusTarget =
    target.querySelector<HTMLElement>(DECISION_FOCUS_TARGET) ?? target
  focusTarget.focus({ preventScroll: true })
}

export function scheduleDecisionFocusHandoff(
  actionId: string,
  onHandoff: (destination: DecisionFocusDestination) => void,
) {
  window.requestAnimationFrame(() => {
    const nextCard = Array.from(
      document.querySelectorAll<HTMLElement>(PENDING_CARD_SELECTOR),
    ).find((card) => card.dataset.actionId !== actionId)
    if (nextCard) {
      nextCard.focus()
      onHandoff("next")
      return
    }

    const composerControl = document.querySelector<HTMLElement>(
      COMPOSER_FOCUS_SELECTOR,
    )
    if (!composerControl) return
    composerControl.focus()
    onHandoff("composer")
  })
}
