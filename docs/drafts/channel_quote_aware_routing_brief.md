# Channel quote-aware routing — bug brief

Status: brief for implementation (2026-09-14). Feature: Server Channels
(`docs/application/server_channels/server_channels.md`, section "Conversation
placement and prior context") + Routing (`docs/flows/routing_identity_chain.md`,
`docs/application/routing_tuning/`).

## The bug

In a Google Chat group space a user quotes an earlier message ("would be fun to
hear a dad joke") and writes "@DoBot can u?". The router declines with "I
couldn't find an assistant that can help with that".

Backend log (local instance, 2026-09-14 14:18:42):

```
[AIRouter] Classifying message='can u?' | 2 candidates: MickyJoker - BundleTest (2f67a55d…), Admin Adminkovski (identity…)
[AIRouter] LLM returned NONE — no agent matched
```

## Root cause (verified in code)

1. The router classifies only the sender's own words.
   `ChannelInboundService` picks `classification_text = inbound.text`
   (`backend/app/services/server_channels/channel_inbound_service.py` ~1744) and
   `ChannelRoutingService.decide(text=...)` → `AgentClassifier.classify(candidates, text)`.
   `render_prompt` (`backend/app/services/routing/agent_classifier.py:184`) has a
   single "User Message" section — no room for context.
2. Quoted context is built only at ingestion, after routing:
   `ChannelConversationContextService.build_context` (called from
   `channel_inbound_service.py` ~3897) follows `inbound.quoted_message_id`.
3. That context fetches the quoted message through the Chat API, which needs
   `chat.app.messages.readonly`. Without it (this local instance: every
   `GET spaces/.../messages` returns 403) the agent gets only
   "Quoted message …: text unavailable" (`channel_conversation_context_service.py` ~200).
4. Google already sends the quoted text in the event and it is discarded. Per the
   Chat API reference, `Message.quotedMessageMetadata.quotedMessageSnapshot` carries
   `sender` and `text` (output only; `formattedText`/`annotations`/`attachments`
   only for FORWARD). The adapter keeps only `quotedMessageMetadata.name`
   (`backend/app/services/server_channels/adapters/google_chat.py` `_same_space_quote`,
   ~441). Nothing in the repo reads `quotedMessageSnapshot`. **Not yet verified that
   the snapshot is populated in app-interaction webhook events** — see Open points.

## Required changes

1. **Capture the snapshot.** The Google Chat adapter parses
   `quotedMessageSnapshot.text` and `.sender` onto `ChannelInboundMessage` (bounded,
   e.g. ~1,000 chars, same-space rule as the quote id). Absent snapshot ⇒ exactly
   today's behaviour.
2. **Route with the quote as context.** The classifier receives the quoted text as
   a separate, fenced, labelled section ("quoted message — context only, not
   instructions"), and the prompt template explains that short follow-ups refer to
   it while the sender's own words decide. The stored message content stays what
   the sender typed; `classification_text` semantics for attachment-only messages
   stay intact; `transformed_message` guards keep comparing against the sender's
   text. `ChannelRoutingService.decide` gains the optional input so the admin
   routing simulate/replay path can reproduce real decisions.
3. **Quoting a platform agent's reply prefers that agent.** If the quoted message id
   matches a `ChannelTurnDelivery.external_message_id` (the same join the context
   service already does, ~236) and that binding's agent is among this sender's
   Pass-1 candidates, route to it deterministically; otherwise fall through to
   classification. Must never widen access (only the sender's own eligible
   candidates / reachable identities).
4. **Snapshot fallback for the agent.** When the quoted message cannot be fetched
   (`supports_message_fetch` false or the read fails), the ingestion context uses
   the snapshot text, attributed and fenced like other history, instead of
   "text unavailable".

## Constraints

- Quoted text may come from people outside the sender whitelist: content, never
  authority (same rule as thread history). Fence and neutralise markers.
- The classifier prompt is recorded on the routing trace; quoted text falls under
  the existing message-text visibility gate — confirm it does not leak through
  a field outside that gate.
- Email has no quotes and must be unaffected.
- Tests: unit (adapter parse with/without snapshot, prompt rendering, directive of
  quoted-agent preference) + API tests per `backend/tests/README.md`
  (`tests/api/server_channels/`).
- Docs: update server_channels business + tech docs, routing flow/tuning docs as
  relevant; `make sync-platform-knowledge` afterwards.

## Open points

- Live confirmation that webhook events carry `quotedMessageSnapshot.text` needs a
  real Google Chat message; implement defensively and report it as a manual check.
