"""Tests for Jupyter notebook export functionality (TDD — write first, implement after)."""

import tempfile
from types import SimpleNamespace

import os
import h5py
import numpy as np
import pandas as pd

from bindmc.webgui.state import StateManager
from bindmc.webgui.classes import Simulation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_state_1to1() -> StateManager:
    sm = StateManager(load_prior_state=False)
    with open("tests/test_data/1to1_test") as f:
        json_str = f.read()
    sm.from_json(json_str)
    return sm


def _make_test_sim(model) -> Simulation:
    """Build a minimal Simulation from the given model so we have something to export."""
    import bindtools.binding as bd

    n_steps = 20
    h_conc = 0.005
    g_concs = np.linspace(0.0, 0.02, n_steps)
    comp_concs = pd.DataFrame(
        {f"{model.component_names[0]}_tot": np.full(n_steps, h_conc), f"{model.component_names[1]}_tot": g_concs}
    )

    logK_vals = np.array([bc.logK for bc in model.binding_constants])
    rows = [
        bd.getConcs(model.eq_mat, np.array([row.iloc[0], row.iloc[1]]), logK_vals) for _, row in comp_concs.iterrows()
    ]
    results = pd.DataFrame(np.array(rows), columns=model.species)

    return Simulation(
        comp_concs=comp_concs,
        model_id=model.id,
        params=model.binding_constants,
        results=results,
        name="1:1 test sim",
    )


# ---------------------------------------------------------------------------
# Simulation notebook tests
# ---------------------------------------------------------------------------


def test_sim_notebook_structure():
    sm = _load_state_1to1()
    model = sm.active_model
    sim = _make_test_sim(model)

    notebook = sm.dump_simulation_notebook(sim)

    assert notebook["nbformat"] == 4
    assert "cells" in notebook
    cells = notebook["cells"]
    assert len(cells) >= 4

    # First cell is markdown containing the model name
    assert cells[0]["cell_type"] == "markdown"
    assert model.name in cells[0]["source"]

    # Must have several code cells
    code_cells = [c for c in cells if c["cell_type"] == "code"]
    assert len(code_cells) >= 3

    all_code = "\n".join(c["source"] for c in code_cells)

    # No NiceGUI / webgui leakage
    assert "nicegui" not in all_code
    assert "webgui" not in all_code

    # Uses bindtools
    assert "bindtools" in all_code

    # Runs speciation
    assert "calcSpeciation" in all_code


def test_sim_notebook_is_executable():
    """The generated code cells should be runnable via exec() and produce a results DataFrame."""
    sm = _load_state_1to1()
    model = sm.active_model
    sim = _make_test_sim(model)

    notebook = sm.dump_simulation_notebook(sim)

    code = "\n".join(c["source"] for c in notebook["cells"] if c["cell_type"] == "code")
    # Suppress any GUI calls that don't make sense in a test
    code = code.replace("plt.show()", "# plt.show()")

    ns: dict = {}
    exec(code, ns)  # noqa: S102

    assert "results" in ns
    result = ns["results"]
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == model.species
    assert len(result) == len(sim.comp_concs)


# ---------------------------------------------------------------------------
# Fit notebook tests
# ---------------------------------------------------------------------------


def test_fit_notebook_structure():
    sm = _load_state_1to1()
    fit = sm.active_fit

    notebook, csv_df = sm.dump_fit_notebook(fit)

    assert notebook["nbformat"] == 4
    cells = notebook["cells"]
    assert len(cells) >= 4

    # First cell is markdown containing the fit name
    assert cells[0]["cell_type"] == "markdown"
    assert fit.name in cells[0]["source"]

    code_cells = [c for c in cells if c["cell_type"] == "code"]
    all_code = "\n".join(c["source"] for c in code_cells)

    # No NiceGUI / webgui leakage
    assert "nicegui" not in all_code
    assert "webgui" not in all_code

    # Uses bindtools
    assert "bindtools" in all_code

    # Loads data from CSV
    assert "read_csv" in all_code

    # Re-runs the fit
    assert "runModel" in all_code


def test_fit_csv_matches_raw_data():
    sm = _load_state_1to1()
    fit = sm.active_fit

    _, csv_df = sm.dump_fit_notebook(fit)

    # Resolve the raw data independently to compare
    expt_data = sm.expt_datas[fit.expt_data_id]
    expt_data.find_and_link_raw_data(sm.raw_datas)
    expected = expt_data._raw_data.data

    assert isinstance(csv_df, pd.DataFrame)
    pd.testing.assert_frame_equal(
        csv_df.reset_index(drop=True),
        expected.reset_index(drop=True),
    )


def test_fit_notebook_original_values_in_output():
    """Original fitted values should appear somewhere in the notebook (e.g. as comments or markdown)."""
    sm = _load_state_1to1()
    fit = sm.active_fit

    notebook, _ = sm.dump_fit_notebook(fit)

    all_text = "\n".join(c["source"] for c in notebook["cells"])

    # logHG was fitted to ~3.9998
    fitted_val = fit.params.get("logHG", {}).get("value", None)
    assert fitted_val is not None
    # At least the first 4 significant digits should appear
    assert f"{fitted_val:.4f}"[:4] in all_text


def test_fit_notebook_uses_initial_values_for_params():
    """Code cells must use initial_value (not final value) so the fit can be re-run."""
    sm = _load_state_1to1()
    fit = sm.active_fit

    notebook, _ = sm.dump_fit_notebook(fit)

    code_cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
    all_code = "\n".join(c["source"] for c in code_cells)

    # The initial value for logHG is 3.0, not the fitted 3.9998
    init_val = fit.params.get("logHG", {}).get("initial_value", None)
    assert init_val is not None
    assert str(init_val) in all_code or f"{float(init_val):.1f}" in all_code


# ---------------------------------------------------------------------------
# MCMC notebook tests
# ---------------------------------------------------------------------------


def test_mcmc_notebook_structure_code_only():
    """export_mcmc_notebook with include_chains=False produces a valid notebook with live MCMC code."""
    sm = _load_state_1to1()
    notebook, csv_df, h5_bytes = sm.dump_mcmc_notebook(mcmc=None, include_chains=False)

    assert notebook["nbformat"] == 4
    cells = notebook["cells"]
    code_cells = [c for c in cells if c["cell_type"] == "code"]
    all_code = "\n".join(c["source"] for c in code_cells)

    # No NiceGUI / webgui leakage
    assert "nicegui" not in all_code
    assert "webgui" not in all_code

    # Live MCMC code present
    assert "bd.MCMC" in all_code
    assert "mc.run" in all_code
    assert "mc.plot_chain" in all_code
    assert "mc.plot_corner" in all_code

    # No chains file in code-only mode
    assert h5_bytes is None

    # CSV is returned
    assert isinstance(csv_df, pd.DataFrame)


def test_mcmc_notebook_csv_matches_raw_data():
    """The CSV returned alongside the MCMC notebook must match the raw experimental data."""
    sm = _load_state_1to1()
    _, csv_df, _ = sm.dump_mcmc_notebook(mcmc=None, include_chains=False)

    fit = sm.active_fit
    expt_data = sm.expt_datas[fit.expt_data_id]
    expt_data.find_and_link_raw_data(sm.raw_datas)
    expected = expt_data._raw_data.data

    pd.testing.assert_frame_equal(
        csv_df.reset_index(drop=True),
        expected.reset_index(drop=True),
    )


def test_mcmc_notebook_inherits_fit_cells():
    """The MCMC notebook must include the fit setup cells (runModel / lmfit code)."""
    sm = _load_state_1to1()
    notebook, _, _ = sm.dump_mcmc_notebook(mcmc=None, include_chains=False)

    all_code = "\n".join(c["source"] for c in notebook["cells"] if c["cell_type"] == "code")

    # Fit cells are present
    assert "runModel" in all_code
    assert "read_csv" in all_code


def test_mcmc_notebook_default_walker_count():
    """When mcmc=None, the notebook code should use the default walker count (50)."""
    sm = _load_state_1to1()
    notebook, _, _ = sm.dump_mcmc_notebook(mcmc=None, include_chains=False)

    all_code = "\n".join(c["source"] for c in notebook["cells"] if c["cell_type"] == "code")

    assert "n_walkers = 50" in all_code


def test_mcmc_notebook_exported_hdf_bytes_reopen_cleanly():
    """The bundled chain file should be a valid HDF5 file that h5py can reopen."""
    sm = _load_state_1to1()

    backend = SimpleNamespace(
        chain=np.arange(24, dtype=float).reshape(3, 4, 2),
        accepted=np.array([1, 2, 3, 4], dtype=int),
        log_prob=np.arange(12, dtype=float).reshape(3, 4),
        blobs=None,
        iteration=3,
    )
    sampler = SimpleNamespace(backend=backend)
    fake_mcmc = SimpleNamespace(
        nwalkers=4,
        nsteps_target=3,
        thin=2,
        burn=1,
        mc=SimpleNamespace(sampler=sampler),
    )

    notebook, _, h5_bytes = sm.dump_mcmc_notebook(mcmc=fake_mcmc, include_chains=True)

    assert h5_bytes is not None

    all_code = "\n".join(c["source"] for c in notebook["cells"] if c["cell_type"] == "code")
    assert "thin     = f['mcmc'].attrs.get('thin', 1)" in all_code

    tmp = tempfile.NamedTemporaryFile(suffix=".hdf", delete=False)
    try:
        tmp.write(h5_bytes)
        tmp.close()

        with h5py.File(tmp.name, "r") as handle:
            group = handle["mcmc"]
            np.testing.assert_array_equal(group["chain"][:], backend.chain)
            np.testing.assert_array_equal(group["accepted"][:], backend.accepted)
            np.testing.assert_array_equal(group["log_prob"][:], backend.log_prob)
            assert group.attrs["iteration"] == backend.iteration
            assert group.attrs["thin"] == 2
            assert bool(group.attrs["has_blobs"]) is False
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# UV-vis / fluorescence linear observable tests
# ---------------------------------------------------------------------------


def _make_minimal_uvvis_fit():
    """Return (fit, model, expt_data, raw_data, lin_obs_col_names, lin_obs_param_map).

    Builds the smallest possible objects needed to exercise export_fit_notebook
    with linear observables, without going through the full StateManager fitting path.
    """
    from bindmc.webgui.classes.Model import Model
    from bindmc.webgui.classes.RawData import RawData
    from bindmc.webgui.classes.ExptData import ExptData
    from bindmc.webgui.classes.FitResult import FitResult

    from bindmc.webgui.classes.BindingConstant import BindingConstant as BC

    model = Model(
        name="1:1 UV-vis",
        component_names=["H", "G"],
        species=["H", "G", "HG"],
        eq_mat=np.array([[1, 1]], dtype=float),
        binding_constants=[BC(species="HG", logK=6.0, vary=True, min=0.0, max=14.0)],
    )

    raw = RawData(
        filename="test_uvvis.csv",
        data=pd.DataFrame(
            {
                "H_conc": np.linspace(1e-4, 1e-4, 10),
                "G_conc": np.linspace(0.0, 2e-4, 10),
                "absorbance": np.linspace(0.1, 0.5, 10),
            }
        ),
    )

    expt_data = ExptData(
        name="uv test",
        init_model=model,
        init_raw_data=raw,
        col_to_comp=np.array([[1, 0], [0, 1]], dtype=float),
        col_details={
            "H_conc": {"depindep": "indep", "dtype": "conc"},
            "G_conc": {"depindep": "indep", "dtype": "conc"},
            "absorbance": {"depindep": "dep", "dtype": "absorbance"},
        },
        selected_columns=["H_conc", "G_conc", "absorbance"],
    )

    fit = FitResult(
        model_id=model.id,
        expt_data_id=expt_data.id,
        name="uvvis_fit",
        description="",
        aic=100.0,
        bic=102.0,
        chisqr=0.01,
        termination_message="",
        success=True,
        params={
            "logH": {"value": 0.0, "initial_value": 0.0, "vary": False, "min": -2.0, "max": 2.0, "stderr": None},
            "logG": {"value": 0.0, "initial_value": 0.0, "vary": False, "min": -2.0, "max": 2.0, "stderr": None},
            "logHG": {"value": 6.0, "initial_value": 4.0, "vary": True, "min": 0.0, "max": 14.0, "stderr": 0.05},
            "eps_H_absorbance": {
                "value": 1000.0,
                "initial_value": 800.0,
                "vary": True,
                "min": 0.1,
                "max": 1e6,
                "stderr": 10.0,
            },
            "eps_G_absorbance": {
                "value": 0.0,
                "initial_value": 0.0,
                "vary": False,
                "min": -1e-9,
                "max": 1e-9,
                "stderr": None,
            },
            "eps_HG_absorbance": {
                "value": 5000.0,
                "initial_value": 3000.0,
                "vary": True,
                "min": 0.1,
                "max": 1e6,
                "stderr": 50.0,
            },
        },
        init_model=model,
        init_expt_data=expt_data,
    )

    lin_obs_col_names = ["absorbance"]
    lin_obs_param_map = [
        [
            {"name": "eps_H_absorbance", "min": 0.1, "max": 1e6},
            {"name": "eps_G_absorbance", "min": -1e-9, "max": 1e-9},
            {"name": "eps_HG_absorbance", "min": 0.1, "max": 1e6},
        ]
    ]

    expt_data.find_and_link_model({"dummy": model, model.id: model})

    return fit, model, expt_data, raw, lin_obs_col_names, lin_obs_param_map


def test_fit_notebook_uvvis_numerical():
    """export_fit_notebook with lin_obs_* kwargs injects specToLinear for numerical path."""
    from bindmc.webgui.export.notebook_exporter import export_fit_notebook

    fit, model, expt_data, raw, lin_obs_col_names, lin_obs_param_map = _make_minimal_uvvis_fit()

    obs_type_names = [expt_data.col_details[col]["dtype"] for col in expt_data.sorted_data.columns]

    notebook, _ = export_fit_notebook(
        fit,
        model,
        expt_data,
        raw,
        obs_type_names=obs_type_names,
        lin_obs_col_names=lin_obs_col_names,
        lin_obs_param_map=lin_obs_param_map,
    )

    code_cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
    all_code = "\n".join(c["source"] for c in code_cells)

    assert "spec_to_linear" in all_code
    assert "m.specToLinear" in all_code
    assert "eps_H_absorbance" in all_code
    assert "eps_HG_absorbance" in all_code

    # Analytical map should NOT appear for a plain numerical fit
    assert "analytical_linear_obs_param_map" not in all_code

    # No webgui / nicegui leakage
    assert "nicegui" not in all_code
    assert "webgui" not in all_code


def test_fit_notebook_uvvis_via_state_manager():
    """StateManager.dump_fit_notebook includes specToLinear when expt_data has UV-vis cols."""
    from bindmc.webgui.classes.Model import Model
    from bindmc.webgui.classes.RawData import RawData
    from bindmc.webgui.classes.ExptData import ExptData
    from bindmc.webgui.classes.FitResult import FitResult
    from bindmc.webgui.classes.ExptDataType import ExptDataType

    sm = StateManager(load_prior_state=False)

    from bindmc.webgui.classes.BindingConstant import BindingConstant as BC

    model = Model(
        name="1:1 UV-vis SM",
        component_names=["H", "G"],
        species=["H", "G", "HG"],
        eq_mat=np.array([[1, 1]], dtype=float),
        binding_constants=[BC(species="HG", logK=6.0, vary=True, min=0.0, max=14.0)],
    )
    sm.models[model.id] = model

    raw = RawData(
        filename="sm_uvvis.csv",
        data=pd.DataFrame(
            {
                "H_conc": np.full(10, 1e-4),
                "G_conc": np.linspace(0.0, 2e-4, 10),
                "absorbance": np.linspace(0.1, 0.5, 10),
            }
        ),
    )
    sm.raw_datas[raw.id] = raw

    expt_data = ExptData(
        name="sm uv test",
        init_model=model,
        init_raw_data=raw,
        col_to_comp=np.array([[1, 0], [0, 1]], dtype=float),
        col_details={
            "H_conc": {"depindep": "indep", "dtype": "conc"},
            "G_conc": {"depindep": "indep", "dtype": "conc"},
            "absorbance": {"depindep": "dep", "dtype": "absorbance"},
        },
        selected_columns=["H_conc", "G_conc", "absorbance"],
    )
    sm.expt_datas[expt_data.id] = expt_data

    # Register the absorbance ExptDataType so has_linear_obs() returns True
    sm._expt_dtypes["absorbance"] = ExptDataType(name="absorbance", init_meas="uvvis")

    fit = FitResult(
        model_id=model.id,
        expt_data_id=expt_data.id,
        name="sm_uvvis_fit",
        description="",
        aic=100.0,
        bic=102.0,
        chisqr=0.01,
        termination_message="",
        success=True,
        params={
            "logH": {"value": 0.0, "initial_value": 0.0, "vary": False, "min": -2.0, "max": 2.0, "stderr": None},
            "logG": {"value": 0.0, "initial_value": 0.0, "vary": False, "min": -2.0, "max": 2.0, "stderr": None},
            "logHG": {"value": 6.0, "initial_value": 4.0, "vary": True, "min": 0.0, "max": 14.0, "stderr": 0.05},
            "eps_H_absorbance": {
                "value": 1000.0,
                "initial_value": 800.0,
                "vary": True,
                "min": 0.1,
                "max": 1e6,
                "stderr": 10.0,
            },
            "eps_HG_absorbance": {
                "value": 5000.0,
                "initial_value": 3000.0,
                "vary": True,
                "min": 0.1,
                "max": 1e6,
                "stderr": 50.0,
            },
        },
        init_model=model,
        init_expt_data=expt_data,
    )
    sm.fits[fit.id] = fit

    notebook, csv_df = sm.dump_fit_notebook(fit)

    code_cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
    all_code = "\n".join(c["source"] for c in code_cells)

    assert "m.specToLinear" in all_code
    assert "nicegui" not in all_code
    assert "webgui" not in all_code


def test_fit_notebook_no_linear_obs_unaffected():
    """A standard NMR fit notebook must NOT contain specToLinear."""
    sm = _load_state_1to1()
    fit = sm.active_fit

    notebook, _ = sm.dump_fit_notebook(fit)

    all_code = "\n".join(c["source"] for c in notebook["cells"] if c["cell_type"] == "code")

    assert "specToLinear" not in all_code
    assert "analytical_linear_obs_param_map" not in all_code
