# Contributing to bindmc

## Development Environment

- **OS**: Linux is preferred, and the ./run_release.sh script (below) assumes it.
- **IDE**: VS Code (or equivalent) is recommended. A debug configuration is provided in `.vscode/launch.json`.

## Development Setup

This project uses [`uv`](https://github.com/astral-sh/uv) for environment management.

1. Clone the repository:
   ```bash
   git clone https://github.com/martinp23/bindmc.git
   cd bindmc
   ```
2. Create the virtual environment and install all dependencies:
   ```bash
   uv sync
   ```

## Linting and Formatting

This project uses `ruff`. Run the following commands to check and format:

```bash
# Check lint rules
uv run ruff check .

# Format code
uv run ruff format .
```

## Testing

Run tests with `pytest`:

```bash
uv run pytest
```

## Building and Releases

### Local Release Testing
To build and run a release version in an isolated environment (replicating how the production executable runs), execute:

```bash
./run_release.sh
```

This script:
1. Cleans previous builds.
2. Builds production wheels for `bindmc` and `bindtools`.
3. Sets up an isolated environment under `.release_env`.
4. Installs the production wheels and runs the main application entry point.

### Building Package Artifacts
To build source distributions and wheels manually:

```bash
uv build
```