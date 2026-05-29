# Firebase Emulator Docker Setup

This directory contains the Firebase emulator configuration for local development.

## Quick Start

1. Start the Firebase emulators:

   ```bash
   docker compose up -d
   ```

2. The following services will be available:
   - Auth: <http://localhost:9099>
   - Firestore: <http://localhost:8080>
   - Storage: <http://localhost:9199>
   - Pub/Sub: <http://localhost:9399>
   - Eventarc: <http://localhost:9299>
   - Cloud Tasks: <http://localhost:9499>
   - Emulator UI: <http://localhost:4000>

3. To stop the emulators:

   ```bash
   docker compose down
   ```

## Configuration

- `firebase.json`: Main Firebase configuration
- `firestore.rules`: Firestore security rules
- `firestore.indexes.json`: Firestore indexes
- `storage.rules`: Storage security rules
- `remoteconfig.template.json`: Remote config template
- `data/`: Emulator data (persisted between runs)

## Environment Variables

The application should use these environment variables to connect to the emulators:

```bash
export FIREBASE_AUTH_EMULATOR_HOST=localhost:9099
export FIRESTORE_EMULATOR_HOST=localhost:8080
export FIREBASE_STORAGE_EMULATOR_HOST=localhost:9199
export PUBSUB_EMULATOR_HOST=localhost:9399
export CLOUD_TASKS_EMULATOR_HOST=localhost:9499
export EVENTARC_EMULATOR_HOST=localhost:9299
```

Or source the provided `.env.firebase` file:

```bash
source ../.env.firebase
```

## Data Persistence

The emulator data is stored in the `data/` directory and persisted between container restarts. To reset the data, delete the contents of this directory.
