# AcademiaGPT v2 - Frontend Dockerfile
# Next.js 16 with standalone output

ARG NODE_IMAGE=node:20-alpine
ARG NPM_REGISTRY=https://registry.npmjs.org

# ============================================
# Dependencies Stage
# ============================================
FROM ${NODE_IMAGE} AS deps

ARG NPM_REGISTRY

# Check https://github.com/nodejs/docker-node/tree/b4117f9333da4138b03a546ec926ef50a31506c3#nodealpine
# for compatible version of libc6-compat
RUN apk add --no-cache libc6-compat

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install all dependencies for build (dev deps are required by next build)
RUN npm config set registry "${NPM_REGISTRY}"
RUN npm ci

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
