# Notebook Export & Reproducibility

`bindmc` emphasizes open science and complete analytical reproducibility. At any point in your workflow, you can export your session to a standalone, executable **Jupyter Notebook (`.ipynb`)**.

---

## How to Export

1. Complete your data import, model setup, and/or non-linear fitting in the `bindmc` web GUI.
2. In the top navigation header, click **Export Notebook**.
3. Save the generated `.ipynb` file to your local computer.

---

## What the Exported Notebook Contains

The exported Jupyter Notebook is completely self-contained and standalone:

- **Raw Data Ingestion**: Recreates the experimental titration data arrays directly in Python code.
- **Stoichiometry Matrix**: Reconstructs the equilibrium species equations and stoichiometry matrix.
- **`bindtools` API Invocation**: Imports `bindtools` and sets up `lmfit` minimization parameters matching your exact GUI state.
- **Publication-Ready Figures**: Generates high-resolution Matplotlib figure code for titration fit curves, residual plots, speciation diagrams, and corner plots.

---

## Running the Exported Notebook

Open the notebook in Jupyter Lab, VS Code, or Google Colab:

```bash
jupyter lab my_bindmc_fit.ipynb
```

Executing all cells reproduces your exact numerical fitting results, standard errors, and plots independently of the GUI application.
