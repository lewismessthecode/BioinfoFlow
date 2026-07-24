import { apiRequest } from "@/lib/api"

export type SpeechStatus = {
  configured: boolean
  available: boolean
  provider: string | null
  model: string | null
  language: string
  message: string | null
}

export type SpeechTranscript = {
  text: string
  language?: string | null
}

export async function getSpeechStatus(): Promise<SpeechStatus> {
  const response = await apiRequest<SpeechStatus>("/speech/status")
  return response.data
}

export async function transcribeSpeech(audio: Blob): Promise<SpeechTranscript> {
  const form = new FormData()
  const extension = audio.type.includes("ogg") ? "ogg" : audio.type.includes("mp4") ? "m4a" : "webm"
  form.set("file", audio, `recording.${extension}`)
  const response = await apiRequest<SpeechTranscript>("/speech/transcriptions", {
    method: "POST",
    body: form,
  })
  return response.data
}
