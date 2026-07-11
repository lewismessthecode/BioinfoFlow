export async function withMinimumDuration<T>(
  work: Promise<T>,
  minimumDurationMs = 500,
): Promise<T> {
  const minimumDuration = new Promise<void>((resolve) => {
    setTimeout(resolve, minimumDurationMs)
  })
  const [result] = await Promise.all([work, minimumDuration])
  return result
}
