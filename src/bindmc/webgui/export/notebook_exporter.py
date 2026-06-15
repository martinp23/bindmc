"""
Export BindTools project state to Jupyter notebooks.

Public API
----------
export_simulation_notebook(sim, model) -> dict
    Returns an nbformat-4 notebook dict ready to be written as .ipynb JSON.

export_fit_notebook(fit, model, expt_data, raw_data) -> tuple[dict, pd.DataFrame]
    Returns (notebook_dict, csv_dataframe).
    Write the DataFrame to a CSV file alongside the notebook so the generated
    code can load it with ``pd.read_csv("data.csv")``.

Both functions produce self-contained notebooks that depend only on standard
scientific Python libraries (numpy, pandas, matplotlib, lmfit) and
``bindtools``; they never import ``nicegui`` or anything from ``webgui``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # avoid runtime webgui imports
    from ..classes.ExptData import ExptData
    from ..classes.FitResult import FitResult
    from ..classes.MCMCSim import MCMCSim
    from ..classes.Model import Model
    from ..classes.RawData import RawData
    from ..classes.Simulation import Simulation

from ..utils import safe_filename


# ---------------------------------------------------------------------------
# Low-level notebook construction helpers
# ---------------------------------------------------------------------------


def _md_cell(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def _code_cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source,
    }


def _notebook(cells: list[dict]) -> dict:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12.0"},
        },
        "cells": cells,
    }


# ---------------------------------------------------------------------------
# Simulation notebook
# ---------------------------------------------------------------------------


def export_simulation_notebook(sim: "Simulation", model: "Model") -> dict:
    """Export a Simulation as an nbformat-4 notebook dict.

    The generated notebook:
    1. Embeds component concentrations from *sim.comp_concs* as inline data.
    2. Uses binding constants from *model.binding_constants*.
    3. Calls ``bd.bindingModel(...).calcSpeciation()`` to reproduce the result.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ------------------------------------------------------------------
    # Cell 0 — Title / metadata (markdown)
    # ------------------------------------------------------------------
    md_title = "\n".join(
        [
            f"# Simulation: {sim.name or 'Unnamed'}",
            "",
            f"**Model:** {model.name}  ",
            f"**Equation:** `{model.eq_str}`  ",
            f"**Generated:** {timestamp}  ",
            "",
            "| Parameter | logK |",
            "|-----------|------|",
            *[f"| log{bc.species} | {bc.logK if bc.logK is not None else 0.0} |" for bc in model.binding_constants],
        ]
    )

    # ------------------------------------------------------------------
    # Cell 1 — Imports
    # ------------------------------------------------------------------
    imports = "import numpy as np\nimport pandas as pd\nimport matplotlib.pyplot as plt\nimport bindtools.binding as bd"

    # ------------------------------------------------------------------
    # Cell 2 — Model definition
    # ------------------------------------------------------------------
    eq_mat_list = model.eq_mat.tolist()
    model_def = "\n".join(
        [
            "# Model definition",
            f"eq_mat = np.array({eq_mat_list!r}, dtype=float)",
            f"component_names = {model.component_names!r}",
            f"species_names = {model.species!r}",
        ]
    )

    # ------------------------------------------------------------------
    # Cell 3 — Component concentrations (inlined from sim.comp_concs)
    # ------------------------------------------------------------------
    comp_dict = {col: sim.comp_concs[col].tolist() for col in sim.comp_concs.columns}
    comp_concs_code = "\n".join(
        [
            "# Component concentrations",
            f"comp_concs = pd.DataFrame({comp_dict!r})",
        ]
    )

    # ------------------------------------------------------------------
    # Cell 4 — Binding parameters
    # ------------------------------------------------------------------
    param_lines = [
        "# Binding parameters (log10 association constants)",
        "params = {",
    ]
    for bc in model.binding_constants:
        val = bc.logK if bc.logK is not None else 0.0
        comment = "  # component pseudo-constant" if bc.isComp else ""
        param_lines.append(f"    'log{bc.species}': {val!r},{comment}")
    param_lines.append("}")
    params_code = "\n".join(param_lines)

    # ------------------------------------------------------------------
    # Cell 5 — Run the binding model and compute speciation
    # ------------------------------------------------------------------
    run_code = (
        "# Set up and run the binding model\n"
        "bm = bd.bindingModel(\n"
        "    eq_mat,\n"
        "    component_names,\n"
        "    species_names,\n"
        "    compConcs=comp_concs.values,\n"
        ")\n"
        "bm.prepModel()\n"
        "\n"
        "# Fix all parameters to simulation values\n"
        "for pname, pval in params.items():\n"
        "    bm.params[pname].set(value=pval, vary=False)\n"
        "\n"
        "# Calculate speciation\n"
        "spec = bm.calcSpeciation()\n"
        "results = pd.DataFrame(spec, columns=species_names, index=comp_concs.index)\n"
        "print(results)"
    )

    # ------------------------------------------------------------------
    # Cell 6 — Plot
    # ------------------------------------------------------------------
    # Note: curly braces inside the string are notebook f-string syntax,
    # evaluated when the *notebook* runs, not at generation time.
    plot_code = (
        "# Plot speciation\n"
        "fig, ax = plt.subplots(figsize=(8, 5))\n"
        "if len(component_names) >= 2:\n"
        "    x_vals = comp_concs.iloc[:, 1].values / comp_concs.iloc[:, 0].values\n"
        "    x_label = f'[{component_names[1]}]$_{{tot}}$ / [{component_names[0]}]$_{{tot}}$'\n"
        "else:\n"
        "    x_vals = np.arange(len(comp_concs))\n"
        "    x_label = 'Step'\n"
        "for col in results.columns:\n"
        "    ax.plot(x_vals, results[col], label=f'[{col}]$_{{free}}$')\n"
        "ax.set_xlabel(x_label)\n"
        "ax.set_ylabel('Concentration (M)')\n"
        "ax.legend()\n"
        "plt.tight_layout()\n"
        "plt.show()"
    )

    cells = [
        _md_cell(md_title),
        _code_cell(imports),
        _code_cell(model_def),
        _code_cell(comp_concs_code),
        _code_cell(params_code),
        _code_cell(run_code),
        _code_cell(plot_code),
    ]
    return _notebook(cells)


# ---------------------------------------------------------------------------
# Fit notebook
# ---------------------------------------------------------------------------


def _build_lin_obs_cell4_lines(
    lin_obs_col_names: list,
    lin_obs_param_map: list,
) -> list[str]:
    """Return source lines that reconstruct spec_to_linear before m.prepModel().

    lin_obs_param_map is a list-of-lists:  [obs_idx][spec_idx] → dict or None.
    Active cells: dict with keys 'name', 'min', 'max'.
    Dark cells:   None.
    """
    n_lin_obs = len(lin_obs_col_names)
    lines = [
        "",
        "# UV-vis / fluorescence: reconstruct specToLinear before prepModel()",
        f"_lin_obs_col_names = {lin_obs_col_names!r}",
        f"_lin_obs_param_map = {lin_obs_param_map!r}",
        f"_n_lin_obs = {n_lin_obs}",
        "spec_to_linear = np.empty((len(species_names), _n_lin_obs), dtype=object)",
        "for _oi, _prow in enumerate(_lin_obs_param_map):",
        "    for _si, _pcell in enumerate(_prow):",
        "        if _pcell is None:",
        "            spec_to_linear[_si, _oi] = 0.0",
        "        else:",
        "            spec_to_linear[_si, _oi] = lmfit.Parameter(",
        "                _pcell['name'], value=1.0, min=_pcell['min'], max=_pcell['max'], vary=True",
        "            )",
        "m.specToLinear = spec_to_linear",
    ]
    return lines


def _build_analytical_lin_obs_lines(lin_obs_param_map: list) -> list[str]:
    """Return setup lines for the analytical path's linear_obs_param_map.

    Extracts the param name (or None) from each cell so
    fitfun_analytical_fast_exchange can call calc_analytical_linear_observables.
    """
    # Serialise as [[name_or_none, ...], ...]
    name_map = [[cell["name"] if cell is not None else None for cell in row] for row in lin_obs_param_map]
    return [
        f"m.analytical_linear_obs_param_map = {name_map!r}",
    ]


def export_fit_notebook(
    fit: "FitResult",
    model: "Model",
    expt_data: "ExptData",
    raw_data: "RawData",
    obs_type_names: "list[str] | None",
    lin_obs_col_names: "list[str] | None" = None,
    lin_obs_param_map: "list[list] | None" = None,
) -> tuple[dict, pd.DataFrame]:
    """Export a FitResult as an nbformat-4 notebook dict plus a CSV DataFrame.

    The notebook is designed to *re-run* the fit from scratch.  Original
    fitted values are embedded as comments so the user can verify the result.
    The companion CSV (second return value) should be saved as ``data.csv``
    next to the notebook.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    n_comp = int(np.shape(expt_data.col_to_comp)[0])
    col_to_comp_list = np.array(expt_data.col_to_comp, dtype=float).tolist()

    integ_to_spec = expt_data.integ_to_spec
    if isinstance(integ_to_spec, np.ndarray) and integ_to_spec.ndim == 2 and integ_to_spec.size > 0:
        integ_to_spec_list: list | None = integ_to_spec.tolist()
    else:
        integ_to_spec_list = None

    delta_to_spec = expt_data.delta_to_spec
    has_delta = isinstance(delta_to_spec, np.ndarray) and delta_to_spec.ndim == 2 and delta_to_spec.size > 0

    obs_list = obs_type_names
    # ------------------------------------------------------------------
    # Cell 0 — Summary markdown
    # ------------------------------------------------------------------
    param_rows = []
    for pname, pinfo in (fit.params or {}).items():
        if isinstance(pinfo, dict):
            val = pinfo.get("value", "?")
            stderr = pinfo.get("stderr", None)
            vary = pinfo.get("vary", False)
            if vary and stderr is not None:
                param_rows.append(f"| {pname} | {val:.6g} ± {stderr:.3g} | fitted |")
            else:
                param_rows.append(f"| {pname} | {val:.6g} | fixed |")

    aic_str = f"{fit.aic:.4g}" if fit.aic is not None else "n/a"
    bic_str = f"{fit.bic:.4g}" if fit.bic is not None else "n/a"
    chisqr_str = f"{fit.chisqr:.4g}" if fit.chisqr is not None else "n/a"
    method_str = fit.fit_method or "least_squares"

    md_title = "\n".join(
        [
            f"# Fit: {fit.name or 'Unnamed'}",
            "",
            f"**Model:** {model.name}  ",
            f"**Equation:** `{model.eq_str}`  ",
            f"**Generated:** {timestamp}  ",
            "",
            "## Original fit results",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| AIC | {aic_str} |",
            f"| BIC | {bic_str} |",
            f"| χ² | {chisqr_str} |",
            f"| Method | {method_str} |",
            f"| Success | {fit.success} |",
            "",
            "| Parameter | Value | Status |",
            "|-----------|-------|--------|",
            *param_rows,
            *(["", f"**Termination:** {fit.termination_message}"] if fit.termination_message else []),
        ]
    )

    # ------------------------------------------------------------------
    # Cell 1 — Imports
    # ------------------------------------------------------------------
    imports = (
        "import numpy as np\n"
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n"
        "import lmfit\n"
        "import bindtools.binding as bd\n"
        "from IPython.display import HTML, display"
    )

    # ------------------------------------------------------------------
    # Cell 2 — Model definition
    # ------------------------------------------------------------------
    model_def = "\n".join(
        [
            "# Model definition",
            f"eq_mat = np.array({model.eq_mat.tolist()!r}, dtype=float)",
            f"component_names = {model.component_names!r}",
            f"species_names = {model.species!r}",
            f"obs_list = {obs_list!r}",
        ]
    )

    # ------------------------------------------------------------------
    # Cell 3 — Load data
    # ------------------------------------------------------------------
    stem = safe_filename(fit.name or "fit")
    # Capture the column order used by the GUI (selected + reordered via column_mapping).
    # Embedding this lets the notebook reconstruct the same data slice from the raw CSV.
    sorted_cols = expt_data.sorted_data.columns.tolist()
    load_data = "\n".join(
        [
            "# Load experimental data — keep the companion CSV alongside this notebook.",
            "# The column list below reproduces the selection and ordering used in BindTools.",
            f"data = pd.read_csv('{stem}_data.csv')",
            f"data_cols = {sorted_cols!r}",
            "data = data[data_cols]",
            "raw = data.to_numpy(dtype=float)",
        ]
    )

    # ------------------------------------------------------------------
    # Cell 4 — Construct binding model (mirrors reference notebook pattern)
    # ------------------------------------------------------------------
    col_to_comp_repr = repr(col_to_comp_list)
    if integ_to_spec_list is not None:
        spec_to_integ_line = f"spec_to_integ = np.array({integ_to_spec_list!r}, dtype=float)"
        spec_to_integ_arg = "spec_to_integ"
    else:
        spec_to_integ_line = "spec_to_integ = None"
        spec_to_integ_arg = "None"

    if has_delta:
        spec_to_dd_line = f"spec_to_dd = np.array({delta_to_spec.T.tolist()!r}, dtype=object)"
        spec_to_dd_arg = "spec_to_dd"
    else:
        spec_to_dd_line = "spec_to_dd = None"
        spec_to_dd_arg = "None"

    is_analytical = bool(getattr(fit, "analytical_fast_exchange", False))
    analytical_topology = getattr(fit, "analytical_topology", None)
    analytical_obs_columns = list(getattr(fit, "analytical_obs_columns", []))
    analytical_obs_components = list(getattr(fit, "analytical_obs_components", []))
    analytical_complex_indices = list(getattr(fit, "analytical_complex_indices", []))

    has_lin_obs = bool(lin_obs_col_names and lin_obs_param_map)

    if is_analytical:
        analytical_setup_lines: list[str] = [
            "",
            "# Analytical fast-exchange backend — must be configured before prepModel()",
            "m.analytical_fast_exchange = True",
            f"m.analytical_topology = {analytical_topology!r}",
            f"m.analytical_obs_columns = {analytical_obs_columns!r}",
            f"m.analytical_obs_components = {analytical_obs_components!r}",
            f"m.analytical_complex_indices = {analytical_complex_indices!r}",
        ]
        if has_lin_obs:
            analytical_setup_lines += _build_analytical_lin_obs_lines(lin_obs_param_map)  # type: ignore[arg-type]
    else:
        analytical_setup_lines = []

    lin_obs_lines = (
        _build_lin_obs_cell4_lines(lin_obs_col_names, lin_obs_param_map)  # type: ignore[arg-type]
        if has_lin_obs
        else []
    )

    construct_model = "\n".join(
        [
            "# Matrices mapping data columns → components and species → observables",
            f"col_to_comp = np.array({col_to_comp_repr}, dtype=float)",
            spec_to_integ_line,
            spec_to_dd_line,
            "",
            "# Construct binding model",
            "m = bd.bindingModel(",
            "    eq_mat,",
            "    component_names,",
            "    species_names,",
            f"    {spec_to_integ_arg},",
            f"    {spec_to_dd_arg},",
            "    col_to_comp,",
            "    obs_list,",
            "    raw,",
            ")",
            "# Compute component concentrations from the data matrix",
            "m.compConcs = np.dot(m.rawData[:, :m.nComp], m.colToComp[:, :m.nComp].T)",
            *lin_obs_lines,
            *analytical_setup_lines,
            "m.prepModel()",
        ]
    )

    # ------------------------------------------------------------------
    # Cell 5 — Set parameters (initial_value for re-running; fitted in comments)
    # ------------------------------------------------------------------
    param_set_lines = [
        "# Set parameter bounds and initial guesses.",
        "# Original fitted values are shown in comments — use them to verify your re-run.",
    ]
    for pname, pinfo in (fit.params or {}).items():
        if not isinstance(pinfo, dict):
            continue
        vary = pinfo.get("vary", False)
        min_val = pinfo.get("min", 0)
        max_val = pinfo.get("max", 14)
        init_val = pinfo.get("initial_value", pinfo.get("value", 0.0))
        fitted_val = pinfo.get("value", init_val)
        stderr = pinfo.get("stderr", None)

        if vary and stderr is not None:
            comment = f"  # fitted: {fitted_val:.6g} ± {stderr:.3g}"
        elif vary:
            comment = f"  # fitted: {fitted_val:.6g}"
        else:
            comment = "  # fixed"

        param_set_lines.append(
            f"m.params[{pname!r}].set(value={float(init_val)!r}, "
            f"vary={vary!r}, min={float(min_val)!r}, max={float(max_val)!r})"
            f"{comment}"
        )

    set_params_code = "\n".join(param_set_lines)

    # ------------------------------------------------------------------
    # Cell 6 — Run the fit
    # ------------------------------------------------------------------
    run_fit = "\n".join(
        [
            "# Run the fit",
            f"skip_col = {n_comp}  # number of component-concentration columns",
            f"m.runModel(skip_col=skip_col, method={method_str!r})",
            "display(HTML(m.miniResult._repr_html_()))",
        ]
    )

    # ------------------------------------------------------------------
    # Cell 7 — Plot residuals
    # ------------------------------------------------------------------
    plot_resid = (
        "# Residual plot — adjust plotMask to select which observables to show\n"
        "n_obs = len(obs_list)\n"
        "bd.makeFitResidPlot(\n"
        "    m,\n"
        "    xindex=1,\n"
        "    plotMask=tuple(range(n_obs)),\n"
        "    skip_end=None,\n"
        "    xvals=m.rawData[:, 1] / m.rawData[:, 0],\n"
        "    xlabel=r'[' + component_names[1] + r']$_{\\mathrm{tot}}$ / [' + component_names[0] + r']$_{\\mathrm{tot}}$',\n"
        "    ylabel='Observable',\n"
        "    labels=obs_list,\n"
        ")"
    )

    # ------------------------------------------------------------------
    # Cell 8 — MCMC section (markdown header)
    # ------------------------------------------------------------------
    md_mcmc = "\n".join(
        [
            "## MCMC sampling",
            "",
            "Use the cell below to explore the posterior distribution of the fit parameters with `emcee`.",
            "Uncomment and adjust as needed.",
        ]
    )

    # ------------------------------------------------------------------
    # Cell 9 — MCMC code (commented out)
    # ------------------------------------------------------------------
    mcmc_code = "\n".join(
        [
            "# # bd.MCMC requires the fit to have been run first (m.runModel above).",
            "# # obs_types maps each observable column to its noise model.",
            "# # Built-in names: 'NMRInteg', 'concMeas', 'deltaH', 'deltaF'.",
            "# # Use a custom string for anything else.",
            "# obs_types = [bd.ObsType(name) for name in obs_list]",
            "#",
            "# # Number of walkers and steps — increase for production runs.",
            "# n_walkers = 50",
            "# n_steps   = 2000",
            "#",
            "# mc = bd.MCMC(m, obs_types, walkers=n_walkers, samples=n_steps)",
            "# mc.run()",
            "#",
            "# # Inspect autocorrelation time to check convergence",
            "# mc.get_tau()",
            "#",
            "# # Walker trace plot",
            "# mc.plot_chain()",
            "# plt.show()",
            "#",
            "# # Corner plot (burn-in is estimated automatically from autocorr time)",
            "# mc.plot_corner()",
            "# plt.show()",
        ]
    )

    cells = [
        _md_cell(md_title),
        _code_cell(imports),
        _code_cell(model_def),
        _code_cell(load_data),
        _code_cell(construct_model),
        _code_cell(set_params_code),
        _code_cell(run_fit),
        _code_cell(plot_resid),
        _md_cell(md_mcmc),
        _code_cell(mcmc_code),
    ]

    csv_df = raw_data.data.copy()
    return _notebook(cells), csv_df


# ---------------------------------------------------------------------------
# MCMC notebook
# ---------------------------------------------------------------------------


def export_mcmc_notebook(
    mcmc: "MCMCSim | None",
    fit: "FitResult",
    model: "Model",
    expt_data: "ExptData",
    raw_data: "RawData",
    obs_type_names: list[str],
    include_chains: bool,
    lin_obs_col_names: "list[str] | None" = None,
    lin_obs_param_map: "list[list] | None" = None,
) -> tuple[dict, pd.DataFrame, bytes | None]:
    """Export a FitResult + MCMC run as an nbformat-4 notebook dict, CSV DataFrame,
    and optionally HDF5 bytes (chains file).

    Parameters
    ----------
    mcmc : MCMCSim or None
        The MCMC run.  When *None*, a code-only notebook is produced with
        default walker / step counts.
    fit, model, expt_data, raw_data : linked domain objects
    obs_type_names : list[str]
        Noise-model name for each observable, e.g. ``['deltaF', 'deltaF']``.
    include_chains : bool
        When True the notebook loads chains from a companion HDF5 file and the
        function also returns the raw HDF5 bytes.  Requires
        ``mcmc.mc.sampler`` to be non-None.

    Returns
    -------
    notebook : dict        nbformat-4 compatible dict.
    csv_df : pd.DataFrame   Raw data for the companion CSV.
    h5_bytes : bytes or None
    """
    # Build the first 8 cells (title … residual plot) from the fit notebook.
    # The fit notebook has exactly 10 cells; we discard the two commented-out
    # MCMC template cells at the end and replace them with live code.
    base_nb, csv_df = export_fit_notebook(
        fit,
        model,
        expt_data,
        raw_data,
        obs_type_names=obs_type_names,
        lin_obs_col_names=lin_obs_col_names,
        lin_obs_param_map=lin_obs_param_map,
    )
    cells = base_nb["cells"][:8]

    # MCMC parameters — use MCMCSim values when available, fall back to defaults
    n_walkers = int(mcmc.nwalkers) if mcmc is not None else 50
    n_steps = int(mcmc.nsteps_target) if mcmc is not None else 2000
    thin = int(mcmc.thin) if mcmc is not None else 1
    burn = int(mcmc.burn) if mcmc is not None else 200

    stem = safe_filename(fit.name or "fit")

    # ------------------------------------------------------------------
    # Cell 8 — MCMC section header (markdown)
    # ------------------------------------------------------------------
    if include_chains:
        md_mcmc = "\n".join(
            [
                "## MCMC sampling — loading saved chains",
                "",
                f"Chains are loaded from `{stem}_chains.hdf` (included in the zip).",
                "Adjust `burnin` as needed.",
            ]
        )
    else:
        md_mcmc = "\n".join(
            [
                "## MCMC sampling",
                "",
                "Run the cell below to explore the posterior distribution via MCMC.",
                f"Walkers: {n_walkers}, steps: {n_steps}, thin: {thin}.",
            ]
        )

    # ------------------------------------------------------------------
    # Cell 9 — MCMC code
    # ------------------------------------------------------------------
    if include_chains:
        mcmc_code = "\n".join(
            [
                "import h5py",
                "import corner as corner",
                "",
                f"with h5py.File('{stem}_chains.hdf', 'r') as f:",
                "    chain    = f['mcmc/chain'][:]     # (nsteps, nwalkers, ndim)",
                "    log_prob = f['mcmc/log_prob'][:]  # (nsteps, nwalkers)",
                "",
                "param_labels = [p for p in m.params if m.params[p].vary]",
                "ndim = chain.shape[2]",
                "",
                "# Walker trace plot",
                "n_rows = ndim + 1",
                "fig, axes = plt.subplots(n_rows, 1, figsize=(12, 3 + n_rows * 1.7), sharex=True)",
                "for i, label in enumerate(param_labels):",
                "    axes[i].plot(chain[:, :, i], alpha=0.3, lw=0.5, color='k')",
                "    axes[i].set_ylabel(label)",
                "axes[-1].plot(log_prob, alpha=0.3, lw=0.5, color='k')",
                "axes[-1].set_ylabel('log prob')",
                "axes[-1].set_xlabel('step')",
                "fig.tight_layout()",
                "plt.show()",
                "",
                f"# Corner plot — burnin from original run ({burn}); adjust as needed",
                f"burnin = {burn}",
                "flat_chain = chain[burnin:].reshape(-1, ndim)",
                "if len(param_labels) < ndim:",
                "    param_labels += [f'sigma_{i}' for i in range(len(param_labels), ndim)]",
                "corner.corner(flat_chain, labels=param_labels)",
                "plt.show()",
            ]
        )
    else:
        mcmc_code = "\n".join(
            [
                f"obs_type_names = {obs_type_names!r}",
                "obs_types = [bd.ObsType(name) for name in obs_type_names]",
                "",
                f"n_walkers = {n_walkers}",
                f"n_steps   = {n_steps}",
                f"thin      = {thin}",
                "",
                "mc = bd.MCMC(m, obs_types, walkers=n_walkers, samples=n_steps)",
                "mc.run(thin=thin)",
                "",
                "# Inspect autocorrelation time to check convergence",
                "mc.get_tau()",
                "",
                "# Walker trace plot",
                "mc.plot_chain()",
                "plt.show()",
                "",
                "# Corner plot (burn-in estimated automatically from autocorr time)",
                "mc.plot_corner()",
                "plt.show()",
                "",
                f"# mc.save('{stem}_chains.hdf')  # uncomment to save chains",
            ]
        )

    cells.append(_md_cell(md_mcmc))
    cells.append(_code_cell(mcmc_code))

    # ------------------------------------------------------------------
    # HDF5 bytes (include_chains=True only)
    # ------------------------------------------------------------------
    h5_bytes: bytes | None = None
    if (
        include_chains
        and mcmc is not None
        and getattr(mcmc, "mc", None) is not None
        and getattr(mcmc.mc, "sampler", None) is not None
    ):
        import h5py  # lazy import — h5py only needed at export time

        backend = mcmc.mc.sampler.backend
        with h5py.File("mcmc_export.h5", "w", driver="core", backing_store=False) as hf:
            g = hf.create_group("mcmc")
            g.create_dataset("chain", data=backend.chain)
            g.create_dataset("accepted", data=backend.accepted)
            g.create_dataset("log_prob", data=backend.log_prob)
            has_blobs = backend.blobs is not None
            g.attrs["has_blobs"] = has_blobs
            if has_blobs:
                g.create_dataset("blobs", data=backend.blobs)
            g.attrs["iteration"] = backend.iteration
            hf.flush()
            h5_bytes = bytes(hf.id.get_file_image())

    return _notebook(cells), csv_df, h5_bytes
