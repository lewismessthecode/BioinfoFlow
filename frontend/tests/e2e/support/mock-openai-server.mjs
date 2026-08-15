import http from "node:http"
import { pathToFileURL } from "node:url"

const port = Number(process.env.PLAYWRIGHT_MODEL_PORT || 9100)
const host = process.env.PLAYWRIGHT_MODEL_HOST || "127.0.0.1"

const advertisedModels = [
  "e2e-workflow-run",
  "e2e-reasoning-stream",
  "e2e-plan",
  "e2e-parallel-tools",
  "e2e-serial-tools",
  "e2e-approval",
  "e2e-ask-user",
  "e2e-stop",
  "e2e-recovery",
]

export function createMockOpenAIServer() {
  return http.createServer(async (request, response) => {
    if (request.method === "GET" && request.url === "/v1/models") {
      writeJson(response, 200, {
        object: "list",
        data: advertisedModels.map((id) => ({ id, object: "model" })),
      })
      return
    }

    if (request.method === "POST" && request.url === "/v1/chat/completions") {
      let body
      try {
        body = JSON.parse(await readBody(request))
      } catch {
        writeJson(response, 400, {
          error: { message: "invalid JSON request" },
        })
        return
      }

      response.writeHead(200, {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
        connection: "keep-alive",
      })
      await streamCompletion(response, body)
      return
    }

    writeJson(response, 404, { error: { message: "not found" } })
  })
}

if (isMainModule()) {
  const server = createMockOpenAIServer()
  server.listen(port, host)

  const close = () => server.close(() => process.exit(0))
  process.on("SIGINT", close)
  process.on("SIGTERM", close)
}

async function streamCompletion(response, body) {
  const model = String(body?.model || "")
  const scenarioModel = model.split("/").at(-1) || model
  const messages = Array.isArray(body?.messages) ? body.messages : []
  const hasToolResult = messages.some((message) => message?.role === "tool")

  if (scenarioModel.startsWith("e2e-reasoning-stream")) {
    await streamText(response, model, {
      reasoning: "Checking the keyless request.",
      chunks: ["Keyless model ", "stream completed."],
      delayMilliseconds: 1_000,
    })
    return
  }

  if (scenarioModel.startsWith("e2e-plan")) {
    if (!hasToolResult) {
      streamToolCalls(response, model, [
        {
          id: "call-e2e-plan",
          name: "update_plan",
          arguments: {
            explanation: "Keyless execution plan",
            plan: [
              { step: "Inspect the request", status: "completed" },
              { step: "Summarize the result", status: "in_progress" },
            ],
          },
        },
      ])
      return
    }
    await streamText(response, model, {
      chunks: ["The keyless plan ", "is ready."],
    })
    return
  }

  if (scenarioModel.startsWith("e2e-parallel-tools")) {
    if (!hasToolResult) {
      streamToolCalls(response, model, [
        {
          id: "call-e2e-parallel-alpha",
          name: "write",
          arguments: { path: "e2e-alpha.txt", content: "alpha" },
        },
        {
          id: "call-e2e-parallel-beta",
          name: "write",
          arguments: { path: "e2e-beta.txt", content: "beta" },
        },
      ])
      return
    }
    await streamText(response, model, {
      chunks: ["Both keyless tools ", "completed."],
    })
    return
  }

  if (scenarioModel.startsWith("e2e-serial-tools")) {
    if (!hasToolResult) {
      streamToolCalls(response, model, [
        {
          id: "call-e2e-serial-alpha",
          name: "bash",
          arguments: { command: "pwd" },
        },
        {
          id: "call-e2e-serial-beta",
          name: "bash",
          arguments: { command: "ls -la" },
        },
      ])
      return
    }
    await streamText(response, model, {
      chunks: ["Both serial tools ", "completed."],
    })
    return
  }

  if (scenarioModel.startsWith("e2e-approval")) {
    if (!hasToolResult) {
      streamToolCalls(response, model, [
        {
          id: "call-e2e-approval",
          name: "bash",
          arguments: { command: "touch e2e-approved.txt" },
        },
      ])
      return
    }
    await streamText(response, model, {
      chunks: ["Approval scenario ", "completed."],
    })
    return
  }

  if (scenarioModel.startsWith("e2e-ask-user")) {
    if (!hasToolResult) {
      streamToolCalls(response, model, [
        {
          id: "call-e2e-ask-user",
          name: "ask_user",
          arguments: {
            questions: [
              {
                header: "Continue",
                question: "Should the keyless run continue?",
                options: [
                  { label: "Continue", description: "Finish the Agent run." },
                  { label: "Stop", description: "Do not continue the run." },
                ],
              },
            ],
          },
        },
      ])
      return
    }
    await streamText(response, model, {
      chunks: ["The keyless answer ", "was received."],
    })
    return
  }

  if (scenarioModel.startsWith("e2e-stop")) {
    if (!hasToolResult) {
      streamToolCalls(response, model, [
        {
          id: "call-e2e-stop",
          name: "bash",
          arguments: { command: "sleep 30" },
        },
      ])
      return
    }
    await streamText(response, model, {
      chunks: ["Stop scenario ", "completed."],
    })
    return
  }

  if (scenarioModel.startsWith("e2e-recovery")) {
    if (!hasToolResult) {
      streamToolCalls(response, model, [
        {
          id: "call-e2e-recovery",
          name: "bash",
          arguments: { command: "sleep 30" },
        },
      ])
      return
    }
    await streamText(response, model, {
      chunks: ["Recovered after ", "inspection."],
    })
    return
  }

  if (scenarioModel.startsWith("e2e-workflow-run")) {
    if (hasToolResult) {
      await streamText(response, model, {
        chunks: toolResultSucceeded(messages)
          ? ["Workflow submitted ", "through bif."]
          : ["Workflow submission ", "failed."],
      })
      return
    }
    const workflowId = workflowIdFromMessages(messages)
    streamToolCalls(response, model, [
      {
        id: "call-e2e-workflow-run",
        name: "bash",
        arguments: {
          command: `bif --output json run submit --workflow ${workflowId} --values '{}'`,
          description: "Submit the workflow through bif",
        },
      },
    ])
    return
  }

  await streamText(response, model || "unknown", {
    chunks: ["Unknown keyless model scenario."],
  })
}

function workflowIdFromMessages(messages) {
  const prompt = messages
    .filter((message) => message?.role === "user")
    .map((message) =>
      typeof message.content === "string"
        ? message.content
        : JSON.stringify(message.content ?? ""),
    )
    .join("\n")
  const match = prompt.match(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i)
  return match?.[0] ?? "00000000-0000-0000-0000-000000000000"
}

function toolResultSucceeded(messages) {
  return messages.some((message) => {
    if (message?.role !== "tool") return false
    const content =
      typeof message.content === "string"
        ? message.content
        : JSON.stringify(message.content ?? "")
    return /["']?exit_code["']?\s*[:=]\s*0\b/.test(content)
  })
}

async function streamText(
  response,
  model,
  { reasoning, chunks, delayMilliseconds = 100 },
) {
  if (reasoning) {
    writeChunk(response, model, {
      role: "assistant",
      reasoning_content: reasoning,
    })
    await delay(delayMilliseconds)
  }
  for (const content of chunks) {
    writeChunk(response, model, { role: "assistant", content })
    await delay(delayMilliseconds)
  }
  writeChunk(response, model, {}, "stop")
  finishStream(response)
}

function streamToolCalls(response, model, calls) {
  writeChunk(response, model, {
    role: "assistant",
    tool_calls: calls.map((call, index) => ({
      index,
      id: call.id,
      type: "function",
      function: {
        name: call.name,
        arguments: JSON.stringify(call.arguments),
      },
    })),
  })
  writeChunk(response, model, {}, "tool_calls")
  finishStream(response)
}

function writeChunk(response, model, delta, finishReason = null) {
  if (response.destroyed || response.writableEnded) return
  response.write(
    `data: ${JSON.stringify({
      id: `chatcmpl-${model}`,
      object: "chat.completion.chunk",
      created: 0,
      model,
      choices: [{ index: 0, delta, finish_reason: finishReason }],
    })}\n\n`,
  )
}

function finishStream(response) {
  if (response.destroyed || response.writableEnded) return
  response.end("data: [DONE]\n\n")
}

function writeJson(response, status, body) {
  response.writeHead(status, { "content-type": "application/json" })
  response.end(JSON.stringify(body))
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    let body = ""
    request.setEncoding("utf8")
    request.on("data", (chunk) => {
      body += chunk
    })
    request.on("end", () => resolve(body))
    request.on("error", reject)
  })
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

function isMainModule() {
  return (
    Boolean(process.argv[1]) &&
    pathToFileURL(process.argv[1]).href === import.meta.url
  )
}
