"use client"

import { ArrowDown } from "@/lib/icons"
import { motion, AnimatePresence, useReducedMotion } from "framer-motion"
import { Button } from "@/components/ui/button"

interface ScrollToBottomProps {
  visible: boolean
  onClick: () => void
  ariaLabel?: string
}

export function ScrollToBottom({
  visible,
  onClick,
  ariaLabel = "Scroll to bottom",
}: ScrollToBottomProps) {
  const prefersReducedMotion = useReducedMotion()

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="flex justify-center py-1"
          initial={prefersReducedMotion ? {} : { opacity: 0, y: 10, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={prefersReducedMotion ? {} : { opacity: 0, y: 10, scale: 0.9 }}
          transition={{ type: "spring", stiffness: 300, damping: 25 }}
        >
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9 rounded-full shadow-md bg-background/95 backdrop-blur-sm border-border/60 hover:bg-accent/50 relative"
            onClick={onClick}
            aria-label={ariaLabel}
          >
            <ArrowDown className="h-4 w-4" />
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
