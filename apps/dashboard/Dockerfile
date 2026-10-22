# Production dashboard image — immutable build, no runtime package installs.
#
# The dashboard server talks to the API over the compose network and attaches
# the signed reviewer session / service token server-side. Nothing here is
# needed in the browser bundle.

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
    PORT=3000
RUN addgroup -S mtk && adduser -S mtk -G mtk
WORKDIR /app

COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json /app/pnpm-workspace.yaml ./
COPY --from=build /app/packages ./packages
COPY --from=build /app/apps/dashboard ./apps/dashboard

USER mtk
EXPOSE 3000
WORKDIR /app/apps/dashboard
CMD ["node", "node_modules/next/dist/bin/next", "start", "-p", "3000"]
