# Non-Linear Fitting

The **Fitting** tab optimizes binding constants ($\log_{10} K$) and physical observable parameters (e.g. chemical shifts $\delta$) against imported titration data using non-linear least squares minimization via `lmfit`.

---

## Fitting Configuration Steps

### 1. Parameter Settings
- **Initial Guesses**: Enter starting estimates for $\log_{10} K$ values (e.g. $4.0$ for $K = 10,000 \text{ M}^{-1}$).
- **Vary / Fix Parameters**: Toggle checkboxes to hold known parameters fixed (e.g., free host chemical shift $\delta_{\text{H}}$ measured independently).
- **Lower / Upper Bounds**: Restrict parameter ranges to prevent non-physical values (e.g. $\log_{10}K \ge 0$).

### 2. Running Optimization
Click **Run Fit**. `bindmc` executes non-linear minimization (Levenberg-Marquardt algorithm by default) and displays:
- Optimized parameter values with standard errors ($1\sigma$).
- Goodness-of-fit statistics ($\chi^2$, reduced $\chi^2$, Akaike Information Criterion $AIC$, $BIC$).
- Correlation matrix between optimized parameters.

---

## Interactive Visualizations

After fitting completes, three interactive plots update:

1. **Titration Curves & Fits**:
   - Experimental data points vs. smooth fitted model curves for all dependent variables.
2. **Residual Plot**:
   - Residuals ($y_{\text{exp}} - y_{\text{fit}}$) plotted against total concentration to check for systematic model mismatch.
3. **Speciation Diagram**:
   - Calculated equilibrium concentrations of free components and all complex species across the titration series.
