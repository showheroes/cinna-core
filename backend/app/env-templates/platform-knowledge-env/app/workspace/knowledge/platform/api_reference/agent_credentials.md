# Agent Credentials — API Reference

Auto-generated from OpenAPI spec. Tag: `agent-credentials`

## POST `/api/v1/agent/credentials/{credential_id}/access-token`
**Agent Credential Access Token**

**Path parameters:**
- `credential_id`: uuid

**Request body** (`AgentCredentialAccessTokenRequest`):
  - `min_ttl`: integer
  - `known_expires_at`: integer | null

**Response:** `AgentCredentialAccessTokenResponse`

---
