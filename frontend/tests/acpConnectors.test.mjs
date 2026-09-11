import assert from "node:assert/strict"
import path from "node:path"
import { after, before, test } from "node:test"
import { fileURLToPath } from "node:url"
import { chromium, expect } from "@playwright/test"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { createServer } from "vite"

const root = fileURLToPath(new URL("..", import.meta.url))
let server, browser, baseUrl, html
before(async () => {
  server = await createServer({ configFile: false, root, resolve: { alias: { "@": path.join(root, "src") } }, plugins: [react(), tailwindcss()], server: { host: "127.0.0.1", port: 0 }, logLevel: "error" })
  await server.listen()
  baseUrl = `http://127.0.0.1:${server.httpServer.address().port}`
  html = await server.transformIndexHtml("/", '<html><body><div id="root"></div><script type="module" src="/tests/fixtures/acpHarness.tsx"></script></body></html>')
  browser = await chromium.launch({ headless: true })
})
after(async () => { await browser?.close(); await server?.close() })

async function openCard(t, { count = 1, fail = false } = {}) {
  const page = await browser.newPage()
  t.after(() => page.close())
  page.setDefaultTimeout(10000)
  const errors = [], writes = []
  page.on("pageerror", (error) => errors.push(error.message))
  t.after(() => assert.deepEqual(errors, []))
  const connectors = Array.from({ length: count }, (_, i) => ({ id: `connector-${i + 1}`, agent_id: "agent-1", owner_id: "owner-1", name: `Editor ${i + 1}`, mode: "conversation", is_active: true, max_connections: 10, acp_server_url: `wss://example.test/acp/connector-${i + 1}`, created_at: "2026-09-11T12:00:00Z", updated_at: "2026-09-11T12:00:00Z" }))
  const tokens = []
  await page.route(`${baseUrl}/`, (route) => route.fulfill({ contentType: "text/html", body: html }))
  await page.route("**/api/**", async (route) => {
    const request = route.request(), url = new URL(request.url()).pathname
    if (fail) return route.fulfill({ status: 503, json: { detail: "Server unavailable" } })
    if (request.method() !== "GET") writes.push({ method: request.method(), url, body: request.postDataJSON() })
    let json
    if (url.endsWith("/tokens") && request.method() === "POST") {
      const token = { id: "token-1", connector_id: "connector-1", prefix: "acp_example", label: request.postDataJSON().label, revoked: false, expires_at: "2099-01-01T00:00:00Z", created_at: "2026-09-11T12:00:00Z", last_used_at: null }
      tokens.push(token)
      json = { ...token, token: "acp_ONE_TIME_SECRET" }
    } else if (url.endsWith("/tokens")) json = { data: tokens, count: tokens.length }
    else if (url.endsWith("/revoke")) { tokens[0].revoked = true; json = tokens[0] }
    else if (request.method() === "PUT") { Object.assign(connectors[0], request.postDataJSON()); json = connectors[0] }
    else if (url.endsWith("/acp-connectors")) json = { data: connectors, count: connectors.length }
    else { errors.push(`Unexpected ${request.method()} ${url}`); return route.abort() }
    await route.fulfill({ json })
  })
  await page.goto(baseUrl)
  return { page, writes, connectors }
}

test("editing only a name preserves settings changed by another client", async (t) => {
  const { page, writes, connectors } = await openCard(t)
  await page.getByRole("button", { name: "Actions for ACP connector Editor 1" }).click()
  await page.getByRole("menuitem", { name: "Edit connector" }).click()
  connectors[0].mode = "building"
  connectors[0].max_connections = 3
  await page.getByLabel("Name", { exact: true }).fill("Renamed editor")
  await page.getByRole("button", { name: "Save changes" }).click()
  await expect(page.getByRole("dialog")).toHaveCount(0)
  assert.deepEqual(writes[0].body, { name: "Renamed editor" })
  assert.equal(connectors[0].mode, "building")
  assert.equal(connectors[0].max_connections, 3)
})

test("one-time token is erased after Done and revoke requires confirmation", async (t) => {
  const { page, writes } = await openCard(t)
  await page.getByRole("button", { name: "Actions for ACP connector Editor 1" }).click()
  await page.getByRole("menuitem", { name: "Access tokens" }).click()
  await page.getByRole("button", { name: "Issue token", exact: true }).click()
  await page.getByLabel("Label", { exact: true }).fill("My client")
  await page.getByRole("button", { name: "Issue token", exact: true }).click()
  await expect(page.getByText("acp_ONE_TIME_SECRET", { exact: true })).toBeVisible()
  assert.deepEqual(writes[0].body, { label: "My client", expires_in_days: 90 })
  await expect(page.getByRole("dialog")).toHaveCount(1)
  await page.getByRole("button", { name: "Done", exact: true }).click()
  await expect(page.getByText("acp_ONE_TIME_SECRET", { exact: true })).toHaveCount(0)
  const retained = await page.evaluate(() => JSON.stringify({ mutations: window.acpQueryClient.getMutationCache().getAll().map((m) => m.state), queries: window.acpQueryClient.getQueryCache().getAll().map((q) => q.state), local: { ...localStorage }, session: { ...sessionStorage } }))
  assert.ok(!retained.includes("acp_ONE_TIME_SECRET"))
  await page.getByRole("button", { name: "Actions for access token My client" }).click()
  await page.getByRole("menuitem", { name: "Revoke token" }).click()
  assert.equal(writes.length, 1)
  await page.getByRole("alertdialog").getByRole("button", { name: "Revoke token" }).click()
  await expect(page.getByRole("alertdialog")).toHaveCount(0)
  assert.equal(writes[1].method, "POST")
  assert.ok(writes[1].url.endsWith("/tokens/token-1/revoke"))
})

test("connector preview is capped and the full list closes before details open", async (t) => {
  const { page } = await openCard(t, { count: 7 })
  await expect(page.getByRole("button", { name: /^Actions for ACP connector/ })).toHaveCount(5)
  await page.getByRole("button", { name: "Show all (7)" }).click()
  await expect(page.getByRole("dialog").getByRole("button", { name: /^Actions for ACP connector/ })).toHaveCount(7)
  await page.getByRole("dialog").getByRole("button", { name: "Actions for ACP connector Editor 7" }).click()
  await page.getByRole("menuitem", { name: "Connection details" }).click()
  await expect(page.getByRole("dialog")).toHaveCount(1)
  await expect(page.getByRole("heading", { name: "Connect to Editor 7" })).toBeVisible()
})

test("failed reads show retry and are never presented as an empty list", async (t) => {
  const { page } = await openCard(t, { fail: true })
  await expect(page.getByRole("alert")).toContainText("Server unavailable")
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible()
  await expect(page.getByText("Add a connector to let an external ACP app use this agent.")).toHaveCount(0)
})
