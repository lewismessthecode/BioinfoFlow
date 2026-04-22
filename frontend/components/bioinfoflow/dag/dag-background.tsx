/**
 * DAG Background Component
 *
 * Renders the background layer for DAG visualization, including:
 * - Radial gradient layer
 * - Grid layer
 * - Glow layer
 */

interface DagBackgroundProps {
  className?: string
}

export function DagBackground({ className }: DagBackgroundProps) {
  return (
    <div className={className}>
      {/* Radial gradient layer - soft glow radiating from center */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--dag-glow),_transparent_70%)] blur-sm" />

      {/* Grid layer - interwoven horizontal and vertical grid lines */}
      <div className="absolute inset-0 bg-[linear-gradient(var(--dag-grid)_1px,_transparent_1px),linear-gradient(90deg,_var(--dag-grid)_1px,_transparent_1px)] bg-[size:40px_40px] opacity-40 [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_70%)]" />

      {/* Glow layer - additional light effect in the upper right corner */}
      <div className="absolute -top-20 -right-20 h-56 w-56 rounded-full bg-[var(--dag-corner-glow)] blur-[60px]" />
    </div>
  )
}
