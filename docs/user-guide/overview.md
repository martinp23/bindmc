# User Guide Overview

`bindmc` provides an intuitive web interface built on NiceGUI. All session state is automatically saved locally in browser storage so your work is preserved across browser refreshes.

---

## Application Navigation Layout

```
+-----------------------------------------------------------------------------------+
|  bindmc  [ Model: Default ] [ New Model ] [ Export Notebook ] [ Load Session ]    |
+-----------------------------------------------------------------------------------+
|  [ Binding Model ] [ Data Import ] [ Fitting ] [ Bayes / MCMC ] [ Simulation ]    |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|                              Active Workspace Panel                               |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

### Top Navigation Header
- **Active Model Selector**: Switch between different active binding models within the same session.
- **New Model Button**: Create a new model configuration from default templates.
- **Export Jupyter Notebook**: Download the complete model, imported data, fitting setup, and MCMC pipeline as an offline `.ipynb` notebook.
- **Save / Load Session**: Export/Import the entire session state as JSON.

### Primary Workspace Tabs

1. **Binding Model**:
   - Define chemical components (Host, Guest, Metal, etc.).
   - Enter equilibrium equations or select fast-exchange analytical models.
   - Set initial log10($K$) guesses and physical property parameters.
2. **Data Import**:
   - Upload titration data files (CSV, XLSX).
   - Assign independent variables (total concentrations) and dependent variables (NMR shifts, UV-vis absorbance).
3. **Fitting**:
   - Perform non-linear curve fitting using Levenberg-Marquardt or L-BFGS-B via `lmfit`.
   - Inspect fitted parameters, standard errors, $R^2$, residual plots, and species speciation curves.
4. **Bayes / MCMC**:
   - Configure Markov Chain Monte Carlo sampling with `emcee`.
   - Set parameter priors (Uniform, Gaussian, Log-Normal).
   - View chain trace plots and corner plots (`corner.py`).
5. **Simulation**:
   - Generate synthetic titration data with added Gaussian noise to evaluate model sensitivity and design optimal titration experiments.
