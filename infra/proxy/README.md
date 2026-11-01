# Public HTTPS ingress (TLS)

How to put the MTK RADAR dashboard behind TLS. The production compose file
publishes the dashboard **loopback-only**

```yaml
ports:
  - "127.0.0.1:3000:3000"
```

(infra/docker/docker-compose.yml), so nothing is exposed until you pick an
ingress. Two paths are supported; both end with the SAME three settings in
your env file (`infra/.env`):

```
MTK_PUBLIC_BASE_URL=https://radar.yourdomain.tld
MTK_CORS_ORIGINS=https://radar.yourdomain.tld
```

## Option A — Cloudflare Tunnel (recommended)

Matches the cost model in `docs/cost-laptop-vps-2026-10-22.md`: no open
inbound ports, no certificate renewal, no SSH-forward babysitting, and the
"server" can be a laptop behind NAT.

The `tunnel` service in infra/docker/docker-compose.tunnel.yml (kept OUT of
the base compose file on purpose) runs `cloudflare/cloudflared` inside the
compose network and routes
**container-to-container** — the dashboard needs no host port on the public
side at all.

Setup:

1. Cloudflare Zero Trust dashboard → **Networks → Tunnels → Create a tunnel**.
   Copy the tunnel token.
2. Put it in `infra/.env` as
   ```
   MTK_TUNNEL_TOKEN=<paste the token>
   ```
   (`.env`/`infra/.env` are gitignored; the token is a deployment secret.)
3. In the same dashboard add the public hostname mapping:
   `radar.yourdomain.tld` → **`http://dashboard:3000`** (compose service DNS).
   Add `http://api:8000` only if the API must be directly reachable — the
   dashboard already proxies browser traffic same-origin at `/api`, so
   normally you never do.
4. Start the tunnel (note the `--env-file`: compose resolves a bare `.env`
   from `infra/docker/`, where none exists):

   ```bash
   docker compose --env-file infra/.env \
     -f infra/docker/docker-compose.yml \
     -f infra/docker/docker-compose.tunnel.yml up -d tunnel
   ```
   (the overlay's `MTK_TUNNEL_TOKEN:?` guard fails loudly right here if the
   token is missing — that guard is in the overlay so it can never abort
   unrelated compose commands)

`scripts/deploy.sh` users: run the deploy first, then start the tunnel with
the command above; everything else in the stack is unchanged.

## Option B — host-side Caddy (auto-HTTPS via Let's Encrypt)

For a VPS where ports 80/443 can be open and you don't want Cloudflare in the
middle. Caddy runs **on the host**, obtains and renews certificates
automatically, and reverse-proxies to the loopback publish.

See `Caddyfile.example` in this directory (copy, set your hostname):

```bash
cp infra/proxy/Caddyfile.example infra/proxy/Caddyfile   # edit the hostname
caddy run --config infra/proxy/Caddyfile                 # or the systemd unit
```

Requirements: a DNS A record pointing at the host, and ports 80/443 allowed
through the host firewall. TLS secrets live in caddy's data directory — keep
them out of this repository.

## Which one?

|                          | Cloudflare Tunnel      | Caddy             |
| ------------------------ | ---------------------- | ----------------- |
| Open inbound ports       | none (dials out)       | 80 + 443          |
| Certificates             | Cloudflare edge        | Let's Encrypt     |
| Works behind NAT/laptop  | yes                    | no                |
| Extra moving parts       | the tunnel container  | caddy on the host |

Either way, review `docs/go-live-checklist.md` before serving real traffic.
