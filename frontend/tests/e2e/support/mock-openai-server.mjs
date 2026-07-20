import http from "node:http"

const port = Number(process.env.PLAYWRIGHT_MODEL_PORT || 9100)
const model = "e2e-runs-submit"

const server = http.createServer((request, response) => {
  if (request.method === "GET" && request.url === "/v1/models") {
    response.writeHead(200, { "content-type": "application/json" })
    response.end(JSON.stringify({ object: "list", data: [{ id: model, object: "model" }] }))
    return
  }

  if (request.method === "POST" && request.url === "/v1/chat/completions") {
    response.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    })
    const chunk = {
      id: "chatcmpl-e2e-runs-submit",
      object: "chat.completion.chunk",
      created: 0,
      model,
      choices: [
        {
          index: 0,
          delta: {
            role: "assistant",
            tool_calls: [
              {
                index: 0,
                id: "call-e2e-runs-submit",
                type: "function",
                function: {
                  name: "runs__submit",
                  arguments: JSON.stringify({
                    project_id: "e2e-project",
                    workflow_id: "e2e-workflow",
                    values: {},
                  }),
                },
              },
            ],
          },
          finish_reason: null,
        },
      ],
    }
    response.write(`data: ${JSON.stringify(chunk)}\n\n`)
    response.write(
      `data: ${JSON.stringify({
        ...chunk,
        choices: [{ index: 0, delta: {}, finish_reason: "tool_calls" }],
      })}\n\n`,
    )
    response.end("data: [DONE]\n\n")
    return
  }

  response.writeHead(404, { "content-type": "application/json" })
  response.end(JSON.stringify({ error: "not found" }))
})

server.listen(port, "127.0.0.1")

const close = () => server.close(() => process.exit(0))
process.on("SIGINT", close)
process.on("SIGTERM", close)
