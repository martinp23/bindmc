from types import SimpleNamespace

import numpy as np
import pandas as pd

from webgui.components.body import _compute_tab_disable_reasons, _format_disable_tooltip


def _state(
    *,
    model=None,
    expt=None,
    fit_id=None,
):
    return SimpleNamespace(
        active_model=model,
        active_expt_data_or_none=expt,
        active_fit_id=fit_id,
    )


def _model(*, valid=True, has_comp_concs=True):
    eq_str = "H + G <=> HG" if valid else ""
    binding_constants = [SimpleNamespace(logK=4.0)] if valid else [SimpleNamespace(logK=None)]
    component_concs = (
        pd.DataFrame({"H": [1e-3, 1e-3], "G": [0.0, 2e-3]})
        if has_comp_concs
        else pd.DataFrame()
    )
    return SimpleNamespace(
        eq_str=eq_str,
        binding_constants=binding_constants,
        component_concs=component_concs,
    )


def _expt(*, has_raw=True, has_data_model=False, analytical=False):
    raw_df = pd.DataFrame({"H_tot": [1e-3], "G_tot": [0.0], "dH": [7.0]}) if has_raw else pd.DataFrame()
    data_df = pd.DataFrame({"H_tot": [1e-3], "G_tot": [0.0], "dH": [7.0]})
    integ_to_spec = np.array([[0.0, 0.0, 1.0]]) if has_data_model else None
    limiting = {} if not has_data_model else {("H_free", "dH"): object()}
    return SimpleNamespace(
        data=data_df,
        raw_data=SimpleNamespace(data=raw_df),
        integ_to_spec=integ_to_spec,
        limiting_shifts=limiting,
        is_analytical_fast_ex=analytical,
    )


def test_disable_reasons_with_no_model_or_data():
    reasons = _compute_tab_disable_reasons(_state(model=None, expt=None, fit_id=None))
    assert ("Simulate", "Data Generation") in reasons
    assert ("Simulate", "Simulation") in reasons
    assert ("Fit", "Data model") in reasons
    assert ("Fit", "Fit results") in reasons
    assert ("Fit", "MCMC") in reasons


def test_fit_results_requires_data_model_when_not_analytical():
    sm = _state(
        model=_model(valid=True, has_comp_concs=True),
        expt=_expt(has_raw=True, has_data_model=False, analytical=False),
        fit_id=None,
    )
    reasons = _compute_tab_disable_reasons(sm)
    assert ("Fit", "Fit results") in reasons
    assert any("Configure a data model first" in msg for msg in reasons[("Fit", "Fit results")])
    assert ("Fit", "MCMC") in reasons
    assert any("Run a fit first" in msg for msg in reasons[("Fit", "MCMC")])


def test_analytical_flag_allows_fit_results_without_explicit_mapping():
    sm = _state(
        model=_model(valid=True, has_comp_concs=True),
        expt=_expt(has_raw=True, has_data_model=False, analytical=True),
        fit_id=None,
    )
    reasons = _compute_tab_disable_reasons(sm)
    assert ("Fit", "Fit results") not in reasons
    assert ("Fit", "MCMC") in reasons  # still blocked until a fit exists


def test_linear_observables_allow_fit_results_without_nmr_mapping():
    expt = _expt(has_raw=True, has_data_model=False, analytical=False)
    expt.has_linear_obs = lambda _dtypes: True
    sm = _state(
        model=_model(valid=True, has_comp_concs=True),
        expt=expt,
        fit_id=None,
    )
    reasons = _compute_tab_disable_reasons(sm)
    assert ("Fit", "Fit results") not in reasons
    assert ("Fit", "MCMC") in reasons  # still blocked until a fit exists


def test_format_disable_tooltip_handles_multiple_reasons():
    tooltip = _format_disable_tooltip(["reason A", "reason B"])
    assert "reason A" in tooltip
    assert "reason B" in tooltip
    assert "\n" in tooltip
