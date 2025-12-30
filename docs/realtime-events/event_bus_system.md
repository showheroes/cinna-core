# Real-Time Event Bus System

## Overview

WebSocket-based event bus using Socket.IO for real-time communication between backend (FastAPI) and frontend (React). Events are emitted from backend on data changes, and frontend components subscribe to specific event types to update in real-time.

## Architecture

```
Frontend Components          Backend Services
       |                            |
   useEventBus hooks          EventService
       |                            |
   eventService.ts      ←WebSocket→ Socket.IO Server
       |                            |
   socket.io-client               /ws endpoint
```

**WebSocket URL**: `ws://localhost:8000/ws` (dev) | `wss://api.domain.com/ws` (prod)

## Event Structure

```typescript
{
  type: string              // Event type (e.g., 'session_updated')
  model_id?: string         // Related model UUID
  text_content?: string     // Optional user notification
  meta?: Record<string, any> // Additional metadata
  user_id?: string          // Target user UUID
  timestamp: string         // ISO timestamp
}
```

## Event Types

**Sessions**: `session_created`, `session_updated`, `session_deleted`
**Messages**: `message_created`, `message_updated`, `message_deleted`
**Activities**: `activity_created`, `activity_updated`, `activity_deleted`
**Agents**: `agent_created`, `agent_updated`, `agent_deleted`
**Streaming**: `stream_started`, `stream_completed`, `stream_error`
**Generic**: `notification`

## Key Files

### Backend
- **`backend/app/models/event.py`** - Event models (`EventType`, `EventBase`, `EventPublic`, `EventBroadcast`)
- **`backend/app/services/event_service.py`** - `EventService` class (connection management, event emission)
- **`backend/app/api/routes/events.py`** - Event API routes (`/broadcast`, `/stats`, `/test`)
- **`backend/app/main.py`** - Socket.IO mount at `/ws` path

### Frontend
- **`frontend/src/services/eventService.ts`** - Socket.IO client wrapper
- **`frontend/src/hooks/useEventBus.ts`** - React hooks for subscriptions

## Usage

### Backend: Emit Events

```python
# backend/app/api/routes/sessions.py
from app.services.event_service import event_service
from app.models.event import EventType

await event_service.emit_event(
    event_type=EventType.SESSION_UPDATED,
    model_id=session_id,
    user_id=current_user.id,
    meta={"field": "value"}  # optional
)
```

**Key Methods** (`EventService` in `event_service.py`):
- `emit_event()` - Broadcast to user room (`user_{user_id}`)
- `broadcast_to_room()` - Broadcast to custom room
- `get_connection_stats()` - Get active connections

### Frontend: Subscribe to Events

**1. Initialize Connection** (in root layout):
```tsx
// frontend/src/routes/__root.tsx
import { useEventBusConnection } from "@/hooks/useEventBus"

function RootComponent() {
  useEventBusConnection() // Auto-connects when authenticated
  return <Outlet />
}
```

**2. Subscribe in Components**:
```tsx
import { useEventSubscription, EventTypes } from "@/hooks/useEventBus"

function LatestSessions() {
  const queryClient = useQueryClient()

  useEventSubscription(EventTypes.SESSION_UPDATED, (event) => {
    queryClient.invalidateQueries({ queryKey: ["sessions"] })
  })

  // ... component code
}
```

**Key Hooks** (`useEventBus.ts`):
- `useEventBusConnection()` - Manages connection lifecycle
- `useEventSubscription(type, handler)` - Subscribe to single event type
- `useMultiEventSubscription(types, handler)` - Subscribe to multiple types
- `useRoomSubscription(room)` - Subscribe to custom room

## API Endpoints

```
POST /api/v1/events/broadcast - Broadcast event (admin or to self)
GET  /api/v1/events/stats     - Connection statistics
POST /api/v1/events/test      - Send test event to current user
```

## Production Setup

### Environment Variables

**Backend (`.env`)**:
```bash
DOMAIN=project.com
FRONTEND_HOST=https://project.com
BACKEND_CORS_ORIGINS="https://project.com,https://api.project.com"
```

**Frontend (build args in `docker-compose.yml`)**:
```yaml
args:
  - VITE_API_URL=https://api.${DOMAIN}
```

### Docker Configuration

WebSocket uses **same port** as HTTP API (8000). Socket.IO upgrades HTTP → WebSocket.

```yaml
# docker-compose.yml
backend:
  ports:
    - "8000:8000"  # API + WebSocket
frontend:
  ports:
    - "80:80"      # Static files
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl;
    server_name api.project.com;

    location / {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;  # 24h keepalive
    }
}
```

**Production URLs**:
- Frontend: `https://project.com`
- Backend API: `https://api.project.com`
- WebSocket: `wss://api.project.com/ws` (auto-upgrade from HTTPS)

## Testing

```bash
# Send test event
curl -X POST http://localhost:8000/api/v1/events/test \
  -H "Authorization: Bearer TOKEN"

# Check connection stats
curl http://localhost:8000/api/v1/events/stats \
  -H "Authorization: Bearer TOKEN"
```

## Dependencies

**Backend**: `python-socketio==5.16.0`, `python-engineio==4.13.0`
**Frontend**: `socket.io-client`

## Best Practices

1. **Invalidate queries, don't manually update cache**:
   ```tsx
   queryClient.invalidateQueries({ queryKey: ["sessions"] })
   ```

2. **Use specific event types** (avoid wildcard `"*"` subscriptions)

3. **Include metadata for context**:
   ```python
   meta={"session_id": str(session_id), "agent_id": str(agent_id)}
   ```

4. **Filter events in handlers when needed**:
   ```tsx
   if (event.model_id === currentSessionId) { /* handle */ }
   ```

## Troubleshooting

**Connection Issues**:
- Check browser console: `[EventService] Connected, socket ID: ...`
- Backend logs: `docker-compose logs -f backend | grep EventService`
- Verify CORS: `BACKEND_CORS_ORIGINS` includes frontend URL

**Events Not Received**:
- Event type matches between backend/frontend
- `user_id` set correctly when emitting
- Browser Network tab shows WebSocket connection (ws:// protocol)

## Extension Points

To extend this system:

1. **Add new event types**: Update `EventType` enum in `backend/app/models/event.py`
2. **Custom rooms**: Use `event_service.broadcast_to_room(room_name, event_data)`
3. **Multi-instance scaling** (potential future implementation): Configure Redis adapter in `event_service.py`:
   ```python
   from socketio import AsyncRedisManager
   redis_manager = AsyncRedisManager('redis://redis:6379')
   sio = socketio.AsyncServer(client_manager=redis_manager)
   ```

## Security

- Connections require authentication (user_id in auth data)
- Users can only broadcast to themselves (unless superuser)
- Each user auto-joins room `user_{user_id}`
- CORS restricted to configured origins
