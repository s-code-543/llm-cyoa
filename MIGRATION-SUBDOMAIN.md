# Migration to Subdomain Architecture

## Overview

The CYOA system has been migrated from a path-based OpenWebUI proxy to a subdomain-based architecture with a dedicated chat interface.

## Architecture

- **https://openwebui.mac.stargate.lan** → OpenWebUI (legacy/testing)
- **https://cyoa.mac.stargate.lan** → Django CYOA app with integrated chat

## Changes Made

### 1. TLS Certificates
- Generated new certificates covering both subdomains
- Located in `./ssl/`
  - `openwebui+cyoa.pem`
  - `openwebui+cyoa-key.pem`

### 2. Nginx Configuration
- Single Nginx container handles both subdomains
- Two server blocks (one per subdomain)
- No port exposure for backend services
- Proxy buffering disabled for OpenWebUI streaming

### 3. Docker Compose
- Services communicate via internal `cyoa-network`
- OpenWebUI: exposed only via Nginx
- Django: exposed only via Nginx (debugpy still on 5678)
- All services use `expose` instead of `ports` for internal communication

### 4. Django Updates
- New models: `ChatConversation`, `ChatMessage`
- New views in `chat_views.py`
- Chat page at `/chat/` with full UI
- API endpoints:
  - `POST /chat/api/new` - Create conversation
  - `POST /chat/api/send` - Send message
  - `GET /chat/api/conversation/<id>` - Get conversation
  - `GET /chat/api/conversations` - List conversations
- Settings updated:
  - `ALLOWED_HOSTS` includes `cyoa.mac.stargate.lan`
  - `SECURE_PROXY_SSL_HEADER` for SSL awareness

### 5. Chat Interface
- Integrated into existing admin layout
- UUID-based conversations
- JSON metadata storage
- No authentication required (for now)
- Uses active configuration's storyteller model
- Tailwind CSS + Alpine.js frontend
- Real-time message history

## Deployment Steps

```bash
# From project root
cd /Users/yolo/openwebui-cyoa

# Stop existing containers
docker compose -f docker-compose.mac.yml down

# Create database migrations
docker compose -f docker-compose.mac.yml run --rm cyoa-game-server python manage.py makemigrations

# Build with new changes
docker compose -f docker-compose.mac.yml build

# Start services
docker compose -f docker-compose.mac.yml up -d

# Run migrations
docker compose -f docker-compose.mac.yml exec cyoa-game-server python manage.py migrate

# Check status
docker compose -f docker-compose.mac.yml ps
docker compose -f docker-compose.mac.yml logs -f cyoa-game-server
```

## DNS Configuration

Ensure your `/etc/hosts` or local DNS includes:

```
<your-mac-ip> openwebui.mac.stargate.lan
<your-mac-ip> cyoa.mac.stargate.lan
```

## Testing

1. Visit https://cyoa.mac.stargate.lan
2. Should redirect to `/chat/`
3. Click "New Chat" to start a conversation
4. Send a message - it will use the active configuration's storyteller model
5. Admin interface still available at https://cyoa.mac.stargate.lan/admin/

## Benefits

- **Independent routing**: Each service has its own clean domain
- **Better metadata**: Conversations stored with UUIDs and JSON metadata
- **No OpenWebUI constraints**: Full control over chat UX
- **Flexible storage**: Can add inventory, game state, etc. to conversation metadata
- **Clean URLs**: No more subpath hacks
- **Future streaming support**: Architecture ready for SSE/WebSocket streaming

## Next Steps

- [ ] Add conversation list/history view
- [ ] Implement inventory/game state tracking
- [ ] Add Whisper.cpp integration for voice input
- [ ] Implement real-time streaming responses
- [ ] Add authentication/user sessions
- [ ] Migrate existing OpenWebUI conversations (if needed)
