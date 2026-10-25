# Release & Packaging Workflow

`bindmc` is distributed both as a PyPI Python package and as standalone native executables (Windows and Linux) bundled with PyInstaller.

---

## 1. Local Release Testing

To build and verify a release executable locally in an isolated environment (this only works on Linux):

```bash
./run_release.sh
```

The `./run_release.sh` script:
1. Cleans existing build caches (`dist/`, `build/`).
2. Builds wheel artifacts for `bindmc` and `bindtools`.
3. Sets up an isolated test virtual environment under `.release_env/`.
4. Installs the production wheels and launches the entry point.

---

## 2. Building PyPI Wheels

Build source distributions and wheels manually:

```bash
uv build
```

---

## 3. GitHub Actions Release Pipelines

The repository includes pre-configured GitHub Actions workflows:

- `.github/workflows/build-all.yml`: Builds standalone Linux binaries.
- `.github/workflows/build_win.yml`: Builds standalone Windows `.exe` executables.
- `.github/workflows/release-pypi.yml`: Publishes tagged releases to PyPI.
- `.github/workflows/docs.yml`: Builds and deploys documentation to GitHub Pages.
