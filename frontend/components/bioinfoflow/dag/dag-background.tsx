interface DagBackgroundProps {
  className?: string
}

export function DagBackground({ className }: DagBackgroundProps) {
  return (
    <div className={className}>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--dag-glow),_transparent_70%)] blur-sm" />

      <div className="absolute -top-20 -right-20 h-56 w-56 rounded-full bg-[var(--dag-corner-glow)] blur-[60px]" />
    </div>
  )
}
