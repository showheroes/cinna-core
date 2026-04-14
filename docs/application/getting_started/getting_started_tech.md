# Getting Started — Technical Details

## File Locations

### Frontend
- `frontend/src/components/Onboarding/ApiKeyOnboarding.tsx` — Full-screen API key input gate
- `frontend/src/components/Onboarding/GettingStartedModal.tsx` — Encyclopedia modal with article navigation
- `frontend/src/components/Common/RotatingHints.tsx` — Clickable rotating hints widget
- `frontend/src/components/Chat/MessageInput.tsx` — Embeds `RotatingHints`, manages its own modal instance
- `frontend/src/routes/_layout/index.tsx` — Dashboard: credentials status query, conditional rendering, modal state

### Backend
- `backend/app/api/routes/users.py` — `get_ai_credentials_status()` and `update_ai_credentials()` endpoints
- `backend/app/services/credentials/ai_credentials_service.py` — Credential CRUD and default management
- `backend/app/models/credentials/ai_credential.py` — `AICredential` model and schemas
- `backend/app/models/users/user.py` — `UserPublicWithAICredentials` schema, `has_anthropic_api_key` flag

## API Endpoints

- `GET /api/v1/users/me/ai-credentials/status` — Returns `UserPublicWithAICredentials` with `has_anthropic_api_key: bool`. Used by Dashboard to decide whether to show the gate
- `PATCH /api/v1/users/me/ai-credentials` — Accepts `AIServiceCredentialsUpdate`. Creates or updates the default `anthropic` credential. Called by `ApiKeyOnboarding` on submit. When creating a new Anthropic credential (first-time), also auto-sets `user.default_ai_functions_sdk` to `"personal:anthropic"` so AI utility functions use the user's key immediately

## Frontend Components

### ApiKeyOnboarding (`frontend/src/components/Onboarding/ApiKeyOnboarding.tsx`)

- Full-screen layout with gradient icon and animated sparkles
- Password-masked input field; submit button animates in when input has a value
- State machine: `idle` → `ready` → `pending` → `success`
- On `success`: shows checkmark icon for 1200ms, then fires `onComplete` callback
- Calls `UsersService.updateAiCredentials()` via `useMutation`
- Contains external link to Claude API Settings for key generation

### GettingStartedModal (`frontend/src/components/Onboarding/GettingStartedModal.tsx`)

- Shadcn `Dialog` component, 800px max-width, 80vh max-height
- Left sidebar (224px) with article list; violet accent on selected item, chevron indicator
- Right pane renders selected article content
- Articles defined in a local `articles[]` config array (not fetched from backend)
- `setSelectedArticle` passed into article content functions to enable cross-article navigation
- "Start Building" gradient button closes the modal
- Five articles (IDs): `gmail-quickstart`, `build-agent`, `share-credentials`, `conversation-vs-building`, `app-mcp-setup`
- Accepts optional `initialArticle` prop to open the modal at a specific article (used by the MCP Server card in Settings > Channels)
- Exports `ArticleId` type for use by other components

### RotatingHints (`frontend/src/components/Common/RotatingHints.tsx`)

- Renders as a `<button>` element with darkened hover state
- Hints array shuffled on mount via Fisher-Yates shuffle
- Rotates every 8 seconds using a `setInterval` (configurable via prop)
- 600ms CSS fade transition between hints
- Accepts `onClick` prop; parent passes `() => setShowGettingStarted(true)`

## State Management — Dashboard

Location: `frontend/src/routes/_layout/index.tsx`

- Query `["aiCredentialsStatus"]` → `UsersService.getAiCredentialsStatus()` → `hasAnthropicKey` boolean
- `showGettingStarted` local `useState(false)` controls modal visibility
- Rendering logic:
  - `hasAnthropicKey === false` → render `<ApiKeyOnboarding onComplete={...} />`
  - `hasAnthropicKey === true` → render normal dashboard + `<GettingStartedModal />`
- `onComplete` handler: sets `showGettingStarted(true)` + calls `queryClient.invalidateQueries(["aiCredentialsStatus"])`

## State Management — MessageInput

Location: `frontend/src/components/Chat/MessageInput.tsx`

- Maintains its own `showGettingStarted` state independent of the Dashboard
- Renders `<RotatingHints onClick={() => setShowGettingStarted(true)} />`
- Renders its own `<GettingStartedModal />` instance (not shared with Dashboard)

## Services Used (Frontend)

- `frontend/src/client/sdk.gen.ts` — `UsersService.getAiCredentialsStatus()` for credentials gate check; `UsersService.updateAiCredentials()` for saving the API key on onboarding

## Configuration Notes

- No server-side state tracks whether a user has seen onboarding — triggers are purely client-side
- `RotatingHints` rotation interval defaults to 8000ms; configurable per usage site via props
- Modal article content is hard-coded in the component; any content updates require a frontend deploy
- **Google OAuth is optional** — When `VITE_GOOGLE_CLIENT_ID` is not set: `GoogleOAuthProvider` is not rendered in `frontend/src/main.tsx`, `GoogleLoginButton` returns `null`, login/signup pages hide the "Or continue with email" divider, and `OAuthAccounts` settings card is hidden. This prevents Google SDK errors on fresh installs without OAuth credentials

---

*Last updated: 2026-04-10*
