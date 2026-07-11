export async function withMinimumDuration<T>(
  work: Promise<T>,
  minimumDurationMs = 500,
): Promise<T> {
  const minimumDuration = new Promise<void>((resolve) => {
    setTimeout(resolve, minimumDurationMs)
  })
  const [result] = await Promise.allSettled([work, minimumDuration])

  if (result.status === "rejected") {
    throw result.reason
  }

  return result.value
}
