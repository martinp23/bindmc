#!/usr/bin/env bash
set -e

echo "1. Cleaning old builds..."
rm -rf dist/ .release_env/

echo "2. Building production wheels..."
uv build
cd bindtools
uv build
cd ..

echo "3. Creating isolated release environment..."
uv venv .release_env
source .release_env/bin/activate

echo "4. Installing production artifacts..."

uv pip install bindtools/dist/*.whl
uv pip install dist/*.whl

echo "5. Executing release script..."
# We use 'uv run --no-project' to explicitly force python to use the 
# active environment and ignore the local pyproject.toml paths.
uv run --no-project src/bindmc/main.py
