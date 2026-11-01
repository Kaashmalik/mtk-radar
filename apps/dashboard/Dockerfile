# Production dashboard image — standalone Next.js server, no runtime installs.
#
# The dashboard server talks to the API over the compose network and attaches
# the signed reviewer session / service token server-side. Nothing here is
# needed in the browser bundle.
#
# next.config.ts sets output: "standalone", so `next build` emits a traced,
# self-contained server graph in apps/dashboard/.next/standalone that mirrors
# the workspace root (node_modules/ at the top, server.js + .next under
# apps/dashboard/). This runtime image ships only that graph plus the static
# chunks, which the standalone server does NOT copy by itself (official
# Next.js standalone Docker pattern).
#
# Build context is the REPO ROOT (workspace files are COPYd from here). Keep a
# root-level .dockerignore in place — .git, node_modules, apps/dashboard/.next,
# storage/ and venv/ among others — so context uploads stay small and no local
# artifact can leak into an immutable build.

FROM node:22-alpine AS build
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app

# Install from the lockfile only; a dependency change requires a lockfile
# change, so an image can never silently drift from `pnpm verify`.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/offer-schema/package.json packages/offer-schema/
COPY apps/dashboard/package.json apps/dashboard/
RUN pnpm install --frozen-lockfile

COPY packages/offer-schema packages/offer-schema
COPY apps/dashboard apps/dashboard
RUN pnpm --dir apps/dashboard build

FROM node:22-alpine AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -S mtk && adduser -S mtk -G mtk
WORKDIR /app

# The traced standalone graph mirrors the workspace root:
#   node_modules/  +  apps/dashboard/{server.js,.next/server files}
COPY --from=build --chown=mtk:mtk /app/apps/dashboard/.next/standalone ./
# Static chunks are served BY server.js but not traced INTO it — copy them to
# the mirrored app dir. (There is no apps/dashboard/public to copy; if one is
# ever added, also `COPY ... apps/dashboard/public ./apps/dashboard/public`.)
COPY --from=build --chown=mtk:mtk /app/apps/dashboard/.next/static ./apps/dashboard/.next/static

USER mtk
EXPOSE 3000

# node:22-alpine ships busybox wget — enough for the liveness probe. The
# existing /api/health route is deliberately unauthenticated and side-effect
# free: it proves the Next server accepts connections, never that the API or
# database is healthy (the dashboard renders those states honestly instead).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -q -O /dev/null "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["node", "apps/dashboard/server.js"]
