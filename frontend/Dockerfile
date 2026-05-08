# Wenjin (问津) - Frontend Dockerfile
# Next.js 16 with standalone output

ARG NODE_IMAGE=node:24-alpine
ARG ALPINE_MIRROR=
ARG NPM_REGISTRY=https://registry.npmjs.org
ARG NPM_FALLBACK_REGISTRY=https://registry.npmjs.org
ARG NPM_FETCH_RETRIES=5
ARG NPM_FETCH_RETRY_MINTIMEOUT=20000
ARG NPM_FETCH_RETRY_MAXTIMEOUT=120000
ARG NPM_FETCH_TIMEOUT=300000

# ============================================
# Dependencies Stage
# ============================================
FROM ${NODE_IMAGE} AS deps

ARG ALPINE_MIRROR
ARG NPM_REGISTRY
ARG NPM_FALLBACK_REGISTRY
ARG NPM_FETCH_RETRIES
ARG NPM_FETCH_RETRY_MINTIMEOUT
ARG NPM_FETCH_RETRY_MAXTIMEOUT
ARG NPM_FETCH_TIMEOUT

# Check https://github.com/nodejs/docker-node/tree/b4117f9333da4138b03a546ec926ef50a31506c3#nodealpine
# for compatible version of libc6-compat
RUN set -eux; \
    if [ -n "${ALPINE_MIRROR}" ]; then \
      sed -i "s|https://dl-cdn.alpinelinux.org/alpine|${ALPINE_MIRROR%/}|g" /etc/apk/repositories; \
      sed -i "s|http://dl-cdn.alpinelinux.org/alpine|${ALPINE_MIRROR%/}|g" /etc/apk/repositories; \
    fi; \
    apk add --no-cache libc6-compat

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install all dependencies for build (dev deps are required by next build)
RUN --mount=type=cache,target=/root/.npm \
    set -eux; \
    npm config set fetch-retries "${NPM_FETCH_RETRIES}"; \
    npm config set fetch-retry-mintimeout "${NPM_FETCH_RETRY_MINTIMEOUT}"; \
    npm config set fetch-retry-maxtimeout "${NPM_FETCH_RETRY_MAXTIMEOUT}"; \
    npm config set fetch-timeout "${NPM_FETCH_TIMEOUT}"; \
    npm config set fund false; \
    npm config set audit false; \
    npm config set prefer-offline true; \
    npm config set registry "${NPM_REGISTRY}"; \
    if npm ci --no-progress; then \
      exit 0; \
    fi; \
    if [ "${NPM_FALLBACK_REGISTRY}" = "${NPM_REGISTRY}" ]; then \
      echo "npm ci failed and fallback registry equals primary: ${NPM_REGISTRY}"; \
      exit 1; \
    fi; \
    echo "npm ci failed with ${NPM_REGISTRY}, retrying with fallback ${NPM_FALLBACK_REGISTRY}"; \
    npm config set registry "${NPM_FALLBACK_REGISTRY}"; \
    npm ci --no-progress

# ============================================
# Builder Stage
# ============================================
FROM ${NODE_IMAGE} AS builder

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy source code
COPY . .
RUN mkdir -p public

# Set environment variables for build
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

# Build the application
# This will generate standalone output in .next/standalone
RUN npm run build

# ============================================
# Runner Stage - Production
# ============================================
FROM ${NODE_IMAGE} AS runner

WORKDIR /app

# Set environment to production
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built application (standalone mode)
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Set correct ownership
RUN chown -R nextjs:nodejs /app

# Switch to non-root user
USER nextjs

# Expose port
EXPOSE 3000

# Set port
ENV PORT=3000 \
    HOSTNAME="0.0.0.0"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:3000 || exit 1

# Start the server
CMD ["node", "server.js"]
