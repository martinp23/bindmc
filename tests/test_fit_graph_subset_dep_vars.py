import numpy as np
import pytest


import pandas as pd

from bindmc.webgui.classes import ExptData, FitResult, Model, RawData
from bindmc.webgui.components.fitting import _mapped_dependent_columns_for_fit, _prepare_fit_plot_frames


def _make_fit(
    expt_rows: int = 3,
    calc_rows: int = 3,
    integ_to_spec: np.ndarray | None = None,
    calc_cols: list[str] | None = None,
) -> FitResult:
    if calc_cols is None:
        calc_cols = ["obs_a", "obs_b"]

    raw = RawData(
        filename="raw.csv",
        data=pd.DataFrame(
            {
                "H_tot": np.linspace(1.0, 1.0, expt_rows),
                "G_tot": np.linspace(0.0, 0.2, expt_rows),
                "obs_a": np.linspace(10.0, 12.0, expt_rows),
                "obs_b": np.linspace(20.0, 22.0, expt_rows),
            }
        ),
    )
    model = Model(name="m", component_names=["H", "G"], species=["HG"])
    expt = ExptData(name="expt", init_model=model, init_raw_data=raw)
    expt.col_to_comp = np.array([[1.0, 0.0], [0.0, 1.0]])
    expt.col_details = {
        "H_tot": {"depindep": "indep"},
        "G_tot": {"depindep": "indep"},
        "obs_a": {"depindep": "dep"},
        "obs_b": {"depindep": "dep"},
    }
    if integ_to_spec is None:
        expt.integ_to_spec = np.array([[0.0, 0.0, 1.0, 0.0]])
    else:
        expt.integ_to_spec = integ_to_spec

    fit = FitResult(
        model_id=model.id,
        expt_data_id=expt.id,
        name="fit",
        description="",
        aic=0.0,
        bic=0.0,
        chisqr=0.0,
        termination_message="ok",
        init_model=model,
        init_expt_data=expt,
    )

    calc_data = {
        "obs_a": np.linspace(10.1, 11.9, calc_rows),
        "obs_b": np.full(calc_rows, np.nan),
    }
    fit.calc_obs = pd.DataFrame({k: v for k, v in calc_data.items() if k in calc_cols})
    return fit


def test_mapped_dependent_columns_selects_only_fitted_obs():
    fit = _make_fit()
    mapped = _mapped_dependent_columns_for_fit(fit)
    assert mapped == {"obs_a"}


def test_prepare_fit_plot_frames_filters_to_fitted_subset():
    fit = _make_fit()
    x_plot, calc_plot, expt_plot, skipped = _prepare_fit_plot_frames(fit)

    assert list(calc_plot.columns) == ["obs_a"]
    assert list(expt_plot.columns) == ["obs_a"]
    assert "obs_b" in skipped
    assert len(x_plot) == len(calc_plot) == len(expt_plot) == 3


def test_prepare_fit_plot_frames_aligns_row_lengths():
    fit = _make_fit(expt_rows=5, calc_rows=3)
    x_plot, calc_plot, expt_plot, _ = _prepare_fit_plot_frames(fit)
    assert len(x_plot) == 3
    assert len(calc_plot) == 3
    assert len(expt_plot) == 3


def test_prepare_fit_plot_frames_falls_back_when_mapping_absent():
    # Legacy-style fit: no mapped dependent columns, but calc data still valid.
    fit = _make_fit(integ_to_spec=np.zeros((1, 4)), calc_cols=["obs_a"])
    x_plot, calc_plot, expt_plot, _ = _prepare_fit_plot_frames(fit)

    assert list(calc_plot.columns) == ["obs_a"]
    assert list(expt_plot.columns) == ["obs_a"]
    assert not x_plot.empty


def test_prepare_fit_plot_frames_keeps_all_dep_cols_for_analytical_fast_exchange():
    fit = _make_fit()
    # Simulate analytical fast-exchange output with multiple valid dependent vectors.
    fit.analytical_fast_exchange = True
    fit.calc_obs["obs_b"] = np.linspace(20.1, 21.9, len(fit.calc_obs))

    x_plot, calc_plot, expt_plot, skipped = _prepare_fit_plot_frames(fit)

    assert list(calc_plot.columns) == ["obs_a", "obs_b"]
    assert list(expt_plot.columns) == ["obs_a", "obs_b"]
    assert skipped == []
    assert len(x_plot) == len(calc_plot) == len(expt_plot)


def test_prepare_fit_plot_frames_isolated_when_expt_data_mutates():
    """
    Regression test: when fit1 has 2 columns (obs_a, obs_b) and fit2 has 1 column (obs_a),
    and they share expt_data, fit1 should still plot both columns even after expt_data.col_details
    is updated to only include obs_a.
    """
    # Create fit1 with 2 calc columns
    fit1 = _make_fit(calc_cols=["obs_a", "obs_b"])
    fit1.calc_obs["obs_b"] = np.linspace(20.1, 21.9, len(fit1.calc_obs))

    # Create fit2 with 1 calc column, sharing fit1's expt_data
    fit2 = _make_fit(calc_cols=["obs_a"])
    fit2.expt_data = fit1.expt_data  # Share the same ExptData

    # Simulate fit2 being run, which would update shared col_details to only mark obs_a as dependent
    fit2.expt_data.col_details["obs_b"]["depindep"] = "indep"

    # Now when we render fit1, it should still show both columns (not be affected by fit2's changes)
    x_plot, calc_plot, expt_plot, skipped = _prepare_fit_plot_frames(fit1)

    # fit1 produced both obs_a and obs_b in calc_obs, so they should both be plotted
    assert set(calc_plot.columns) == {"obs_a", "obs_b"}, \
        f"fit1 should plot both columns it produced, but got {list(calc_plot.columns)}"
    assert len(x_plot) == len(calc_plot) == len(expt_plot)
