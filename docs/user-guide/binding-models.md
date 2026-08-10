# Binding Models & Speciation Solvers

`bindmc` supports two modes for calculating equilibrium species concentrations:
1. **Numerical Speciation Solver**: Arbitrary stoichiometries using Newton–Raphson iteration.
2. **Analytical Fast Exchange Solvers**: Exact closed-form algebraic solutions for common single host-guest topologies ($1:1$, $1:2$, $2:1$).

---

## 1. Numerical Solver (Newton–Raphson)

The general chemical equilibrium for formation of complex species $C_j$ from $N$ components $A_i$ is described by:

$$a_{j1} A_1 + a_{j2} A_2 + \dots + a_{jN} A_N \rightleftharpoons C_j$$

with cumulative formation constant $\beta_j = 10^{\log_{10} K_j}$:

$$[C_j] = \beta_j \prod_{i=1}^N [A_i]^{a_{ji}}$$

The mass balance equations for each component total concentration $T_i$ are:

$$T_i = [A_i] + \sum_{j} a_{ji} [C_j]$$

`bindmc` uses `bindtools.binding.DoNR`, a Numba-JIT compiled Newton–Raphson solver with analytical Jacobian evaluation, ensuring high-speed calculation across thousands of titration points.

### Writing Equations in the GUI

In the **Binding Model** tab, enter equilibrium reactions directly using standard chemical notation:

```text
H + G <=> HG
H + 2G <=> HG2
```

`bindmc` automatically parses the equations, identifies free components (`H`, `G`) and complexes (`HG`, `HG2`), and constructs the stoichiometry matrix ($E_{\text{mat}}$).

<!-- 
### Multi-State & Competition Equilibria (Indicator Displacement / Displacement Assays)

Competitive equilibria involving multiple hosts, guests, or metals (e.g., indicator displacement assays):

```text
H + I <=> HI
H + G <=> HG
```

*Note: Automated test cases for competitive equilibria are currently under development in the test suite.*
-->

---

## 2. Analytical Fast-Exchange Solvers

For fast-exchange titrations with standard binding topologies ($1:1$, $1:2$, $2:1$ host-guest systems), analytical solvers avoid iterative root-finding overhead.

`bindmc` automatically inspects the stoichiometry matrix ($E_{\text{mat}}$) to detect whether a model matches a simple analytical topology. If it does, `calc_analytical_speciation` calculates exact species concentrations in a single vectorized numpy operation.

### 1:1 Fast Exchange Model
Equilibrium reaction: $\text{H} + \text{G} \rightleftharpoons \text{HG}$ with binding constant $K_{11}$.

Free guest concentration $[G]$ is solved directly via quadratic formula:

$$K_{11} [G]^2 + (1 + K_{11} [\text{H}]_{\text{tot}} - K_{11} [\text{G}]_{\text{tot}}) [G] - [\text{G}]_{\text{tot}} = 0$$

Observed chemical shift:

$$\delta_{\text{obs}} = \delta_{\text{H}} + (\delta_{\text{HG}} - \delta_{\text{H}}) \frac{[\text{HG}]}{[\text{H}]_{\text{tot}}}$$

### 1:2 and 2:1 Fast Exchange Models
Closed-form analytical equations solve cubic polynomials directly via vectorized trigonometric methods (`_solve_cubic_vectorized`).
