import importlib
import json
import queue
import uuid
from unittest.mock import patch

import pandas as pd

from bindmc.webgui.classes import ExptData, FitResult, MCMCSim, RawData, Simulation
from bindmc.webgui.state import StateManager


class _FakeEvent:
    def __init__(self):
        self._is_set = False

    def is_set(self) -> bool:
        return self._is_set

    def set(self) -> None:
        self._is_set = True

    def clear(self) -> None:
        self._is_set = False


class _FakeManager:
    def Event(self):
        return _FakeEvent()

    def Queue(self):
        return queue.Queue()

    def Value(self, param, val):
        return val


def _new_state_manager() -> StateManager:
    sm = StateManager(load_prior_state=False)
    # These tests validate state reconciliation, not UI/storage side effects.
    # Clearing listeners avoids `app.storage.user` access when no app context exists.
    sm._listeners.clear()
    return sm


def _new_mcmc(model, expt) -> MCMCSim:
    mcmc_module = importlib.import_module("bindmc.webgui.classes.MCMCSim")
    with patch.object(mcmc_module, "Manager", new=lambda: _FakeManager()):
        return MCMCSim(model=model, expt_data=expt)


def _new_model(sm: StateManager, name: str):
    model_id = sm.new_model(name)
    return sm.models[model_id]


def _add_raw_and_expt(sm: StateManager, model, stem: str):
    raw = RawData(
        filename=f"{stem}.csv",
        data=pd.DataFrame({"x": [0.0, 1.0], "y": [0.1, 0.2]}),
    )
    sm.add_raw_data(raw)
    expt = ExptData(name=stem, init_model=model, init_raw_data=raw)
    expt.col_details = {col: {"depindep": "dep", "dtype": "conc"} for col in expt.columns}
    sm.add_expt_data(expt)
    return raw, expt


def _add_fit(sm: StateManager, model, expt, name: str):
    fit = FitResult(
        model_id=model.id,
        expt_data_id=expt.id,
        name=name,
        description="",
        aic=0.0,
        bic=0.0,
        chisqr=0.0,
        termination_message="ok",
        init_model=model,
        init_expt_data=expt,
    )
    sm.add_fit(fit)
    return fit


def _assert_active_ids_valid(sm: StateManager):
    assert sm.active_model_id in sm.models
    assert sm.active_raw_data_id is None or sm.active_raw_data_id in sm.raw_datas
    assert sm.active_expt_data_id is None or sm.active_expt_data_id in sm.expt_datas
    assert sm.active_fit_id is None or sm.active_fit_id in sm.fits
    assert sm.active_sim_id is None or sm.active_sim_id in sm.simulations
    assert sm.active_mcmc_id is None or sm.active_mcmc_id in sm.mcmcs


def test_delete_active_fit_reconciles_to_contextual_fallback():
    sm = _new_state_manager()
    model = _new_model(sm, "model-fit-fallback")
    sm.active_model_id = model.id

    raw_1, expt_1 = _add_raw_and_expt(sm, model, "expt-1")
    _, expt_2 = _add_raw_and_expt(sm, model, "expt-2")
    sm.active_raw_data_id = raw_1.id
    sm.active_expt_data_id = expt_1.id

    fit_1 = _add_fit(sm, model, expt_1, "fit-1")
    _add_fit(sm, model, expt_2, "fit-2")
    fit_3 = _add_fit(sm, model, expt_1, "fit-3")

    sm.active_fit_id = fit_1.id
    sm.delete_fit(fit_1)

    assert fit_1.id not in sm.fits
    assert sm.active_fit_id == fit_3.id
    _assert_active_ids_valid(sm)


def test_delete_expt_data_cascades_fit_and_mcmc_and_reselects():
    sm = _new_state_manager()
    model = _new_model(sm, "model-expt-delete")
    sm.active_model_id = model.id

    _, expt_1 = _add_raw_and_expt(sm, model, "expt-a")
    _, expt_2 = _add_raw_and_expt(sm, model, "expt-b")
    fit_1 = _add_fit(sm, model, expt_1, "fit-a")
    fit_2 = _add_fit(sm, model, expt_2, "fit-b")

    mcmc_1 = _new_mcmc(model, expt_1)
    sm.add_mcmc(mcmc_1)

    sm.active_expt_data_id = expt_1.id
    sm.active_fit_id = fit_1.id
    sm.active_mcmc_id = mcmc_1.id
    sm.delete_expt_data(expt_1)

    assert expt_1.id not in sm.expt_datas
    assert fit_1.id not in sm.fits
    assert mcmc_1.id not in sm.mcmcs
    assert sm.active_expt_data_id == expt_2.id
    assert sm.active_fit_id == fit_2.id
    _assert_active_ids_valid(sm)


def test_delete_raw_data_cascades_and_reconciles_expt_and_fit():
    sm = _new_state_manager()
    model = _new_model(sm, "model-raw-delete")
    sm.active_model_id = model.id

    raw_1, expt_1 = _add_raw_and_expt(sm, model, "raw-a")
    raw_2, expt_2 = _add_raw_and_expt(sm, model, "raw-b")
    fit_1 = _add_fit(sm, model, expt_1, "fit-a")
    fit_2 = _add_fit(sm, model, expt_2, "fit-b")

    sm.active_raw_data_id = raw_1.id
    sm.active_expt_data_id = expt_1.id
    sm.active_fit_id = fit_1.id
    sm.delete_raw_data(raw_1)

    assert raw_1.id not in sm.raw_datas
    assert expt_1.id not in sm.expt_datas
    assert fit_1.id not in sm.fits
    assert sm.active_raw_data_id == raw_2.id
    assert sm.active_expt_data_id == expt_2.id
    assert sm.active_fit_id == fit_2.id
    _assert_active_ids_valid(sm)


def test_delete_active_model_cascade_keeps_valid_actives():
    sm = _new_state_manager()
    model_1 = _new_model(sm, "model-delete-a")
    model_2 = _new_model(sm, "model-delete-b")
    sm.active_model_id = model_1.id

    _, expt_1 = _add_raw_and_expt(sm, model_1, "model-a-expt")
    fit_1 = _add_fit(sm, model_1, expt_1, "model-a-fit")
    sim_1 = Simulation(model_id=model_1.id, name="model-a-sim")
    sm.add_sim(sim_1)
    mcmc_1 = _new_mcmc(model_1, expt_1)
    sm.add_mcmc(mcmc_1)

    sm.delete_model(model_1)

    assert model_1.id not in sm.models
    assert fit_1.id not in sm.fits
    assert sim_1.id not in sm.simulations
    assert expt_1.id not in sm.expt_datas
    assert mcmc_1.id not in sm.mcmcs
    assert sm.active_model_id in sm.models
    assert sm.active_model_id != model_1.id
    assert sm.active_model_id == model_2.id or sm.active_model_id is not None
    _assert_active_ids_valid(sm)


def test_from_json_stale_active_ids_are_reconciled():
    sm = _new_state_manager()
    model = _new_model(sm, "model-json")
    _, expt = _add_raw_and_expt(sm, model, "json-expt")
    _add_fit(sm, model, expt, "json-fit")

    data = sm.to_dict()
    data["active_model_id"] = str(uuid.uuid4())
    data["active_sim_id"] = str(uuid.uuid4())
    data["active_expt_data_id"] = str(uuid.uuid4())
    data["active_fit_id"] = str(uuid.uuid4())
    data["active_raw_data_id"] = str(uuid.uuid4())
    data["active_mcmc_id"] = str(uuid.uuid4())

    sm2 = _new_state_manager()
    sm2.from_json(json.dumps(data))

    _assert_active_ids_valid(sm2)


def test_safe_getters_return_none_without_active():
    sm = _new_state_manager()
    sm._active_fit_id = uuid.uuid4()
    sm._active_expt_data_id = uuid.uuid4()
    sm._active_raw_data_id = uuid.uuid4()
    sm._active_sim_id = uuid.uuid4()
    sm._active_mcmc_id = uuid.uuid4()

    assert sm.active_fit_or_none is None
    assert sm.active_expt_data_or_none is None
    assert sm.active_raw_data_or_none is None
    assert sm.active_sim_or_none is None
    assert sm.active_mcmc_or_none is None


def test_default_models_are_tracked_as_default_ids():
    sm = _new_state_manager()
    assert len(sm.models) > 0
    assert len(sm.default_model_ids) > 0
    assert set(sm.default_model_ids).issubset(set(sm.models.keys()))


def test_delete_default_model_is_blocked():
    sm = _new_state_manager()
    assert sm.default_model_ids, "Expected built-in defaults to be present."

    default_model_id = sm.default_model_ids[0]
    default_model = sm.models[default_model_id]
    n_before = len(sm.models)

    sm.delete_model(default_model, notify_user=False, notify_listeners=False)
    assert default_model_id in sm.models
    assert len(sm.models) == n_before


def test_mcmcsim_max_retained_points_serialization():
    sm = _new_state_manager()
    model = _new_model(sm, "model-mcmc")
    _, expt = _add_raw_and_expt(sm, model, "mcmc-expt")

    # Create MCMCSim with custom max_retained_points
    mcmc = _new_mcmc(model, expt)
    mcmc.max_retained_points = 2500
    sm.add_mcmc(mcmc)

    # Serialize
    data = sm.to_dict()

    # Verify max_retained_points is written
    mcmc_entries = data.get("mcmcs", [])
    assert len(mcmc_entries) == 1
    assert mcmc_entries[0]["max_retained_points"] == 2500

    # Deserialize back
    sm2 = _new_state_manager()
    sm2.from_json(json.dumps(data))
    assert sm2.mcmcs[mcmc.id].max_retained_points == 2500

    # Verify compatibility: delete max_retained_points from json, verify it falls back to 1000
    del data["mcmcs"][0]["max_retained_points"]
    sm3 = _new_state_manager()
    sm3.from_json(json.dumps(data))
    assert sm3.mcmcs[mcmc.id].max_retained_points == 1000


def test_delete_last_expt_data_creates_empty():
    sm = _new_state_manager()
    model = _new_model(sm, "model-delete-last")
    sm.active_model_id = model.id

    raw, expt = _add_raw_and_expt(sm, model, "expt-only")
    sm.active_raw_data_id = raw.id
    sm.active_expt_data_id = expt.id
    sm.reconcile_active_context()

    assert len(sm.expt_datas) == 1

    sm.delete_expt_data(expt)

    # A new empty ExptData should have been created and set as active
    assert len(sm.expt_datas) == 1
    new_expt = list(sm.expt_datas.values())[0]
    assert new_expt.id != expt.id
    assert new_expt.name == "expt-only.csv"
    assert sm.active_expt_data_id == new_expt.id
    assert sm.active_raw_data_id == raw.id

