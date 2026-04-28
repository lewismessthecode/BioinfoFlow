# syntax=docker/dockerfile:1.7
# ── Stage 1: Install dependencies ─────────────────────────────
FROM node:22-slim AS deps
WORKDIR /app

RUN npm install -g bun

COPY package.json bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

# ── Stage 2: Build ────────────────────────────────────────────
FROM node:22-slim AS builder
WORKDIR /app

RUN npm install -g bun

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time env vars — baked into the JS bundle by Next.js.
# Changing these requires a rebuild (docker compose up -d --build).
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
ARG NEXT_PUBLIC_AUTH_MODE=personal
ARG NEXT_PUBLIC_AUTH_LOCAL_ENABLED=true
ARG NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED=false

ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE
ENV NEXT_PUBLIC_AUTH_LOCAL_ENABLED=$NEXT_PUBLIC_AUTH_LOCAL_ENABLED
ENV NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED=$NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED

# Ensure better-sqlite3 native bindings match this Node version
RUN node scripts/ensure-better-sqlite3-node-abi.mjs

RUN bun run build

# ── Stage 3: Production runner ────────────────────────────────
FROM node:22-slim AS runner
WORKDIR /app

ENV NODE_ENV=production

# Copy Next.js standalone output (requires output: "standalone" in next.config.mjs)
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# i18n message bundles (next-intl)
COPY --from=builder /app/messages ./messages
COPY --from=builder /app/scripts/with-root-env.mjs ./scripts/with-root-env.mjs

# better-sqlite3 native addon — required at runtime for Better Auth
COPY --from=builder /app/node_modules/better-sqlite3 ./node_modules/better-sqlite3
COPY --from=builder /app/node_modules/bindings ./node_modules/bindings
COPY --from=builder /app/node_modules/file-uri-to-path ./node_modules/file-uri-to-path

# Strip sourcemaps: Next.js standalone ships server-side .js.map files that
# recover readable code. Customer-delivered images should not include them.
RUN find . -type f -name "*.map" -delete

EXPOSE 3000

CMD ["node", "scripts/with-root-env.mjs", "start"]
