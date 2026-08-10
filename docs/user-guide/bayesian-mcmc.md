# Bayesian MCMC Sampling

The **Bayes / MCMC** tab performs Markov Chain Monte Carlo sampling using `emcee` to sample the posterior probability distribution of model parameters, quantifying uncertainties and parameter correlations.

---

## 1. Prior Distributions & Parameter Bounds

In `bindmc`, parameters are assigned **Uniform priors** bounded by lower and upper limits $[a, b]$:

$$P(\theta) = \begin{cases} \frac{1}{b - a} & \text{if } a \le \theta \le b \\ 0 & \text{otherwise} \end{cases}$$

Parameter bounds (e.g., restricting $\log_{10} K \in [0, 14]$ or limiting chemical shifts $\delta$) prevent non-physical regions of parameter space during sampling.

---

## 2. Heterogeneous Experimental Weighting (`lnsigma`)

When combining multiple data types or techniques (e.g. NMR chemical shifts in ppm vs. UV-Vis absorbance in AU vs. NMR peak integrations), measurement uncertainties and units differ significantly.

`bindmc` automatically creates and samples independent log-variance hyperparameters ($\ln \sigma$) for each experimental technique:
- `lnsigmadeltaH` (NMR $^1\text{H}$ shifts)
- `lnsigmadeltaF` (NMR $^{19}\text{F}$ shifts)
- `lnsigmaUVvis` (UV-Vis absorbance)
- `lnsigmaFluorescence` (Fluorescence intensity)
- `lnsigmaNMRInteg` (NMR peak integrations)

This ensures that heterogeneous datasets are appropriately weighted according to their individual noise characteristics without manual scaling.

---

## 3. Convergence Diagnostics ($\tau$)

- **Walkers**: Number of MCMC ensemble walkers (typically $32$ to $64$).
- **Integrated Autocorrelation Time ($\tau$)**: `bindmc` estimates the integrated autocorrelation time $\tau$ for each parameter chain. As a rule of thumb, sampling should run for at least $50 \times \tau$ steps to guarantee independent samples and converged chains.
- **Trace Plots**: Inspect parameter values vs. step index across all walkers. Converged chains resemble stable, stationary "hairy caterpillars" without long-term drift.

---

## 4. Exporting Notebooks & External Analysis

### Option A: Jupyter Notebook Export (Recommended)
Click **Export Notebook** in the top navigation header to download an executable `.ipynb` notebook alongside your `.h5` MCMC session. The exported notebook includes complete, pre-configured template plotting code using `arviz`, `corner`, and `matplotlib`.

### Option B: Custom Python Analysis Script
You can also inspect raw MCMC chains directly from exported `.h5` files in Python:

```python
import h5py
import numpy as np
import corner
import matplotlib.pyplot as plt

# 1. Open exported HDF5 session file
with h5py.File("mcmc_session.h5", "r") as f:
    chain = f["mcmc/chain"][:]        # Shape: (steps, walkers, n_params)
    log_prob = f["mcmc/log_prob"][:]  # Log posterior probabilities
    labels = [s.decode() if isinstance(s, bytes) else str(s) for s in f["mcmc"].attrs["labels"]]

# 2. Discard burn-in (e.g., first 200 steps) and flatten chains
burn_in = 200
flat_chain = chain[burn_in:].reshape(-1, chain.shape[-1])

# 3. Generate publication-ready Corner plot
fig = corner.corner(
    flat_chain,
    labels=labels,
    show_titles=True,
    quantiles=[0.16, 0.50, 0.84],
    title_fmt=".2f"
)
plt.savefig("mcmc_corner_plot.png", dpi=300, bbox_inches="tight")
plt.show()
```
