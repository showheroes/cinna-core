import assert from "node:assert/strict"
import path from "node:path"
import { after, before, test } from "node:test"
import { fileURLToPath } from "node:url"
import { chromium, expect } from "@playwright/test"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { createServer } from "vite"

const frontendRoot = fileURLToPath(new URL("..", import.meta.url))
let server
let browser
let baseUrl
let harnessHtml

before(async () => {
  server = await createServer({
    configFile: false,
    root: frontendRoot,
    resolve: { alias: { "@": path.join(frontendRoot, "src") } },
    plugins: [react(), tailwindcss()],
    server: { host: "127.0.0.1", port: 0 },
    logLevel: "error",
  })
  await server.listen()
  baseUrl = `http://127.0.0.1:${server.httpServer.address().port}`
  harnessHtml = await server.transformIndexHtml(
    "/",
    '<html><body><div id="root"></div><script type="module" src="/tests/fixtures/skillInstallHarness.tsx"></script></body></html>',
  )
  browser = await chromium.launch({ headless: true })
})

after(async () => {
  await browser?.close()
  await server?.close()
})

async function openInstall(t, { needsSetup, sync = {} }) {
  const page = await browser.newPage()
  page.setDefaultTimeout(10000)
  t.after(() => page.close())
  const errors = []
  page.on("pageerror", (error) => errors.push(error.message))
  t.after(() => assert.deepEqual(errors, []))
  const item = {
    slot: "erp",
    type: "api_token",
    provided_by: "user",
    outcome: "linked_existing",
    credential_name: "ERP key",
    needs_setup: needsSetup,
  }
  const revision = {
    id: "revision-1",
    revision_number: 1,
    version: "1.0.0",
    required_credentials: [
      { slot: "erp", type: "api_token", provided_by: "user" },
    ],
  }
  await page.route(`${baseUrl}/`, (route) =>
    route.fulfill({
      contentType: "text/html",
      body: harnessHtml,
    }),
  )
  const posts = []
  await page.route("**/api/**", async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    let json
    if (pathname === "/api/v1/agents/") {
      json = { data: [{ id: "agent-1", name: "Test agent" }], count: 1 }
    } else if (pathname === "/api/v1/skills/packages/package-1") {
      json = { latest_revision: revision, revisions: [revision] }
    } else if (pathname === "/api/v1/agents/agent-1/skills/install-preview") {
      json = { credentials: [item] }
    } else if (
      pathname === "/api/v1/agents/agent-1/skills/install" &&
      request.method() === "POST"
    ) {
      posts.push(request.postDataJSON())
      json = {
        success: true,
        message: "Installed",
        credential_provisioning: [item],
        ...sync,
      }
    } else {
      errors.push(`Unexpected API request: ${request.method()} ${pathname}`)
      await route.abort()
      return
    }
    await route.fulfill({ json })
  })
  await page.goto(baseUrl)
  await page.getByRole("button", { name: "Select an agent" }).click()
  await page.getByRole("radio", { name: "Test agent" }).click()
  await expect(
    page.getByText(
      needsSetup
        ? "1 needs setup after install."
        : "Ready to use on this agent.",
    ),
  ).toBeVisible()
  await page.getByRole("button", { name: "Add to agent", exact: true }).click()
  await expect.poll(() => posts.length).toBe(1)
  assert.deepEqual(posts[0], {
    package_id: "package-1",
    revision_number: null,
    conversation_mode: true,
    building_mode: true,
  })
  return page
}

for (const [label, sync] of Object.entries({
  failed: { failed_syncs: 1 },
  unsupported: { unsupported_syncs: 1 },
  partial: { partial_failures: true },
})) {
  test(`ready install warns about ${label} sync instead of claiming success`, async (t) => {
    const page = await openInstall(t, { needsSetup: false, sync })
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await expect(
      page.locator('[data-sonner-toast][data-type="error"]'),
    ).toContainText("didn't reach every environment")
    await expect(
      page.locator('[data-sonner-toast][data-type="success"]'),
    ).toHaveCount(0)
  })
}

for (const closeVia of ["Done", "Escape", "Credentials"]) {
  test(`reused placeholder keeps setup visible and warns after ${closeVia}`, async (t) => {
    const page = await openInstall(t, {
      needsSetup: true,
      sync: { partial_failures: true },
    })
    await expect(
      page.getByRole("heading", { name: "ERP installed" }),
    ).toBeVisible()
    await expect(
      page.getByText("1 credential needs setup before the skill can use it."),
    ).toBeVisible()
    const link = page.getByRole("link", { name: "Open the Credentials tab" })
    await expect(link).toBeFocused()
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(0)
    if (closeVia === "Escape") await page.keyboard.press("Escape")
    else if (closeVia === "Done")
      await page.getByRole("button", { name: "Done" }).click()
    else {
      await link.click()
      await expect(page).toHaveURL(`${baseUrl}/agent/agent-1#credentials`)
    }
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await expect(
      page.locator('[data-sonner-toast][data-type="error"]'),
    ).toContainText("agent's Addons tab")
  })
}

test("fully synced ready install closes with success", async (t) => {
  const page = await openInstall(t, { needsSetup: false })
  await expect(page.getByRole("dialog")).toHaveCount(0)
  await expect(
    page.locator('[data-sonner-toast][data-type="success"]'),
  ).toContainText("Added ERP to Test agent")
  await expect(
    page.locator('[data-sonner-toast][data-type="error"]'),
  ).toHaveCount(0)
})
