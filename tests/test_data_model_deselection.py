import numpy as np
import pandas as pd
import pytest
import importlib
from unittest.mock import MagicMock, patch

from bindmc.webgui.classes import ExptData, Model, RawData, ExptDataType, Component, ChemicalShiftParam, FitResult, MCMCSim
from bindmc.webgui.state import StateManager
from bindmc.webgui.components.data_model import DataModelPanel
from bindmc.webgui.components.data_import import DataImportPanel


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
        import queue
        return queue.Queue()

    def Value(self, param, val):
        return val


def _new_mcmc(model, expt) -> MCMCSim:
    mcmc_module = importlib.import_module("bindmc.webgui.classes.MCMCSim")
    with patch.object(mcmc_module, "Manager", new=lambda: _FakeManager()):
        return MCMCSim(model=model, expt_data=expt)


def setup_mock_ui(mock_ui_model, mock_ui_import, mock_ui_selector):
    # Mock NiceGUI UI elements to prevent startup crash
    mock_element = MagicMock()
    for mock_ui in (mock_ui_model, mock_ui_import, mock_ui_selector):
        mock_ui.column.return_value = mock_element
        mock_ui.row.return_value = mock_element
        mock_ui.card.return_value = mock_element
        mock_ui.chip.return_value = mock_element
        mock_ui.label.return_value = mock_element
        mock_ui.button.return_value = mock_element
        mock_ui.element.return_value = mock_element
        mock_ui.dropdown_button.return_value = mock_element

        def create_mock_input(*args, **kwargs):
            inp = MagicMock()
            inp.value = kwargs.get("value", "")
            inp.bind_enabled_from = MagicMock()
            inp.on = MagicMock()
            return inp
        mock_ui.input.side_effect = create_mock_input

        def create_mock_checkbox(*args, **kwargs):
            cb = MagicMock()
            cb.value = kwargs.get("value", False)
            cb.on_value_change = MagicMock()
            return cb
        mock_ui.checkbox.side_effect = create_mock_checkbox


@patch("bindmc.webgui.components.data_import.Graph")
@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_import.ui")
@patch("bindmc.webgui.components.data_model.ui")
def test_data_model_deselection_inplace(mock_ui_model, mock_ui_import, mock_ui_selector, mock_graph):
    setup_mock_ui(mock_ui_model, mock_ui_import, mock_ui_selector)

    # 1. Setup a StateManager and a Model
    sm = StateManager(load_prior_state=False)
    model = Model(
        name="Test Model",
        component_names=["H", "G"],
        components=[Component(name="H"), Component(name="G")],
        species=["HG"]
    )
    sm.models[model.id] = model
    sm.active_model_id = model.id

    # Add default experimental data types
    sm._expt_dtypes["conc"] = ExptDataType(name="Conc.", init_meas="grav_vol", units="M")
    sm._expt_dtypes["delta h"] = ExptDataType(name="H (ppm)", init_meas="nmr_ppm", units="ppm")

    # 2. Setup RawData
    raw = RawData(
        filename="test_data.csv",
        data=pd.DataFrame({
            "htot": np.linspace(1.0, 1.0, 5),
            "h1": np.linspace(2.0, 2.0, 5),
            "h2": np.linspace(3.0, 3.0, 5),
            "h3": np.linspace(4.0, 4.0, 5),
            "ltot": np.linspace(5.0, 5.0, 5)
        })
    )
    sm.raw_datas[raw.id] = raw
    sm.active_raw_data_id = raw.id

    # 3. Setup ExptData mapping component concentrations and dependent variables
    expt = ExptData(name="test_expt", init_model=model, init_raw_data=raw)
    expt.selected_columns = ["htot", "h1", "h2", "h3", "ltot"]
    expt.col_details = {
        "htot": {"depindep": "indep", "dtype": "conc"},
        "h1": {"depindep": "dep", "dtype": "delta h"},
        "h2": {"depindep": "dep", "dtype": "delta h"},
        "h3": {"depindep": "dep", "dtype": "delta h"},
        "ltot": {"depindep": "indep", "dtype": "conc"}
    }
    expt.col_to_comp = np.array([
        [1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 1.0]
    ])
    expt._matrix_columns = list(expt.selected_columns)

    sm.add_expt_data(expt)

    # 4. Instantiate DataImportPanel
    import_panel = DataImportPanel(sm)
    assert import_panel._restore_point is not None
    assert import_panel._restore_point.id == expt.id

    # 5. Deselect one of the dependent columns: e.g. "h3" (index 3)
    col_to_deselect = "h3"
    expt.col_details[col_to_deselect]["depindep"] = None
    expt.col_details[col_to_deselect]["dtype"] = None
    if col_to_deselect in expt.selected_columns:
        expt.selected_columns.remove(col_to_deselect)

    # 6. Click prepare data model (calls prepare_data_model)
    # Since there is NO existing work (no limiting shifts, delta_to_spec size is empty, no fits),
    # this will reconcile the active_expt in-place.
    import_panel.prepare_data_model(None)

    # Assert that no new ExptData was added to StateManager (len remains 1)
    assert len(sm.expt_datas) == 1

    # Assert the active expt is reconciled in-place
    active_expt = sm.active_expt_data
    assert "h3" not in active_expt.selected_columns
    assert active_expt.col_to_comp.shape == (2, 4)
    # index of ltot in active_expt.selected_columns is now 3. So it must be mapped to index 3 in col_to_comp.
    assert active_expt.col_to_comp[1, 3] == 1.0

    # 7. Opening DataModelPanel should not raise any IndexError
    panel = DataModelPanel(state_manager=sm)
    assert len(panel.compConcInps) == 2


@patch("bindmc.webgui.components.data_import.Graph")
@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_import.ui")
@patch("bindmc.webgui.components.data_model.ui")
def test_data_model_deselection_rename_with_work(mock_ui_model, mock_ui_import, mock_ui_selector, mock_graph):
    setup_mock_ui(mock_ui_model, mock_ui_import, mock_ui_selector)

    # 1. Setup a StateManager and a Model
    sm = StateManager(load_prior_state=False)
    model = Model(
        name="Test Model",
        component_names=["H", "G"],
        components=[Component(name="H"), Component(name="G")],
        species=["HG"]
    )
    sm.models[model.id] = model
    sm.active_model_id = model.id

    # Add default experimental data types
    sm._expt_dtypes["conc"] = ExptDataType(name="Conc.", init_meas="grav_vol", units="M")
    sm._expt_dtypes["delta h"] = ExptDataType(name="H (ppm)", init_meas="nmr_ppm", units="ppm")

    # 2. Setup RawData
    raw = RawData(
        filename="test_data.csv",
        data=pd.DataFrame({
            "htot": np.linspace(1.0, 1.0, 5),
            "h1": np.linspace(2.0, 2.0, 5),
            "h2": np.linspace(3.0, 3.0, 5),
            "h3": np.linspace(4.0, 4.0, 5),
            "ltot": np.linspace(5.0, 5.0, 5)
        })
    )
    sm.raw_datas[raw.id] = raw
    sm.active_raw_data_id = raw.id

    # 3. Setup ExptData mapping component concentrations and dependent variables
    expt = ExptData(name="test_expt", init_model=model, init_raw_data=raw)
    expt.selected_columns = ["htot", "h1", "h2", "h3", "ltot"]
    expt.col_details = {
        "htot": {"depindep": "indep", "dtype": "conc"},
        "h1": {"depindep": "dep", "dtype": "delta h"},
        "h2": {"depindep": "dep", "dtype": "delta h"},
        "h3": {"depindep": "dep", "dtype": "delta h"},
        "ltot": {"depindep": "indep", "dtype": "conc"}
    }
    expt.col_to_comp = np.array([
        [1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 1.0]
    ])
    expt._matrix_columns = list(expt.selected_columns)
    # Setup some dummy fast exchange delta_to_spec data to simulate model configuration work
    expt.delta_to_spec = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0]
    ], dtype=object)

    sm.add_expt_data(expt)

    # 4. Instantiate DataImportPanel
    import_panel = DataImportPanel(sm)

    # 5. Deselect one of the dependent columns: e.g. "h3" (index 3)
    col_to_deselect = "h3"
    expt.col_details[col_to_deselect]["depindep"] = None
    expt.col_details[col_to_deselect]["dtype"] = None
    if col_to_deselect in expt.selected_columns:
        expt.selected_columns.remove(col_to_deselect)

    # 6. We expect a prompt, and if we select "Rename (Create New)"
    # we call prepare_data_model_rename directly.
    import_panel.prepare_data_model_rename(expt)

    # Assert that a new ExptData was added to StateManager (len is 2)
    assert len(sm.expt_datas) == 2

    # Assert the original is preserved and restored from backup
    orig_expt = sm.expt_datas[expt.id]
    assert "h3" in orig_expt.selected_columns
    assert orig_expt.col_details["h3"]["depindep"] == "dep"

    # Assert the new one is versioned and has reconciled matrices
    new_expt = next(ed for ed in sm.expt_datas.values() if ed.id != expt.id)
    assert new_expt.name == "test_expt v2"
    assert "h3" not in new_expt.selected_columns
    assert new_expt.col_to_comp.shape == (2, 4)
    assert new_expt.col_to_comp[1, 3] == 1.0

    # 7. Opening DataModelPanel for the new versioned data should not raise any IndexError
    sm.active_expt_data_id = new_expt.id
    panel = DataModelPanel(state_manager=sm)
    assert len(panel.compConcInps) == 2


@patch("bindmc.webgui.components.data_import.Graph")
@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_import.ui")
@patch("bindmc.webgui.components.data_model.ui")
def test_data_model_addition_inplace(mock_ui_model, mock_ui_import, mock_ui_selector, mock_graph):
    setup_mock_ui(mock_ui_model, mock_ui_import, mock_ui_selector)

    # 1. Setup a StateManager and a Model
    sm = StateManager(load_prior_state=False)
    model = Model(
        name="Test Model",
        component_names=["H", "G"],
        components=[Component(name="H"), Component(name="G")],
        species=["HG"]
    )
    sm.models[model.id] = model
    sm.active_model_id = model.id

    # Add default experimental data types
    sm._expt_dtypes["conc"] = ExptDataType(name="Conc.", init_meas="grav_vol", units="M")
    sm._expt_dtypes["delta h"] = ExptDataType(name="H (ppm)", init_meas="nmr_ppm", units="ppm")

    # 2. Setup RawData
    raw = RawData(
        filename="test_data.csv",
        data=pd.DataFrame({
            "htot": np.linspace(1.0, 1.0, 5),
            "ltot": np.linspace(5.0, 5.0, 5),
            "h1": np.linspace(2.0, 2.0, 5),
            "h2": np.linspace(3.0, 3.0, 5),
            "h3": np.linspace(4.0, 4.0, 5)
        })
    )
    sm.raw_datas[raw.id] = raw
    sm.active_raw_data_id = raw.id

    # 3. Setup ExptData mapping component concentrations and dependent variables (initially 2 dependent)
    expt = ExptData(name="test_expt", init_model=model, init_raw_data=raw)
    expt.selected_columns = ["htot", "ltot", "h1", "h2"]
    expt.col_details = {
        "htot": {"depindep": "indep", "dtype": "conc"},
        "ltot": {"depindep": "indep", "dtype": "conc"},
        "h1": {"depindep": "dep", "dtype": "delta h"},
        "h2": {"depindep": "dep", "dtype": "delta h"},
        "h3": {"depindep": None, "dtype": None}
    }
    expt.col_to_comp = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0]
    ])
    expt._matrix_columns = list(expt.selected_columns)

    sm.add_expt_data(expt)

    # 4. Instantiate DataImportPanel
    import_panel = DataImportPanel(sm)

    # 5. Add a new dependent column: "h3" (index 4)
    col_to_add = "h3"
    expt.col_details[col_to_add]["depindep"] = "dep"
    expt.col_details[col_to_add]["dtype"] = "delta h"
    expt.selected_columns.append(col_to_add)

    # 6. Click prepare data model (calls prepare_data_model)
    # Since there is NO existing work (no limiting shifts, delta_to_spec size is empty, no fits),
    # this will reconcile the active_expt in-place.
    import_panel.prepare_data_model(None)

    # Assert that no new ExptData was added to StateManager (len remains 1)
    assert len(sm.expt_datas) == 1

    # Assert the active expt is reconciled in-place
    active_expt = sm.active_expt_data
    assert "h3" in active_expt.selected_columns
    assert active_expt.col_to_comp.shape == (2, 5)

    # 7. Opening DataModelPanel should not raise any IndexError
    panel = DataModelPanel(state_manager=sm)
    assert len(panel.compConcInps) == 2


@patch("bindmc.webgui.components.data_import.Graph")
@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_import.ui")
@patch("bindmc.webgui.components.data_model.ui")
def test_data_model_addition_rename_with_work(mock_ui_model, mock_ui_import, mock_ui_selector, mock_graph):
    setup_mock_ui(mock_ui_model, mock_ui_import, mock_ui_selector)

    # 1. Setup a StateManager and a Model
    sm = StateManager(load_prior_state=False)
    model = Model(
        name="Test Model",
        component_names=["H", "G"],
        components=[Component(name="H"), Component(name="G")],
        species=["HG"]
    )
    sm.models[model.id] = model
    sm.active_model_id = model.id

    # Add default experimental data types
    sm._expt_dtypes["conc"] = ExptDataType(name="Conc.", init_meas="grav_vol", units="M")
    sm._expt_dtypes["delta h"] = ExptDataType(name="H (ppm)", init_meas="nmr_ppm", units="ppm")

    # 2. Setup RawData
    raw = RawData(
        filename="test_data.csv",
        data=pd.DataFrame({
            "htot": np.linspace(1.0, 1.0, 5),
            "ltot": np.linspace(5.0, 5.0, 5),
            "h1": np.linspace(2.0, 2.0, 5),
            "h2": np.linspace(3.0, 3.0, 5),
            "h3": np.linspace(4.0, 4.0, 5)
        })
    )
    sm.raw_datas[raw.id] = raw
    sm.active_raw_data_id = raw.id

    # 3. Setup ExptData mapping component concentrations and dependent variables (initially 2 dependent)
    expt = ExptData(name="test_expt", init_model=model, init_raw_data=raw)
    expt.selected_columns = ["htot", "ltot", "h1", "h2"]
    expt.col_details = {
        "htot": {"depindep": "indep", "dtype": "conc"},
        "ltot": {"depindep": "indep", "dtype": "conc"},
        "h1": {"depindep": "dep", "dtype": "delta h"},
        "h2": {"depindep": "dep", "dtype": "delta h"},
        "h3": {"depindep": None, "dtype": None}
    }
    expt.col_to_comp = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0]
    ])
    expt._matrix_columns = list(expt.selected_columns)
    expt.delta_to_spec = np.array([
        [1.0, 0.0, 0.0],  # 3 species
        [0.0, 1.0, 0.0]
    ], dtype=object)

    sm.add_expt_data(expt)

    # 4. Instantiate DataImportPanel
    import_panel = DataImportPanel(sm)

    # 5. Add a new dependent column: "h3" (index 4)
    col_to_add = "h3"
    expt.col_details[col_to_add]["depindep"] = "dep"
    expt.col_details[col_to_add]["dtype"] = "delta h"
    expt.selected_columns.append(col_to_add)

    # 6. We expect a prompt, and if we select "Rename (Create New)"
    # we call prepare_data_model_rename directly.
    import_panel.prepare_data_model_rename(expt)

    # Assert that a new ExptData was added to StateManager (len is 2)
    assert len(sm.expt_datas) == 2

    # Assert the original is preserved and restored from backup
    orig_expt = sm.expt_datas[expt.id]
    assert "h3" not in orig_expt.selected_columns
    assert orig_expt.col_details["h3"]["depindep"] is None

    # Assert the new one is versioned and has reconciled matrices
    new_expt = next(ed for ed in sm.expt_datas.values() if ed.id != expt.id)
    assert new_expt.name == "test_expt v2"
    assert "h3" in new_expt.selected_columns
    # Check that delta_to_spec was expanded from 2 to 3 rows
    assert new_expt.delta_to_spec.shape == (3, 3)

    # 7. Opening DataModelPanel for the new versioned data should not raise any IndexError
    sm.active_expt_data_id = new_expt.id
    panel = DataModelPanel(state_manager=sm)
    assert len(panel.specDeltaInps) == 3


@patch("bindmc.webgui.components.data_import.Graph")
@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_import.ui")
@patch("bindmc.webgui.components.data_model.ui")
def test_data_model_overwrite_with_dependents(mock_ui_model, mock_ui_import, mock_ui_selector, mock_graph):
    setup_mock_ui(mock_ui_model, mock_ui_import, mock_ui_selector)

    # 1. Setup a StateManager and a Model
    sm = StateManager(load_prior_state=False)
    model = Model(
        name="Test Model",
        component_names=["H", "G"],
        components=[Component(name="H"), Component(name="G")],
        species=["HG"]
    )
    sm.models[model.id] = model
    sm.active_model_id = model.id

    # Add default experimental data types
    sm._expt_dtypes["conc"] = ExptDataType(name="Conc.", init_meas="grav_vol", units="M")
    sm._expt_dtypes["delta h"] = ExptDataType(name="H (ppm)", init_meas="nmr_ppm", units="ppm")

    # 2. Setup RawData
    raw = RawData(
        filename="test_data.csv",
        data=pd.DataFrame({
            "htot": np.linspace(1.0, 1.0, 5),
            "h1": np.linspace(2.0, 2.0, 5),
            "h2": np.linspace(3.0, 3.0, 5),
            "h3": np.linspace(4.0, 4.0, 5),
            "ltot": np.linspace(5.0, 5.0, 5)
        })
    )
    sm.raw_datas[raw.id] = raw
    sm.active_raw_data_id = raw.id

    # 3. Setup ExptData
    expt = ExptData(name="test_expt", init_model=model, init_raw_data=raw)
    expt.selected_columns = ["htot", "h1", "h2", "h3", "ltot"]
    expt.col_details = {
        "htot": {"depindep": "indep", "dtype": "conc"},
        "h1": {"depindep": "dep", "dtype": "delta h"},
        "h2": {"depindep": "dep", "dtype": "delta h"},
        "h3": {"depindep": "dep", "dtype": "delta h"},
        "ltot": {"depindep": "indep", "dtype": "conc"}
    }
    expt.col_to_comp = np.array([
        [1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 1.0]
    ])
    expt._matrix_columns = list(expt.selected_columns)

    sm.add_expt_data(expt)

    # Add dependent dummy fit and mcmc
    fit = FitResult(
        model_id=model.id,
        expt_data_id=expt.id,
        name="Test Fit",
        description="",
        aic=0.0,
        bic=0.0,
        chisqr=0.0,
        termination_message="ok",
        init_model=model,
        init_expt_data=expt,
    )
    sm.add_fit(fit)

    mcmc = _new_mcmc(model, expt)
    mcmc.name = "Test MCMC"
    sm.add_mcmc(mcmc)

    assert len(sm.fits) == 1
    assert len(sm.mcmcs) == 1

    # 4. Instantiate DataImportPanel
    import_panel = DataImportPanel(sm)

    # 5. Deselect a column
    col_to_deselect = "h3"
    expt.col_details[col_to_deselect]["depindep"] = None
    expt.col_details[col_to_deselect]["dtype"] = None
    if col_to_deselect in expt.selected_columns:
        expt.selected_columns.remove(col_to_deselect)

    # 6. We expect a prompt, and if we select "Overwrite"
    # we call prepare_data_model_overwrite directly with delete_dependents=True.
    import_panel.prepare_data_model_overwrite(expt, delete_dependents=True)

    # Assert that no new ExptData was added to StateManager (len remains 1)
    assert len(sm.expt_datas) == 1

    # Assert the active expt is reconciled in-place
    active_expt = sm.active_expt_data
    assert "h3" not in active_expt.selected_columns
    assert active_expt.col_to_comp.shape == (2, 4)

    # Assert that the dependent fit and mcmc are deleted from StateManager
    assert len(sm.fits) == 0
    assert len(sm.mcmcs) == 0


@patch("bindmc.webgui.components.data_import.Graph")
@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_import.ui")
@patch("bindmc.webgui.components.data_model.ui")
def test_data_model_duplication(mock_ui_model, mock_ui_import, mock_ui_selector, mock_graph):
    setup_mock_ui(mock_ui_model, mock_ui_import, mock_ui_selector)

    # 1. Setup a StateManager and a Model
    sm = StateManager(load_prior_state=False)
    model = Model(
        name="Test Model",
        component_names=["H", "G"],
        components=[Component(name="H"), Component(name="G")],
        species=["HG"]
    )
    sm.models[model.id] = model
    sm.active_model_id = model.id

    # Add default experimental data types
    sm._expt_dtypes["conc"] = ExptDataType(name="Conc.", init_meas="grav_vol", units="M")
    sm._expt_dtypes["delta h"] = ExptDataType(name="H (ppm)", init_meas="nmr_ppm", units="ppm")

    # 2. Setup RawData
    raw = RawData(
        filename="test_data.csv",
        data=pd.DataFrame({
            "htot": np.linspace(1.0, 1.0, 5),
            "ltot": np.linspace(5.0, 5.0, 5),
            "h1": np.linspace(2.0, 2.0, 5)
        })
    )
    sm.raw_datas[raw.id] = raw
    sm.active_raw_data_id = raw.id

    # 3. Setup ExptData
    expt = ExptData(name="test_expt", init_model=model, init_raw_data=raw)
    expt.selected_columns = ["htot", "ltot", "h1"]
    expt.col_details = {
        "htot": {"depindep": "indep", "dtype": "conc"},
        "ltot": {"depindep": "indep", "dtype": "conc"},
        "h1": {"depindep": "dep", "dtype": "delta h"}
    }
    expt.col_to_comp = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0]
    ])
    expt._matrix_columns = list(expt.selected_columns)

    sm.add_expt_data(expt)

    # 4. Instantiate DataImportPanel
    import_panel = DataImportPanel(sm)

    # 5. Call duplicate configuration
    import_panel.selector.duplicate_active_expt()

    # Assert that a new ExptData was added to StateManager (len is 2)
    assert len(sm.expt_datas) == 2

    # Assert the new one is named versioned and is active
    new_expt = next(ed for ed in sm.expt_datas.values() if ed.id != expt.id)
    assert new_expt.name == "test_expt v2"
    assert sm.active_expt_data_id == new_expt.id


@pytest.mark.asyncio
@patch("bindmc.webgui.components.data_import.Graph")
@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_import.ui")
@patch("bindmc.webgui.components.data_model.ui")
async def test_data_model_rename(mock_ui_model, mock_ui_import, mock_ui_selector, mock_graph):
    setup_mock_ui(mock_ui_model, mock_ui_import, mock_ui_selector)

    # 1. Setup a StateManager and a Model
    sm = StateManager(load_prior_state=False)
    model = Model(
        name="Test Model",
        component_names=["H", "G"],
        components=[Component(name="H"), Component(name="G")],
        species=["HG"]
    )
    sm.models[model.id] = model
    sm.active_model_id = model.id

    # Add default experimental data types
    sm._expt_dtypes["conc"] = ExptDataType(name="Conc.", init_meas="grav_vol", units="M")
    sm._expt_dtypes["delta h"] = ExptDataType(name="H (ppm)", init_meas="nmr_ppm", units="ppm")

    # 2. Setup RawData
    raw = RawData(
        filename="test_data.csv",
        data=pd.DataFrame({
            "htot": [1.0],
            "ltot": [5.0],
            "h1": [2.0]
        })
    )
    sm.raw_datas[raw.id] = raw
    sm.active_raw_data_id = raw.id

    # 3. Setup ExptData
    expt = ExptData(name="test_expt", init_model=model, init_raw_data=raw)
    expt.selected_columns = ["htot", "ltot", "h1"]
    expt.col_details = {
        "htot": {"depindep": "indep", "dtype": "conc"},
        "ltot": {"depindep": "indep", "dtype": "conc"},
        "h1": {"depindep": "dep", "dtype": "delta h"}
    }
    expt.col_to_comp = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0]
    ])
    expt._matrix_columns = list(expt.selected_columns)

    sm.add_expt_data(expt)
    sm.save_to_storage = MagicMock()

    # 4. Instantiate DataImportPanel
    import_panel = DataImportPanel(sm)

    # 5. Mock dialog context manager to return a renamed string
    class AsyncMockDialog:
        def __init__(self, submit_value=None):
            self.submit_value = submit_value

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def __await__(self):
            async def _await_impl():
                return self.submit_value
            return _await_impl().__await__()

    mock_ui_selector.dialog.return_value = AsyncMockDialog("renamed_expt")

    # 6. Call rename_active_expt
    await import_panel.selector.rename_active_expt()

    # Assert name has changed
    assert expt.name == "renamed_expt"
