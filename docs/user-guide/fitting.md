# Non-Linear Fitting

The **Fitting** tab optimizes binding constants ($\log_{10} K$) and physical observable parameters (e.g. chemical shifts $\delta$, extinction coefficients $\varepsilon$) against imported titration data using `lmfit`.

---

## 1. Minimizer Algorithm Selection

`bindmc` provides access to several optimization algorithms depending on model complexity and parameter conditioning:

| Algorithm Name | Method Key in `lmfit` | Recommended Usage |
|---|---|---|
| **Levenberg-Marquardt** (Default) | `least_squares` / `lm` | Standard non-linear least squares. Fastest convergence for well-behaved problems with smooth gradients. |
| **L-BFGS-B** | `lbfgsb` | Bounded quasi-Newton optimization. Ideal when strict parameter bounds are required and gradient evaluation is cheap. |
| **Nelder-Mead** | `nelder-mead` | Simplex direct-search method. Gradient-free optimization useful when residual landscapes are noisy or non-smooth. |
| **AMPGO** | `ampgo` | Adaptive Memory Programming for Global Optimization. Useful for exploring complex multimodal parameter spaces with multiple local minima. |

---

## 2. Weighting & Technique-Specific Errors

When fitting single data series, residuals are evaluated as:

$$\text{residual}_i = \frac{y_{\text{exp}, i} - y_{\text{fit}, i}}{\sigma}$$

- **Single Dataset Weighting**: For single-technique fits, uniform weighting ($\sigma = 1$) optimizes unweighted sum of squared residuals.
- **Heterogeneous Data**: Note that when combining multiple experimental techniques (e.g., NMR ppm shifts alongside UV-Vis absorbance), each technique operates on different units and scales. In `bindmc`, technique-specific error variance parameters ($\ln \sigma$) are modeled explicitly during **Bayesian MCMC sampling** to prevent larger numerical units from dominating the optimization.

---

## 3. Parameter Constraints & Bounds

- **Initial Guesses**: Enter starting estimates for $\log_{10} K$ values (e.g. $3.5$ for $K \approx 3,160 \text{ M}^{-1}$).
- **Vary / Fix Flags**: Toggle checkboxes to hold known parameters fixed (e.g., free host chemical shift $\delta_{\text{H}}$ measured independently prior to titration).
- **Lower / Upper Bounds**: Restrict parameter ranges to physically meaningful bounds (e.g., $\log_{10}K \ge 0$).

---

## 4. Fitting Diagnostics & Troubleshooting

After optimization completes, `bindmc` displays parameter standard errors ($1\sigma$) and correlation coefficients:

### High Parameter Correlation ($r > 0.95$)
- **Cause**: Strong correlation between two parameters (e.g. binding constant $\log_{10} K$ and bound complex chemical shift $\delta_{\text{HG}}$ in weak binding regimes where $K [\text{H}]_{\text{tot}} \ll 1$).
- **Solution**: Measure the free component property ($\delta_{\text{H}}$ or $\varepsilon_{\text{H}}$) independently and fix it in the model, or increase maximum titrant concentration to reach saturation.

### Non-Convergence or Boundary Clipping
- **Symptom**: Parameter pegged exactly at lower or upper bound, or high standard errors ($> 100\%$).
- **Solution**: Try switching minimizer to `nelder-mead` or `ampgo` to escape local minima, or expand parameter bounds.
