# Channel routing guidance — design brief

Status: design for discussion (2026-09-14), no code yet. Feature: Server Channels
(`docs/application/server_channels/server_channels.md`) + Routing
(`docs/flows/routing_identity_chain.md`, `docs/application/routing_tuning/`).
Builds on the quote-aware routing work in `f14a32c8`.

## The problem

On a channel (Google Chat first) the router has exactly two answers: route the
message to an agent, or settle the status notice with

> I couldn't find an assistant that can help with that. Please contact your
> administrator.

Three situations make that answer true but useless:

1. **Meta questions.** "What agents do I have?", "How can you help me?",
   "Who are you?" — the classifier correctly returns `NONE` (no agent's trigger
   prompt describes *answering questions about the platform*) and the sender is
   told to contact an administrator for a question the router could have
   answered itself from the ballot it just rendered.
2. **Genuine ambiguity.** Two agents fit about equally and the wording does not
   decide. Today's prompt says "pick the most specific one" (rule 3) or "if
   uncertain return NONE" (rule 4), so the sender either lands on a silent
   best guess or gets the no-match sentence. Nothing asks them.
3. **A real task nothing fits.** The sender learns that nothing matched, but not
   what *would* have — so the natural next move (rephrase, or name the agent)
   is guesswork.

## Where it lives today (verified in code)

- One classifier for every consumer: `AgentClassifier.classify`
  (`backend/app/services/routing/agent_classifier.py`) renders
  `app/agents/prompts/app_agent_router_prompt.md` over a `Candidate` list and
  parses `{"agent_id", "message", "confidence", "reason", "runner_up"}`.
  `confidence` / `runner_up` are recorded, never acted on (plan §8 of the
  tuning feature: gating on a score needs data).
- `ChannelRoutingService.decide` (`channel_routing_service.py`) is pure and
  returns `RoutingDecisionResult` — an agent id, a bundle id, or neither. It
  has **no vocabulary for "say something back"**.
- The effect half, `ChannelInboundService._route_new_thread`
  (`channel_inbound_service.py` ~2121), turns "neither" into
  `REPLY_NO_MATCH` via `_settle_notice` (~2745), which rewrites the status
  notice on Google Chat and falls back to `_reply` → `adapter.send_message`
  (email gets it as a mail).
- `ChannelThreadBinding.agent_id` is **NOT NULL**. A thread cannot be "bound
  to a pending question"; there is no state between "no binding" and "bound to
  agent X" except `pending_install`, which already carries `pending_messages`
  (the park/drain mechanism).
- `process_inbound` (~1199, ~1660) dispatches on the binding: control command
  → active → pending_install (park) → failed (delete + re-route) → no binding
  → `_route_new_thread`. A sender's *reply to a question* would arrive here as
  an unbound message and be classified on its own — "2" or "the joker one"
  routes to nothing.
- Every sender-facing string in `channel_inbound_service.py` is static and
  deliberately uninformative (the "no oracle" family), with one documented
  exception (`REPLY_ATTACHMENTS_REJECTED`) whose justification applies here
  too: it is reached only after every gate admitted the sender, and it talks
  about *the sender's own* situation.

## Design

### Principle 1 — the model decides the shape, the backend writes the words

No model-authored prose reaches a channel. The classifier returns a categorical
`intent`; the platform composes the reply from data the sender is already
entitled to: the names and trigger prompts of the candidates **on their own
ballot** (own agents, identities that bound them, catalog bundles
`user_can_install` admits). This keeps the no-oracle posture, makes replies
pinnable in tests the way reachability verdicts are, and means quoted
third-party text can never author outbound text through the router.

Trade-off accepted: templated replies are less conversational than a model
sentence. For "what can you do" a list of *Name — what it handles* is the
right answer anyway; for a clarifying question, naming the two options with
their descriptions is enough.

### Principle 2 — one LLM call, additive contract, graceful degradation

Extend the JSON the classifier already asks for:

```json
{"agent_id": "<uuid>|NONE", "intent": "route|clarify|help|none",
 "options": ["<uuid>", "<uuid>"], "message": ..., "confidence": ..., "reason": ..., "runner_up": ...}
```

- `route` — exactly today.
- `clarify` — ≥2 candidates fit about equally and the sender's wording does not
  decide; `options` lists 2–3 candidate ids **in preference order**, and
  `agent_id` still carries the model's best pick. Consumers that do not know
  about `intent` therefore behave as before (they route the best pick), and so
  do transports that cannot ask (see below). Identity Stage 2 and App MCP call
  `classify()` and are untouched — the same design as `quoted=None` keeping
  the prompt byte-identical for them.
- `help` — the message is about the assistant/platform itself (what can you
  do, which agents/assistants do I have, who are you, help). `agent_id` is
  `NONE`.
- `none` — a real task and nothing fits. `agent_id` is `NONE`, as today.

Parsing is defensive like every other field: a missing or unknown `intent`
means `route` when `agent_id` is set and `none` otherwise; `options` not on the
ballot are dropped, fewer than two survivors collapse `clarify` into `route`.
A small model that ignores the new fields produces exactly today's behaviour.

Ambiguity is a **categorical answer** from the model, not a threshold over
`confidence` — which is what plan §8 was guarding against. The recorded
`confidence` / `runner_up` columns stay as they are and will let the tuning
surface check, after the fact, whether the model's `clarify` calls line up
with low-confidence rows.

Quoted context keeps its rule: it may help read a short follow-up, it never
drives `intent` and never lands in a reply.

### What the sender gets

All three are composed by one pure function (`compose_guidance_reply`) from
`(intent, candidates, options, catalog_offer)` — list capped at 5 with "and N
more", names and descriptions clamped, markdown that `markdown_to_chat`
already translates.

| Situation | Reply (Google Chat, illustrative) |
|---|---|
| `help`, ballot non-empty | "Here's who I can hand your message to:<br>• **Joker** — tells jokes and light banter<br>• **HR Helper** — leave, payroll and policy questions<br>• **Anna Admin** — ask Anna's assistants<br>Just describe what you need and I'll pick the right one." |
| `help`, ballot empty, catalog offers bundles | "You don't have an assistant yet. I can set one up for you:<br>• **Support Desk** — …<br>Describe what you need and I'll set it up." |
| `help`, nothing anywhere | today's `REPLY_NO_MATCH` (there is nothing to say) |
| `clarify` | "That could go to two of your assistants:<br>1. **Joker** — tells jokes…<br>2. **Writer** — drafts posts and copy…<br>Reply with the number or the name. Anything else and I'll treat it as a new request." |
| `none`, ballot non-empty | "I couldn't find an assistant for that. I can route to: **Joker** (…), **HR Helper** (…). Rephrase, or name the one you mean." |
| `none`, nothing anywhere | today's `REPLY_NO_MATCH` unchanged |

The reply *settles* the status notice (it is the answer for this turn), the
same operation `REPLY_NO_MATCH` uses today. The debug feed gets a
`DEBUG_GUIDED` entry; the trace gets `outcome="guided"` with a stage-level
`guidance_kind` and `guidance_options` (ids only — safe fields).

### The clarification round-trip

This is the only part that needs state, and it is where a shortcut would hurt.

**State:** a new table `channel_routing_clarification` — one row per
`(server_channel_id, scope_key, user_id)`, the same key a binding uses, so a
second asker in the same space is unaffected. It holds the options offered
(`ref_id`, `name`, `kind` ∈ agent | identity | bundle), the **original**
message exactly as the park mechanism stores one (`text`, `classification_text`,
`file_ids`, `external_message_id`, quote fields), `status_message_id`, and
`expires_at`. Not a binding: `ChannelThreadBinding.agent_id` is NOT NULL and
every ownership invariant reads it; making it nullable would touch every
reader for a state that is not a conversation yet.

**Dispatch:** in `process_inbound`, when there is no binding (or a failed one
was just cleared), look for a live clarification for the key. If one exists:

1. `resolve_choice(reply_text, options)` — a pure, unit-tested function.
   Ordinal ("1", "2", "first", "second"), exact / prefix / unique-substring
   name match, case-insensitive. "neither" / "none" / "cancel" cancels.
2. Not resolvable → one classifier call over the options only, with the reply
   as the user message and the original message as `QuotedContext` (context,
   not authority — the existing renderer does exactly this). `NONE` → the
   clarification is dropped and the message routes as a fresh request, which
   is the right reading of someone who moved on.
3. Resolved → delete the row and run the ordinary `_route_new_thread` for the
   **original** message with a new argument `chosen_ref_id` on
   `decide()`. Inside Pass 1 the chosen ref must be on the ballot as rebuilt
   under the *current* policy (narrows only — the same rule as
   `_route_quoted_reply`), records `match_method="clarified"`, and an identity
   ref still goes through Stage 2. A bundle ref goes to Pass 2 with the same
   pin and ends as `parked_install` as today. The choice message itself is not
   ingested — it answered the router, not the agent — and is recorded on the
   debug feed only.
4. Expired row (default TTL 30 min, `CHANNEL_ROUTING_CLARIFY_TTL_MINUTES`) →
   deleted lazily and the message routes fresh. A periodic purge rides the
   existing pending-binding scheduler tick.

**Transport gate:** clarification is asked only where the adapter reports
`supports_status_notice` (Google Chat). Email and any transport that cannot
rewrite its own message degrade `clarify` to `route` on the best pick — no
question is ever sent that the platform cannot follow up on within the TTL.
`help` and `none` replies go everywhere `REPLY_NO_MATCH` goes today.

### What stays deliberately unchanged

- **Pinned agent** and **`only_one` short-circuit**: no model call today, no
  model call after. A single-agent sender's "what can you do?" reaches that
  agent, which can answer for itself. Detecting `help` there would put an LLM
  call in front of every message for the population the short-circuit exists
  to spare.
- **Identity Stage 2** and **App MCP**: same prompt, `classify()` unchanged,
  they route the best pick. App MCP's discovery need is already served by
  `prompts/list`.
- **`decide()` purity**: guidance is a frozen dataclass of plain strings/ids on
  `RoutingDecisionResult` (added to the purity test's `also_plain_data`
  allowlist), so `POST /admin/routing/simulate` returns it and an admin can see
  *what the sender would have been told* — the tuning loop this feature needs.

### Trace and tuning surface

- `OUTCOME_GUIDED = "guided"` + stage fields `guidance_kind`,
  `guidance_options` (safe: ids and an enum, never sender text).
- `MATCH_CLARIFIED = "clarified"` on the follow-up decision, next to
  `quoted_reply` / `only_one` / `ai`.
- New reachability verdicts, one sentence + one test each per the 16-code
  convention: `guided_help`, `guided_clarify`, `guided_no_match`,
  `clarified` (the follow-up).
- Simulate response gains `guidance_reply` (the composed text) so the admin
  page can show it; frontend: outcome badge + the reply on the trace detail.
- Trigger prompts become user-visible on the channel. Worth one line in the
  agent prompts doc: "this sentence is what your users are shown when they ask
  what you can do".

### Settings

- `CHANNEL_ROUTING_GUIDANCE_ENABLED: bool = True` — kill switch for the effect
  half. Off ⇒ every reply is exactly today's, clarify degrades to best pick,
  no clarification rows are written. The prompt still asks for `intent`
  (harmless when ignored) so the trace keeps showing what the model would
  have done.
- `CHANNEL_ROUTING_CLARIFY_TTL_MINUTES: int = 30`.
- `CHANNEL_ROUTING_GUIDANCE_MAX_LISTED: int = 5`.

## Phasing

1. **Classifier contract** — template, parser (`intent`, `options`), trace
   fields, `ClassificationResult.intent/options`. Unit tests for parsing and
   for `render_prompt(quoted=None)` still identical across consumers. No
   sender-visible change.
2. **Guidance replies** — `compose_guidance_reply`, `RoutingGuidance` on the
   decision result, the effect branch in `_route_new_thread`, debug kind,
   `outcome=guided`, simulate `guidance_reply`, settings. API tests in
   `tests/api/server_channels/` (help lists own agents and reachable
   identities only; empty ballot + catalog lists bundles; `none` lists the
   ballot; flag off ⇒ `REPLY_NO_MATCH`; email receives help/none, never a
   question) and `tests/api/routing/` (simulate shows the reply, no send).
3. **Clarification round-trip** — model + migration, dispatch branch,
   `resolve_choice`, `chosen_ref_id` on `decide`, `match_method=clarified`,
   TTL purge. API tests: question then "2" ingests the *original* text and
   files to the second agent; name reply; unrelated reply routes fresh; expiry;
   second asker unaffected; identity option goes through Stage 2; bundle
   option parks an install; re-delivery of the choice is idempotent.
4. **Tuning + docs** — verdict codes with sentences, frontend badge/reply,
   server_channels + routing flow + tuning docs, agent prompts note,
   `make sync-platform-knowledge`.

## Decisions to confirm

1. Templated replies rather than model prose — recommended, see Principle 1.
2. On `none` with a non-empty ballot, list the ballot (recommended) or keep
   the administrator sentence.
3. Clarify on Google Chat only for now; email degrades to best pick.
4. Leave the `only_one` short-circuit as is (a single-agent sender's meta
   question reaches their agent).

## Open points

- `markdown_to_chat` handles the bullet/numbered list shapes above — verify
  once against a real space; the composer should stay to bold + line breaks
  if not.
- Whether `help` should also be recognised on a **bound** thread ("what else
  can you do?" mid-conversation) — out of scope here; a bound thread has an
  agent and the message is the agent's.
