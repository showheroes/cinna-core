# Authoring & Assigning Agent Prompts

End-to-end walkthrough for giving an agent its **prompts and description** from
the account workspace — in one bulk write that lands in the running environment
automatically.

## When to use this

Read this guide whenever you are **finishing** an agent: you have built its
functionality (scripts, credentials, an Agent REST API, MCP/agent-api
connections, team wiring) and now need to give it the prompts that make it
behave — and a description that accurately reflects what you built.

> **Author prompts LAST.** Create the agent with a one-line *provisional*
> description, build and verify all functionality first, then come back here to
> write the real prompt set from what actually exists. The final acceptance step
> of every build is rewriting the agent's **description** to match the finished
> agent.

## The six fields

An agent carries six prompt-ish fields. They look similar but each is consumed
by a **different system at a different moment** — do not conflate them.

| Field | What it is | When it fires | How it should look |
|-------|-----------|---------------|--------------------|
| `description` | Human-facing summary of what the agent does | Discovery (agent cards, A2A card); also feeds router-trigger / A2A skill generation | One clear sentence describing capability & purpose. *"Reconciles Stripe payouts against the ledger and flags mismatches."* |
| `workflow_prompt` | The **conversation-mode system prompt** — the agent's real execution instructions | Every conversation-mode session (the main prompt) | Operational: which scripts to run, how to parse their output (JSON/CSV), how to present results, decision logic. The agent is a *bridge* — it runs scripts, parses, and rephrases conversationally, quoting every figure from the output and never computing one. Once the agent answers two or more kinds of question it becomes **scope + a routing table** (skill → the questions it owns, in the user's words); the procedures live in `skills/<name>/SKILL.md`. |
| `entrypoint_prompt` | A short, human-like trigger message (1–2 sentences) | First user message for scheduled / automated runs | Conversational, **not** technical. ✅ *"What is my time-off balance?"* ❌ *"Query Odoo API and return JSON."* Must be **self-contained** — it is sent automatically with nobody there to fill anything in, so never leave a placeholder in it. |
| `refiner_prompt` | Instructions for turning a vague request into a structured task | During AI task refinement, before execution | Default-fill rules + mandatory fields. *"If no period is given, default to the current week. Always capture account id and currency."* |
| `router_trigger_prompt` | A single capability-verb sentence used to route incoming messages to this agent | Only by the routing classifier (`AgentClassifier.classify`) — never in any system prompt. Four consumers share it: Server Channels Pass 1 and Pass 2, App MCP Stage 1, and identity Stage 2 | *"Reconciles Stripe payouts and flags ledger mismatches."* Describes *when to route here*, not how to behave. |
| `example_prompts` | Ready-to-use task suggestions (`list[str]`) surfaced *for the agent* — **and a first-class routing input**: the classifier reads it alongside `router_trigger_prompt`, and an agent with neither is not routable | Shown in the A2A / external agent catalog and as MCP slash commands, **and rendered into the routing prompt** on every surface | Short imperative **templates a stranger can use**, never a replay of your build data. `["reconcile last week", "show failed payouts"]`. See [Writing `example_prompts`](#writing-example_prompts-templates-not-a-replay-of-your-build) — this is the field that goes wrong most often. |

### Don't confuse `example_prompts` with binding `prompt_examples`

- **`example_prompts`** (this guide) is an **agent-level** field — a list of
  ready-to-use task suggestions surfaced for the agent (e.g. in the A2A /
  external agent catalog). It is also one of the two fields the routing
  classifier reads, so writing it well makes the agent easier to reach, not
  just easier to start. Set it with `cinna agent prompts` (below).
- **`prompt_examples`** is a *different*, **binding-level** field. It survives
  on `IdentityAgentBinding` only (surfaced in MCP `prompts/list`); the App MCP
  routes that used to carry it are gone. It is not part of agent prompt
  authoring — leave it alone unless you are configuring an identity binding.
  (When you *do* configure one, the authoring rules below apply to it
  verbatim — same audience, same failure mode.)

## Writing `example_prompts`: templates, not a replay of your build

`example_prompts` are shown to **a different person, at a different time, with
different data** than the build you just finished. They are starting points the
user clicks and sends — so every one of them has to still make sense to someone
who was not in the room while you built the agent.

The single most common failure: the authoring agent copies concrete values out
of its own build session — the URL it tested against, the customer id in the
fixture, the report file it happened to open, today's date — and freezes them
into the examples. The result looks specific and useful and is actually dead on
arrival:

❌ `"Check this exact URL: https://internal.acme.example/reports/q3-2025"`
❌ `"Summarize invoice INV-88421"`
❌ `"Reconcile payouts for account acct_1M4kTest"`
❌ `"Analyze /app/workspace/data/sample_export.csv"`

A user who sends any of those gets an answer about *your* test data, not theirs.

### The two shapes an example may take

**1. Universal — needs no input from the user.** Write it out in full, ready to
send as-is:

✅ `"What is my status today?"`
✅ `"reconcile last week"`
✅ `"show failed payouts"`
✅ `"List everything waiting on my approval"`

**2. Input-required — the task is meaningless without a concrete value** (a URL,
an id, a file, an address, a date range). Write a **template that visibly stops
where the user takes over**, with a bracketed placeholder that can never be
mistaken for data:

✅ `"Investigate this URL — <paste the URL here>"`
✅ `"Summarize the invoice with number <invoice number>"`
✅ `"Reconcile payouts for account <account id>"`
✅ `"Analyze the uploaded file <file name>"`

Never substitute a realistic-looking fake (`https://example.com/report`,
`ACC-12345`, `john@example.com`) for the placeholder. A plausible fake is worse
than an obvious blank: the user sends it unchanged and the agent goes off and
does real work against a value nobody meant.

### Colons are structural — do not end a template with one

Each line is parsed as `slug: prompt text`, and **the first colon splits the
line**. A line with no usable colon is used verbatim as both the name and the
text, which is the normal case.

So `"Investigate this URL: <paste the URL here>"` does *not* render as one
sentence — it becomes a prompt named `Investigate this URL` whose entire body is
`<paste the URL here>`. Use an em dash, or fold the placeholder into the
sentence, instead of a trailing colon:

| Intent | ❌ Wrong | ✅ Right |
|--------|---------|---------|
| slugless template | `Investigate this URL: <url>` | `Investigate this URL — <url>` |
| explicit slug | *(none)* | `investigate_url: Investigate this URL — <url>` |

The explicit-slug form (`slug: prompt text`, one per line) is the format the
Config-tab editor documents and what MCP clients use for slash-command names.
Either form is accepted; just never let a *stray* colon appear in a slugless
line.

### Self-check before you write the list

- [ ] No URL, hostname, id, account, email address, file path, or date carried
      over from building or testing.
- [ ] No organization or person names from fixtures or sample data.
- [ ] Every entry is either fully universal, or an obviously unfinished template
      with a `<bracketed>` placeholder.
- [ ] Short and imperative — a handful of words before the placeholder.
- [ ] 3–6 entries covering *distinct* capabilities, not variations of one.
- [ ] Hand-test: would this example still be meaningful to a stranger, next
      month, with their own data? If it only works with the data you used while
      building, rewrite it.

Note the contrast with `entrypoint_prompt`: that one is fired **automatically**
by schedulers and triggers, with no human to complete it, so it must be fully
self-contained and rely on `refiner_prompt` defaults — never put a placeholder
there.

## Editing prompts as files

Edit prompts with `cinna agent prompts`, run from the account workspace root.
Each field lives in its own file, so a prompt's Markdown backticks never pass
through a shell, and a push never silently reverts a change someone made on the
platform after you pulled.

```bash
# 1. Pull the current values into prompts/<agent-slug>/
cinna agent prompts pull billing-agent

# 2. Edit the files (layout below)

# 3. Review your edits, and see whether the platform changed a field since the pull
cinna agent prompts diff billing-agent

# 4. One bulk write of the edited fields; the doc prompts reach the running environment too
cinna agent prompts push billing-agent

# 5. Verify what actually landed
cinna agent show billing-agent --prompts
```

`pull` writes one file per field:

| File | Field |
|------|-------|
| `workflow.md` | `workflow_prompt` |
| `entrypoint.md` | `entrypoint_prompt` |
| `refiner.md` | `refiner_prompt` |
| `router_trigger.md` | `router_trigger_prompt` |
| `description.md` | `description` |
| `example_prompts.json` | `example_prompts` — a JSON list of strings |

For example, `prompts/billing-agent/example_prompts.json`:

```json
[
  "reconcile last week",
  "show failed payouts",
  "Reconcile payouts for account <account id>"
]
```

Note the third entry: the task genuinely needs an account, so it ships as a
template the user finishes — not as the test account you reconciled during the
build. See [Writing `example_prompts`](#writing-example_prompts-templates-not-a-replay-of-your-build).

`push` sends only the fields whose file you edited since the pull. A field the
platform changed since the pull is left alone when you did not edit it, and
refused when you did: `diff` shows both sides, `pull --force` takes the
platform's version and `push --force` keeps yours. Delete a file to leave its
field untouched, use `push --dry-run` to see what would be sent, and `--dir` to
keep the files somewhere other than `prompts/<agent-slug>/`.

### How it reaches the environment

The three document-backed prompts (`workflow_prompt`, `entrypoint_prompt`,
`refiner_prompt`) exist twice — as fields of the agent config and as the
container's `docs/*.md` files. When a push changes one of them, it also pushes
them into the running environment's `docs/*.md` (`--no-sync-env` skips that). If
the environment is not running, the push still saves them and they arrive on its
next start. `router_trigger_prompt`, `example_prompts`, and `description` are
config-only and take effect immediately.

### One-path rule

The agent's config (the database) is authoritative. `cinna agent prompts push`
writes it and refreshes the environment's `docs/*.md`, which then mirror down to
the synced agent workspace. The platform reconciles the config and those files
in both directions, and when both changed since the last reconcile the later
write wins — so hand-editing the synced `workspace/docs/*.md` as well as the
prompt files is a race that one of the two edits loses. Change a prompt through
`cinna agent prompts` **or** through the synced docs, never both at once; for the
account orchestrator, `cinna agent prompts` is the path. (That is also why this
guide calls the config authoritative while the Local Agent Kit calls
`docs/WORKFLOW_PROMPT.md` "the single source": both hold, as long as each change
takes one path.)

> **Without the prompt verbs** (an older CLI), the same write is
> `cinna api PUT agents/<agent_id> --data @<file>.json` with a JSON object of just
> the fields to change, then `cinna api POST agents/<agent_id>/sync-prompts` for a
> running environment. Keep that file outside `agents/` — that tree is the synced
> workspace — and never build the JSON inline in the shell: zsh
> command-substitutes the backticks in Markdown prompts.

## Optional: let the platform generate the router trigger

If you'd rather not hand-write `router_trigger_prompt`, the platform can derive
it from the agent's name + description:

```bash
cinna api POST agents/<agent_id>/generate-router-trigger-prompt
```

This derives the trigger from the agent's name **and description**, so it
requires a `description` to already be set on the agent (it errors out if none
is set) — call it *after* you've pushed the description. It writes
`router_trigger_prompt` on the platform directly; run
`cinna agent prompts pull <agent>` afterwards so `router_trigger.md` shows it.

This only generates the routing sentence. The other prompts and the description
are yours to author — you have the full build context and are the better author.

## The finalize step (do this at the end of every build)

1. Confirm all functionality works (scripts run, connections resolve, the API
   spec harvests, etc.).
2. `cinna agent prompts pull <name>`, then author the full prompt set in the
   files **from what you actually built**:
   - `workflow_prompt` describes the *real* scripts/flow you created;
   - `entrypoint_prompt` matches the *real* trigger;
   - `refiner_prompt` matches the *real* task fields;
   - `router_trigger_prompt` + `example_prompts` reflect *real* capabilities —
     and `example_prompts` are written as **user-ready templates**, scrubbed of
     every URL, id, path, and date you used while building (run the self-check
     in [Writing `example_prompts`](#writing-example_prompts-templates-not-a-replay-of-your-build));
   - **`description` is rewritten to accurately describe the finished agent.**
     Write it in `description.md` for the same push — don't rely on auto-derivation.
3. `cinna agent prompts diff <name>`, then `cinna agent prompts push <name>` —
   which also puts the doc prompts into a running environment.
4. `cinna agent show <name> --prompts` to confirm.
5. If the agent has recorded test scenarios (`docs/test_scenarios/`), re-run them
   with `cinna chat` — a prompt edit is a behaviour change, and so is a model or
   provider switch. How to record and run them:
   `context/local-kit/guides/13-design-patterns.md` §9.

An agent whose `description` and prompts match its actual behavior is the mark of
a finished build.
