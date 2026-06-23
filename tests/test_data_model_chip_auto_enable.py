from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd

from bindmc.webgui.classes import ExptData, Model, RawData, ExptDataType, Component
from bindmc.webgui.state import StateManager
from bindmc.webgui.components.data_model import DataModelPanel

def setup_mock_ui(mock_ui_model, mock_ui_selector):
    # Mock NiceGUI UI elements to prevent startup crash
    mock_element = MagicMock()
    for mock_ui in (mock_ui_model, mock_ui_selector):
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
            inp.classes = MagicMock(return_value=inp)
            inp.props = MagicMock(return_value=inp)
            inp.on_value_change = MagicMock(return_value=inp)
            return inp
        mock_ui.input.side_effect = create_mock_input

        def create_mock_checkbox(*args, **kwargs):
            cb = MagicMock()
            cb.value = kwargs.get("value", False)
            cb.on_value_change = MagicMock()
            return cb
        mock_ui.checkbox.side_effect = create_mock_checkbox


@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_model.ui")
def test_data_model_chip_auto_enable(mock_ui_model, mock_ui_selector):
    setup_mock_ui(mock_ui_model, mock_ui_selector)

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
    sm._expt_dtypes["integ"] = ExptDataType(name="Integration", init_meas="nmr_integ", units="au")

    # 2. Setup RawData
    raw = RawData(
        filename="test_data.csv",
        data=pd.DataFrame({
            "htot": np.linspace(1.0, 1.0, 5),
            "h1": np.linspace(2.0, 2.0, 5),
            "h2": np.linspace(3.0, 3.0, 5),
            "ltot": np.linspace(5.0, 5.0, 5)
        })
    )
    sm.raw_datas[raw.id] = raw
    sm.active_raw_data_id = raw.id

    # 3. Setup ExptData with slow exchange (nmr_integ) and fast exchange (nmr_ppm) columns
    expt = ExptData(name="test_expt", init_model=model, init_raw_data=raw)
    expt.selected_columns = ["htot", "h1", "h2", "ltot"]
    expt.col_details = {
        "htot": {"depindep": "indep", "dtype": "conc"},
        "h1": {"depindep": "dep", "dtype": "delta h"},   # fast exchange
        "h2": {"depindep": "dep", "dtype": "integ"},     # slow exchange
        "ltot": {"depindep": "indep", "dtype": "conc"}
    }
    expt.col_to_comp = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0]
    ])
    expt._matrix_columns = list(expt.selected_columns)

    sm.add_expt_data(expt)

    # 4. Instantiate DataModelPanel
    panel = DataModelPanel(state_manager=sm)

    # Assert widgets are generated
    assert len(panel.specDeltaInps) == 1  # 1 fast exchange: h1
    assert "HG" in panel.spec_integ_inps  # 1 slow exchange: HG

    # Verify initial enabled checkbox state
    panel.specDeltaCbs[0].value = False
    panel.spec_integ_cbs["HG"].value = False

    # Simulate user clicking a chip that targets the fast exchange input (e.g. inserting into panel.specDeltaInps[0])
    panel.set_focus(panel.specDeltaInps[0])
    panel.insert_term("[htot]")

    # Check if checkbox was automatically ticked/enabled
    assert panel.specDeltaCbs[0].value is True

    # Simulate user clicking a chip that targets the slow exchange input (panel.spec_integ_inps["HG"])
    panel.set_focus(panel.spec_integ_inps["HG"])
    panel.insert_term("[htot]")

    # Check if checkbox was automatically ticked/enabled
    assert panel.spec_integ_cbs["HG"].value is True

    # Test the species/expression specific helper insertions
    # 1. _insert_species_into_fast_inp
    panel.specDeltaCbs[0].value = False
    panel._insert_species_into_fast_inp("HG_free", widget=panel.specDeltaInps[0])
    assert panel.specDeltaCbs[0].value is True

    # 2. _insert_expression_into_fast_inp
    panel.specDeltaCbs[0].value = False
    panel._insert_expression_into_fast_inp("HG_free", widget=panel.specDeltaInps[0])
    assert panel.specDeltaCbs[0].value is True
