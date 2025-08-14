# Project Overview

This is a dotfiles repository for managing personal development environment configurations. It includes setup scripts, Makefile targets for various tasks (installation, updates, checks, cloud connections), and a comprehensive Docker Compose setup for local emulators of various cloud services and databases (Firebase, Spanner, Neo4j, Qdrant, Elasticsearch). It leverages `mise` for version management, `uv` for Python package management, `pnpm` for Node.js package management, and `dotenvx` for environment variable management.

## Building and Running

### Initial Setup

To set up the dotfiles on a new machine, execute the `install.sh` script:

```bash
bash -c "$(curl -L raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"
```

This script clones the repository, installs Homebrew and Google Cloud SDK, and then runs `make add-all`, `make update-all`, `make clean`, and `make deploy` to configure the environment.

### General Tasks (using `make`)

The primary task runner for this project is `Makefile`. You can see a list of available commands by running `make help`. Some key commands include:

*   `make install`: Installs repository requirements using `mise`.
*   `make deploy`: Creates symlinks to the home directory (e.g., `.zshrc`).
*   `make clean`: Removes dotfiles from your home directory.
*   `make dump`: Dumps the current Homebrew bundle to `dump/Brewfile`.
*   `make freeze`: Freezes current Python packages using `uv`.
*   `make add-all`: Installs all dependencies (Homebrew, Google Cloud SDK components, pnpm global packages).
*   `make update-all`: Updates all dependencies (Google Cloud SDK, Homebrew, pnpm global packages, mise, gh extensions, tldr, gitignore).
*   `make check-*`: Various commands to check system configurations (e.g., `check-path`, `check-myip`, `check-dockerport`, `check-brew`, `check-gcloud`, `check-npm-g`, `check-pnpm-g`, `check-rust`).
*   `make connect-*`: Connects to cloud services or local emulators (e.g., `connect-gcloud-sql`, `connect-azurite`).
*   `make check-version-*`: Checks specific software versions (e.g., `check-version-nvcc`, `check-version-torch`).

### Emulator Management

The `emulator` directory contains a `docker-compose.yaml` file for setting up various local emulators.

*   **Starting Emulators:**
    You can start the emulators by navigating to the `emulator` directory and running:
    ```bash
    docker compose up -d
    ```
    (There are also `start-emulators.sh` and `stop-emulators.sh` scripts in the `emulator` directory, which likely wrap these Docker Compose commands.)
*   **Python Environment (within `emulator`):**
    The `emulator/pyproject.toml` defines Python dependencies. To install them, use `uv`:
    ```bash
    cd emulator
    uv sync
    ```
    Tests for the emulators are located in `emulator/tests/` and can be run using `pytest`. Linting is handled by `ruff`.

## Development Conventions

*   **Task Runner:** Primarily uses `Makefile` for automation. `just` is also present but used for fewer tasks.
*   **Version Management:** `mise` is used for managing various tool versions (e.g., Node.js, Python, Go).
*   **Package Management:**
    *   `pnpm` for Node.js packages.
    *   `uv` for Python packages.
    *   Homebrew for system-level packages on macOS/Linux.
*   **Environment Variables:** `dotenvx` is used for managing encrypted environment variables.
*   **Testing:** Python tests are written using `pytest` within the `emulator/tests` directory.
*   **Linting:** `ruff` is used for Python code linting.
*   **Shell Configuration:** `.zshrc` is managed as part of the dotfiles, with deployment handled by `make deploy`.
