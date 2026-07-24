"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { getSpeechStatus, transcribeSpeech } from "@/lib/speech"

export type VoiceDictationState = "idle" | "recording" | "transcribing" | "error"

type UseVoiceDictationOptions = {
  onTranscript: (text: string) => void
  onError?: (error: unknown) => void
  maxDurationSeconds?: number
}

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
]

export function useVoiceDictation({
  onTranscript,
  onError,
  maxDurationSeconds = 120,
}: UseVoiceDictationOptions) {
  const browserSupported =
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof MediaRecorder !== "undefined"
  const [serviceAvailable, setServiceAvailable] = useState(false)
  const [state, setState] = useState<VoiceDictationState>("idle")
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [level, setLevel] = useState(0)
  const [error, setError] = useState<unknown>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const discardRef = useRef(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const animationRef = useRef<number | null>(null)
  const mountedRef = useRef(true)
  const startPendingRef = useRef(false)
  const sessionRef = useRef(0)

  const clearTimers = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    intervalRef.current = null
    timeoutRef.current = null
  }, [])

  const releaseMedia = useCallback(() => {
    clearTimers()
    if (animationRef.current !== null) cancelAnimationFrame(animationRef.current)
    animationRef.current = null
    void audioContextRef.current?.close()
    audioContextRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    recorderRef.current = null
    setLevel(0)
  }, [clearTimers])

  useEffect(() => {
    let active = true
    if (!browserSupported) return
    void getSpeechStatus()
      .then((status) => {
        if (active) setServiceAvailable(status.available)
      })
      .catch(() => {
        if (active) setServiceAvailable(false)
      })
    return () => {
      active = false
    }
  }, [browserSupported])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      startPendingRef.current = false
      sessionRef.current += 1
    }
  }, [])

  useEffect(
    () => () => {
      discardRef.current = true
      const recorder = recorderRef.current
      if (recorder?.state === "recording") {
        recorder.ondataavailable = null
        recorder.onstop = null
        recorder.stop()
      }
      releaseMedia()
    },
    [releaseMedia],
  )

  const beginLevelSampling = useCallback((stream: MediaStream) => {
    if (typeof AudioContext === "undefined") return
    const context = new AudioContext()
    const source = context.createMediaStreamSource(stream)
    const analyser = context.createAnalyser()
    analyser.fftSize = 256
    source.connect(analyser)
    const samples = new Uint8Array(analyser.fftSize)
    audioContextRef.current = context
    const sample = () => {
      analyser.getByteTimeDomainData(samples)
      let squareSum = 0
      for (const value of samples) {
        const centered = (value - 128) / 128
        squareSum += centered * centered
      }
      setLevel(Math.min(1, Math.sqrt(squareSum / samples.length) * 4))
      animationRef.current = requestAnimationFrame(sample)
    }
    sample()
  }, [])

  const finishRecording = useCallback(async () => {
    const mimeType = recorderRef.current?.mimeType || "audio/webm"
    const shouldDiscard = discardRef.current
    const audio = new Blob(chunksRef.current, { type: mimeType })
    chunksRef.current = []
    releaseMedia()
    if (shouldDiscard) {
      discardRef.current = false
      setElapsedSeconds(0)
      setState("idle")
      return
    }
    setState("transcribing")
    const session = sessionRef.current
    try {
      const transcript = await transcribeSpeech(audio)
      if (!mountedRef.current || session !== sessionRef.current) return
      onTranscript(transcript.text)
      setError(null)
      setElapsedSeconds(0)
      setState("idle")
    } catch (caught) {
      if (!mountedRef.current || session !== sessionRef.current) return
      setError(caught)
      setState("error")
      onError?.(caught)
    }
  }, [onError, onTranscript, releaseMedia])

  const stop = useCallback(() => {
    const recorder = recorderRef.current
    if (recorder?.state === "recording") recorder.stop()
  }, [])

  const start = useCallback(async () => {
    if (
      !browserSupported ||
      startPendingRef.current ||
      state === "recording" ||
      state === "transcribing"
    ) return
    startPendingRef.current = true
    const session = ++sessionRef.current
    setError(null)
    discardRef.current = false
    chunksRef.current = []
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!mountedRef.current || session !== sessionRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      const mimeType = MIME_CANDIDATES.find((candidate) =>
        MediaRecorder.isTypeSupported(candidate),
      )
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)
      streamRef.current = stream
      recorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data)
      }
      recorder.onstop = () => void finishRecording()
      recorder.start()
      beginLevelSampling(stream)
      setElapsedSeconds(0)
      setState("recording")
      intervalRef.current = setInterval(
        () => setElapsedSeconds((current) => Math.min(maxDurationSeconds, current + 1)),
        1000,
      )
      timeoutRef.current = setTimeout(stop, maxDurationSeconds * 1000)
    } catch (caught) {
      if (!mountedRef.current || session !== sessionRef.current) return
      releaseMedia()
      setError(caught)
      setState("error")
      onError?.(caught)
    } finally {
      if (session === sessionRef.current) startPendingRef.current = false
    }
  }, [
    beginLevelSampling,
    browserSupported,
    finishRecording,
    maxDurationSeconds,
    onError,
    releaseMedia,
    state,
    stop,
  ])

  const cancel = useCallback(() => {
    discardRef.current = true
    const recorder = recorderRef.current
    if (recorder?.state === "recording") recorder.stop()
    else {
      releaseMedia()
      setState("idle")
    }
  }, [releaseMedia])

  const resetError = useCallback(() => {
    setError(null)
    setState("idle")
  }, [])

  return {
    available: browserSupported && serviceAvailable,
    browserSupported,
    state,
    elapsedSeconds,
    level,
    error,
    start,
    stop,
    cancel,
    resetError,
  }
}
