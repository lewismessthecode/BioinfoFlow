export type DecisionFocusDestination = "next" | "composer"

const PENDING_CARD_SELECTOR = '[data-agent-decision-card="pending"]'
const COMPOSER_FOCUS_SELECTOR = [
  '[data-testid="composer-decision-jump"]',
  '[data-testid="agent-composer-control"]',
  '[data-testid="agent-composer"] textarea',
].join(",")

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
