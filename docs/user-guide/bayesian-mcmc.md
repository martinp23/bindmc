# Bayesian MCMC Sampling

The **Bayes / MCMC** tab performs Markov Chain Monte Carlo sampling using `emcee` to sample the full posterior probability distribution of model parameters, quantifying uncertainties and parameter correlations.

---

## 1. Prior Probability Distributions

Bayes' theorem relates the posterior probability $P(\theta \mid D)$ of parameters $\theta$ given data $D$:

$$P(\theta \mid D) \propto P(D \mid \theta) \cdot P(\theta)$$

In `bindmc`, you can assign independent prior distributions $P(\theta)$ to each parameter:

- **Uniform Prior**: Equal probability over specified $[a, b]$ bounds.
- **Gaussian (Normal) Prior**: Centered around mean $\mu$ with standard deviation $\sigma$.
- **Log-Normal Prior**: Useful for strictly positive physical quantities.

---

## 2. MCMC Configuration

- **Walkers**: Number of MCMC ensemble walkers (typically $32$ to $64$).
- **Steps**: Number of iterations per walker (e.g. $1000$ to $5000$).
- **Burn-in**: Number of initial steps to discard before sample collection (e.g. $200$ steps).

---

## 3. Results & Plots

### Trace Plot
Plots parameter values vs. step index for each walker.
- **Convergence Check**: Chains should resemble "hairy caterpillars" randomly oscillating around stable values without drift.

### Corner Plot
Generates a 2D corner plot using `corner.py` and `arviz`:
- **1D Histograms**: Diagonal panels show 1D marginal posterior probability density functions with median and $16^{\text{th}}/84^{\text{th}}$ percentile confidence intervals.
- **2D Contour Plots**: Off-diagonal panels reveal non-linear correlations and covariance between binding constants and chemical shift parameters.

---

## 4. Saving Sessions

MCMC sampling states and full chain arrays can be exported to binary **HDF5 (`.h5`)** files for long-term archiving or downstream analysis with ArviZ.
