# Getting Started

`bindmc` can be used either as a desktop/web GUI application or as a Python package.

---

## Installation Options

### Option 1: Standalone Pre-built Executable (Recommended for non-programmers)

No Python installation is required to run the pre-built desktop application.

1. Navigate to the **[bindmc Releases](https://github.com/martinp23/bindmc/releases)** page on GitHub.
2. Download the executable for your operating system:
   - Linux: `bindmc` executable
   - Windows: `bindmc.exe`
3. Double-click or run the executable in your terminal. The app will launch in your browser or native web window.

---

### Option 2: Installation via Pip

If you have Python 3.12 or higher installed:

```bash
pip install bindmc
```

To launch the graphical application after installing via pip:

```bash
python -m bindmc
```

---

### Option 3: Developer Setup with `uv`

For developers contributing to `bindmc` or `bindtools`:

```bash
# 1. Clone the repository with submodules
git clone https://github.com/martinp23/bindmc.git
cd bindmc

# 2. Synchronize environment and install dependencies
uv sync

# 3. Run the application
uv run python src/bindmc/main.py
```

---

## Quick Workflow Summary

1. Launch `bindmc` via standalone binary, `python -m bindmc`, or `python main.py`.
2. Go to **Binding Models** to enter stoichiometric equilibrium equations (e.g., `H + G <=> HG`).
3. Navigate to **Data Import** to load titration data (CSV/Excel).
4. Select **Fitting** to optimize binding constants ($K$) and physical parameters ($\delta$).
5. Run **Bayesian MCMC** to generate posterior probability distributions and corner plots.
6. Click **Export Notebook** in the header to download a reproducible `.ipynb` Jupyter notebook.
