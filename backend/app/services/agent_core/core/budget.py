from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IterationBudget:
    max_iterations: int = 6
    used_iterations: int = 0

    def consume(self) -> bool:
        if self.used_iterations >= self.max_iterations:
            return False
        self.used_iterations += 1
        return True

    def snapshot(self) -> dict[str, int]:
        return {
            "max_iterations": self.max_iterations,
            "used_iterations": self.used_iterations,
            "remaining_iterations": max(self.max_iterations - self.used_iterations, 0),
        }
