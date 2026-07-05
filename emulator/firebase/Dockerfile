FROM node:26-trixie-slim

# Install Java and other dependencies (required for Firebase emulators).
# firebase-tools >=14 requires a JDK >= 21. node:26-trixie-slim is Debian
# 13 (trixie), whose main repo ships openjdk-21 directly -- Debian 12
# (bookworm) only has openjdk-17 and bookworm-backports carries no
# openjdk-21, so the trixie base avoids any extra apt source.
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install Firebase CLI with specific version for stability
RUN npm install -g firebase-tools@15.22.3 && \
    firebase --version

WORKDIR /firebase

# Copy configuration files
COPY firebase.json ./
COPY firestore.rules ./
COPY firestore.indexes.json ./
COPY storage.rules ./
COPY remoteconfig.template.json ./

# Create data directory
RUN mkdir -p data

# Expose emulator ports
EXPOSE 9099 8080 9399 9199 9299 9499 4000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:4000 || exit 1

# Default command (can be overridden by docker-compose). firebase-tools
# 15 removed the `--host` flag; the emulator host binding (0.0.0.0) now
# comes from firebase.json's per-emulator `host` fields.
CMD ["firebase", "emulators:start"]