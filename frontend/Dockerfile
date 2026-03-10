# Multi-stage build: build the React app, then copy dist to a volume
# The nginx container serves the files, so this container just produces the build output

# Stage 1: Build the frontend
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (layer caching)
COPY package.json package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install

# Copy source and build
COPY . .
RUN npm run build

# Stage 2: Copy dist to a minimal image that exits after copying
# The volume mount at /app/dist will persist the build output for nginx
FROM alpine:3.20

# Copy the built files to /build (not /app/dist, which is where the volume is mounted)
COPY --from=builder /app/dist /build/dist

# This container's sole purpose is to populate the frontend_build volume.
# Volume is mounted at /app/dist; we copy from /build/dist into it and exit.
CMD ["sh", "-c", "cp -r /build/dist/. /app/dist/"]
