# Welcome to `bindmc` Documentation

[![PyPI version](https://badge.fury.io/py/bindmc.svg)](https://badge.fury.io/py/bindmc)
[![Python Version](https://img.shields.io/pypi/pyversions/bindmc.svg)](https://pypi.org/project/bindmc/)

**`bindmc`** is a Python application and scientific toolkit for modeling, fitting, and analyzing supramolecular chemical binding equilibria. Built on top of **`bindtools`**, it provides both an interactive, state-persisted NiceGUI web interface and a robust computational backend.

---

## Key Features

- 🧪 **Speciation Solvers**:
  - **Numerical**: JIT-compiled Numba Newton–Raphson equilibrium solver (`DoNR`) for arbitrary chemical stoichiometries.
  - **Analytical**: High-speed analytical solutions for standard binding models (e.g. $1:1$, $1:2$, $2:1$ fast exchange).
- 📊 **Experimental Data Support**:
  - NMR chemical shifts ($\delta_{\text{H}}$, $\delta_{\text{F}}$).
  - Absorbance and Fluorescence spectroscopy.
  - NMR integration peak areas.
- 🎯 **Parameter Optimization**:
  - Non-linear least squares optimization using `lmfit`.
  - Flexible constraints, fixed parameters, and parameter bounds.
- 🎲 **Bayesian Inference & Uncertainty**:
  - MCMC sampling with `emcee` for complete posterior distribution estimation.
  - Interactive trace plots and corner plots via `corner` and `arviz`.
  - Full session serialization to HDF5 files.
- 📓 **Open Science & Reproducibility**:
  - Export complete fitting sessions directly to standalone, executable **Jupyter Notebooks (`.ipynb`)** for publication supplementary data.

---

## Quick Navigation

<div class="grid cards" markdown>

-   :rocket: __[Getting Started](getting-started/index.md)__
    
    Installation instructions for pre-built binaries, pip, and uv environment setup.

-   :book: __[User Guide](user-guide/overview.md)__
    
    Step-by-step documentation for importing data, building models, fitting, MCMC, and exporting.

-   :gear: __[API Reference](api-reference/bindtools.md)__
    
    Complete docstrings and signatures for `bindtools` core solvers and `bindmc` GUI state components.

-   :code: __[Developer Guide](developer-guide/architecture.md)__
    
    Architecture diagrams, state manager details, testing instructions, and release workflows.

</div>
