import numpy as np
import pandas as pd

import bindtools.binding as bd
from bindmc.webgui.classes import BindingConstant, ChemicalShiftParam, ExptData, FitResult, Model, RawData
from bindmc.webgui.components.fitting import _infer_analytical_fast_exchange_config
from bindmc.webgui.state import StateManager


def _new_state_manager() -> StateManager:
    sm = StateManager(load_prior_state=False)
    sm._listeners.clear()
    return sm


def _build_state(
    eq_mat: np.ndarray,
    species: list[str],
    shift_species: list[str],
    data: pd.DataFrame | None = None,
) -> tuple[StateManager, Model, ExptData]:
    sm = _new_state_manager()
    model = Model(
        name="analytical-test",
        eq_mat=eq_mat,
        component_names=["H", "G"],
        species=species,
    )
    model.binding_constants = [
        BindingConstant(species="H", logK=0.0, vary=False, isComp=True),
        BindingConstant(species="G", logK=0.0, vary=False, isComp=True),
        *[BindingConstant(species=s, logK=4.0, vary=True, isComp=False) for s in species[2:]],
    ]
    sm.add_model(model)

    if data is None:
        data = pd.DataFrame(
            {
                "H_tot": np.linspace(1.0e-3, 1.0e-3, 8),
                "G_tot": np.linspace(0.0, 2.0e-3, 8),
                "dH": np.linspace(7.0, 8.0, 8),
            }
        )

    raw = RawData(filename="raw.csv", data=data)
    sm.add_raw_data(raw)

    expt = ExptData(name="expt", init_model=model, init_raw_data=raw)
    expt.col_to_comp = np.array([[1.0, 0.0], [0.0, 1.0]])
    expt.col_details = {
        "H_tot": {"depindep": "indep", "dtype": "conc"},
        "G_tot": {"depindep": "indep", "dtype": "conc"},
        "dH": {"depindep": "dep", "dtype": "delta h"},
    }
    for spec_name in shift_species:
        expt.limiting_shifts[(spec_name, "dH")] = ChemicalShiftParam(
            species=spec_name,
            col="dH",
            fixed=False,
        )
    sm.add_expt_data(expt)
    sm.active_model_id = model.id
    sm.active_raw_data_id = raw.id
    sm.active_expt_data_id = expt.id
    return sm, model, expt


def _delta_11(host_tot: np.ndarray, guest_tot: np.ndarray, beta11: float, d0: float, amp: float) -> np.ndarray:
    term = host_tot + guest_tot + 1.0 / beta11
    disc = np.maximum(term**2 - 4.0 * host_tot * guest_tot, 0.0)
    hg = 0.5 * (term - np.sqrt(disc))
    frac = np.divide(hg, host_tot, out=np.zeros_like(hg), where=host_tot > 0)
    return d0 + amp * frac


def test_generate_binding_model_selects_analytical_backend_for_11():
    sm, model_obj, expt_obj = _build_state(
        eq_mat=np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 1.0]]),
        species=["H", "G", "HG"],
        shift_species=["H_free"],
    )

    cfg = _infer_analytical_fast_exchange_config(model_obj, expt_obj, sm._expt_dtypes)
    assert cfg is not None
    model = sm.generate_binding_model_for_fit(analytical_cfg=cfg)
    assert model.analytical_fast_exchange is True
    assert model.analytical_topology == "1:1"
    assert model.analytical_complex_indices == [2]


def test_generate_binding_model_selects_analytical_backend_for_12_and_21():
    sm12, m12_obj, ex12_obj = _build_state(
        eq_mat=np.array([[1.0, 0.0, 1.0, 1.0], [0.0, 1.0, 1.0, 2.0]]),
        species=["H", "G", "HG", "HG2"],
        shift_species=["H_free"],
    )
    cfg12 = _infer_analytical_fast_exchange_config(m12_obj, ex12_obj, sm12._expt_dtypes)
    assert cfg12 is not None
    m12 = sm12.generate_binding_model_for_fit(analytical_cfg=cfg12)
    assert m12.analytical_fast_exchange is True
    assert m12.analytical_topology == "1:2"
    assert m12.analytical_complex_indices == [2, 3]

    sm21, m21_obj, ex21_obj = _build_state(
        eq_mat=np.array([[1.0, 0.0, 1.0, 2.0], [0.0, 1.0, 1.0, 1.0]]),
        species=["H", "G", "HG", "H2G"],
        shift_species=["H_free"],
    )
    cfg21 = _infer_analytical_fast_exchange_config(m21_obj, ex21_obj, sm21._expt_dtypes)
    assert cfg21 is not None
    m21 = sm21.generate_binding_model_for_fit(analytical_cfg=cfg21)
    assert m21.analytical_fast_exchange is True
    assert m21.analytical_topology == "2:1"
    assert m21.analytical_complex_indices == [2, 3]


def test_generate_binding_model_infers_component_when_mapping_ambiguous():
    sm, model_obj, expt_obj = _build_state(
        eq_mat=np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 1.0]]),
        species=["H", "G", "HG"],
        shift_species=["H_free", "G_free"],
    )

    cfg = _infer_analytical_fast_exchange_config(model_obj, expt_obj, sm._expt_dtypes)
    assert cfg is not None
    assert cfg["obs_components"] == [0]
    model = sm.generate_binding_model_for_fit(analytical_cfg=cfg)
    assert model.analytical_fast_exchange is True


def test_generate_binding_model_uses_analytical_config_stored_on_fit():
    sm, model_obj, expt_obj = _build_state(
        eq_mat=np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 1.0]]),
        species=["H", "G", "HG"],
        shift_species=["H_free"],
    )
    cfg = _infer_analytical_fast_exchange_config(model_obj, expt_obj, sm._expt_dtypes)
    assert cfg is not None

    fit = FitResult(
        model_id=model_obj.id,
        expt_data_id=expt_obj.id,
        name="fit-analytical",
        description="",
        aic=0.0,
        bic=0.0,
        chisqr=0.0,
        termination_message="ok",
        init_model=model_obj,
        init_expt_data=expt_obj,
        analytical_fast_exchange=True,
        analytical_topology=str(cfg["topology"]),
        analytical_obs_columns=[str(x) for x in cfg["obs_columns"]],
        analytical_obs_components=[int(x) for x in cfg["obs_components"]],
        analytical_complex_indices=[int(x) for x in cfg["complex_indices"]],
    )
    sm.add_fit(fit)

    model = sm.generate_binding_model_for_fit(fit)
    assert model.analytical_fast_exchange is True
    assert model.analytical_topology == "1:1"
    assert model.analytical_complex_indices == [2]


def test_analytical_11_fit_recovers_log_beta_and_returns_calc_data():
    true_log_beta = 5.0
    host_tot = np.linspace(1.0e-3, 1.0e-3, 24)
    guest_tot = np.linspace(0.0, 2.2e-3, 24)
    delta = _delta_11(host_tot, guest_tot, beta11=10**true_log_beta, d0=7.0, amp=1.2)
    data = pd.DataFrame({"H_tot": host_tot, "G_tot": guest_tot, "dH": delta})

    sm, model_obj, expt = _build_state(
        eq_mat=np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 1.0]]),
        species=["H", "G", "HG"],
        shift_species=["H_free"],
        data=data,
    )

    cfg = _infer_analytical_fast_exchange_config(model_obj, expt, sm._expt_dtypes)
    assert cfg is not None
    model = sm.generate_binding_model_for_fit(analytical_cfg=cfg)
    assert model.analytical_fast_exchange is True
    assert "delta0_dH" in model.params
    assert "deltac1_dH" in model.params

    model.params["delta0_dH"].set(value=6.8)
    model.params["deltac1_dH"].set(value=1.0)

    fitted = model.runModel(ret=True, skip_col=np.shape(expt.col_to_comp)[0], method="least_squares")
    assert fitted is not None
    assert fitted.miniResult is not None

    fitted_log_beta = float(fitted.miniResult.params["logHG"].value)
    assert np.isfinite(fitted_log_beta)
    assert abs(fitted_log_beta - true_log_beta) < 0.35

    calc = bd.getCalcData(fitted)
    assert calc.shape == (len(data), 1)
    assert np.isfinite(calc).all()
