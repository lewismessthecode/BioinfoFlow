"use client"

import { motion, useReducedMotion } from "framer-motion"

export function TypingIndicator() {
  const prefersReducedMotion = useReducedMotion()

  return (
    <motion.div
      className="flex items-start gap-3 mx-auto max-w-3xl px-4 py-3"
      initial={prefersReducedMotion ? {} : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <div className="flex items-center gap-1.5 rounded-2xl bg-secondary/50 px-4 py-3">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="block h-2 w-2 rounded-full bg-muted-foreground/60"
            animate={
              prefersReducedMotion
                ? {}
                : {
                    y: [0, -4, 0],
                    opacity: [0.4, 1, 0.4],
                  }
            }
            transition={{
              duration: 0.8,
              repeat: Infinity,
              delay: i * 0.15,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>
    </motion.div>
  )
}
