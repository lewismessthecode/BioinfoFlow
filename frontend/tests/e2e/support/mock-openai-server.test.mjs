import assert from "node:assert/strict"
import { after, before, test } from "node:test"

import { createMockOpenAIServer } from "./mock-openai-server.mjs"

const server = createMockOpenAIServer()
let baseUrl

before(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve))
  const address = server.address()
  assert(address && typeof address === "object")
  baseUrl = `http://127.0.0.1:${address.port}/v1`
})

after(async () => {
  await new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()))
  })
})

test("advertises the deterministic keyless scenarios", async () => {
  const response = await fetch(`${baseUrl}/models`)
  assert.equal(response.status, 200)
  const payload = await response.json()
  assert.deepEqual(
    payload.data.map((item) => item.id),
    [
      "e2e-runs-submit",
      "e2e-reasoning-stream",
      "e2e-plan",
      "e2e-parallel-tools",
      "e2e-serial-tools",
      "e2e-approval",
      "e2e-ask-user",
      "e2e-stop",
      "e2e-recovery",
    ],
  )
})

test("streams reasoning and final text without an external provider", async () => {
  const events = await completion("openai/e2e-reasoning-stream-selfcheck")
  assert.equal(
    events
      .map((event) => event.choices[0].delta.reasoning_content || "")
      .join(""),
    "Checking the keyless request.",
  )
  assert.equal(
    events.map((event) => event.choices[0].delta.content || "").join(""),
    "Keyless model stream completed.",
  )
  assert.equal(events.at(-1).choices[0].finish_reason, "stop")
})

test("derives tool phases from request history instead of global state", async () => {
  const first = await completion("e2e-parallel-tools-selfcheck")
  const toolCalls = first[0].choices[0].delta.tool_calls
  assert.deepEqual(
    toolCalls.map((call) => call.function.name),
    ["write", "write"],
  )

  const second = await completion("e2e-parallel-tools-selfcheck", [
    { role: "user", content: "Inspect both values." },
    { role: "tool", tool_call_id: toolCalls[0].id, content: "alpha" },
    { role: "tool", tool_call_id: toolCalls[1].id, content: "beta" },
  ])
  assert.equal(
    second.map((event) => event.choices[0].delta.content || "").join(""),
    "Both keyless tools completed.",
  )
})

test("emits valid approval and ask-user tool calls", async () => {
  const approval = await completion("e2e-approval-selfcheck")
  assert.equal(approval[0].choices[0].delta.tool_calls[0].function.name, "bash")
  assert.deepEqual(
    JSON.parse(approval[0].choices[0].delta.tool_calls[0].function.arguments),
    { command: "touch e2e-approved.txt" },
  )

  const askUser = await completion("e2e-ask-user-selfcheck")
  assert.equal(
    askUser[0].choices[0].delta.tool_calls[0].function.name,
    "ask_user",
  )
  const argumentsPayload = JSON.parse(
    askUser[0].choices[0].delta.tool_calls[0].function.arguments,
  )
  assert.equal(argumentsPayload.questions.length, 1)
  assert.equal(argumentsPayload.questions[0].options.length, 2)
})

test("emits plan, serial, stop, and recovery scenarios", async () => {
  const plan = await completion("e2e-plan-selfcheck")
  assert.equal(
    plan[0].choices[0].delta.tool_calls[0].function.name,
    "update_plan",
  )

  const serial = await completion("e2e-serial-tools-selfcheck")
  assert.deepEqual(
    serial[0].choices[0].delta.tool_calls.map((call) => call.function.name),
    ["bash", "bash"],
  )

  for (const scenario of ["stop", "recovery"]) {
    const events = await completion(`e2e-${scenario}-selfcheck`)
    const call = events[0].choices[0].delta.tool_calls[0]
    assert.equal(call.function.name, "bash")
    assert.deepEqual(JSON.parse(call.function.arguments), {
      command: "sleep 30",
    })
  }
})

async function completion(
  model,
  messages = [{ role: "user", content: "test" }],
) {
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ model, messages, stream: true }),
  })
  assert.equal(response.status, 200)
  const body = await response.text()
  return body
    .split("\n")
    .filter((line) => line.startsWith("data: ") && line !== "data: [DONE]")
    .map((line) => JSON.parse(line.slice("data: ".length)))
}
