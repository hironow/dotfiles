FROM node:24-slim

# Install Java and other dependencies (required for Firebase emulators)
RUN apt-get update && apt-get install -y \
    openjdk-17-jre-headless \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install Firebase CLI with specific version for stability
RUN npm install -g firebase-tools@13.0.2 && \
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

# Default command (can be overridden by docker-compose)
CMD ["firebase", "emulators:start", "--host", "0.0.0.0"]