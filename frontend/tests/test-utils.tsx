import type { ReactElement, ReactNode } from "react"
import { render, type RenderOptions } from "@testing-library/react"

type TestProvidersProps = {
  children: ReactNode
}

function TestProviders({ children }: TestProvidersProps) {
  return <>{children}</>
}

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  return render(ui, {
    wrapper: TestProviders,
    ...options,
  })
}

export * from "@testing-library/react"
