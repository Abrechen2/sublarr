# Reverse Proxy Setup

Sublarr runs on port 5765 and works behind any reverse proxy. This guide covers Nginx and Traefik.

---

## Nginx

### Basic Setup (HTTP)

```nginx
server {
    listen 80;
    server_name sublarr.example.com;

    location / {
        proxy_pass http://sublarr:5765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support (required for real-time updates)
    location /socket.io/ {
        proxy_pass http://sublarr:5765/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

### With SSL (Certbot / Let's Encrypt)

```nginx
server {
    listen 443 ssl;
    server_name sublarr.example.com;

    ssl_certificate     /etc/letsencrypt/live/sublarr.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sublarr.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Increase timeouts for large subtitle file uploads
    client_max_body_size 50M;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    location / {
        proxy_pass http://sublarr:5765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /socket.io/ {
        proxy_pass http://sublarr:5765/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 86400;
    }
}

# HTTP -> HTTPS redirect
server {
    listen 80;
    server_name sublarr.example.com;
    return 301 https://$host$request_uri;
}
```

### Subpath Setup

If you need Sublarr under a subpath (e.g., `/sublarr/`):

```nginx
location /sublarr/ {
    proxy_pass http://sublarr:5765/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Prefix /sublarr;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /sublarr/socket.io/ {
    proxy_pass http://sublarr:5765/socket.io/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}
```

---

## Traefik v2 / v3

### Docker Labels

Add these labels to your Sublarr service in `docker-compose.yml`:

```yaml
services:
  sublarr:
    image: ghcr.io/abrechen2/sublarr:0.11.0-beta
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.sublarr.rule=Host(`sublarr.example.com`)"
      - "traefik.http.routers.sublarr.entrypoints=websecure"
      - "traefik.http.routers.sublarr.tls.certresolver=letsencrypt"
      - "traefik.http.services.sublarr.loadbalancer.server.port=5765"
      # WebSocket upgrade (required for Socket.IO)
      - "traefik.http.middlewares.sublarr-ws.headers.customrequestheaders.X-Forwarded-Proto=https"
    networks:
      - traefik_network
      - sublarr_net
```

### Static Traefik Configuration (traefik.yml)

Ensure WebSocket support is enabled:

```yaml
entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"
```

---

## Authentik / Authelia (SSO)

To add SSO in front of Sublarr:

### Nginx Proxy Manager + Authelia

1. Configure NPM with the Authelia forward auth URL
2. Set up an Authelia bypass rule for the API (if using the API from scripts):
   ```yaml
   bypass:
     - domain: sublarr.example.com
       resources:
         - "^/api/v1/.*$"
   ```
3. Sublarr's own API key auth (`SUBLARR_API_KEY`) still applies to API calls

### Important: WebSocket Exclusion

Always exclude `/socket.io/` from SSO forward auth — SSO middleware often strips WebSocket upgrade headers, breaking real-time updates.

---

## API Key Authentication

When Sublarr is accessible from the internet, always set `SUBLARR_API_KEY`:

```
SUBLARR_API_KEY=your_secret_key_here
```

All API endpoints will then require the `X-Api-Key: your_secret_key_here` header. The web UI handles this automatically when you enter the API key in Settings.

---

## Unraid Nginx Proxy Manager

Unraid users with Nginx Proxy Manager:

1. Add a new Proxy Host
2. Domain: `sublarr.your-domain.com`
3. Scheme: `http`, Forward Hostname: container name or IP, Port: `5765`
4. Enable **Websockets Support** checkbox
5. Add SSL certificate (Let's Encrypt)

The **Websockets Support** checkbox in NPM adds the necessary upgrade headers automatically.

---

## Common Issues

### Real-time updates not working (activity feed frozen)

The WebSocket connection to `/socket.io/` is missing or blocked. Check:
- Nginx `Upgrade` and `Connection` headers are forwarded
- Traefik has the WebSocket middleware applied
- Proxy read timeout is at least 300 seconds

### 413 Request Entity Too Large

When uploading backup files or large subtitle files, increase the client body size:

```nginx
client_max_body_size 100M;
```

### 502 Bad Gateway after wake from sleep

Sublarr is running as a single Gunicorn worker (required for Socket.IO). It can take a few seconds to wake on the first request after inactivity. Increase proxy read timeout to 30s to avoid false 502 errors.
