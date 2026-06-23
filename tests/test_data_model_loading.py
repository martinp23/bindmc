import gzip
import json
import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from lmfit import Parameter as LMFitParameter

from bindmc.webgui.components.data_model import DataModelPanel
from bindmc.webgui.state import StateManager
from nicegui import app


def test_load_project_delta_to_spec():
    project_path = "bindtools_project_20260619-224157.json.gz"
    assert os.path.exists(project_path)

    with gzip.open(project_path, "rt", encoding="utf-8") as f:
        content = f.read()

    # Mock storage so StateManager load_prior_state loads it
    mock_storage = MagicMock()
    mock_storage.user = {"state-data": content}

    orig_storage = getattr(app, "storage", None)
    app.storage = mock_storage
    try:
        sm = StateManager(load_prior_state=True)
    finally:
        if orig_storage is not None:
            app.storage = orig_storage

    # Check that both experimental data loaded correctly
    assert len(sm.expt_datas) == 2

    # Get v2 experimental data
    expt_v2 = next(expt for expt in sm.expt_datas.values() if expt.name == "ethan1.xlsx v2")
    assert expt_v2.delta_to_spec is not None

    # Check shapes and types
    assert expt_v2.delta_to_spec.ndim == 2
    assert expt_v2.delta_to_spec.shape == (4, 4)
    assert isinstance(expt_v2.delta_to_spec[0, 0], LMFitParameter)
    assert expt_v2.delta_to_spec[0, 1] is None


@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_model.ui")
def test_data_model_panel_fast_exchange_reconstruction(mock_ui, mock_ui_selector):
    # Mock ui elements so that instantiating DataModelPanel doesn't crash on nicegui layout construction
    mock_element = MagicMock()
    for m in (mock_ui, mock_ui_selector):
        m.column.return_value = mock_element
        m.row.return_value = mock_element
        m.card.return_value = mock_element
        m.chip.return_value = mock_element
        m.label.return_value = mock_element
        m.button.return_value = mock_element
        m.element.return_value = mock_element
        m.dropdown_button.return_value = mock_element
    
    # We want input fields to store their value attribute
    def create_mock_input(*args, **kwargs):
        inp = MagicMock()
        inp.value = kwargs.get("value", "")
        # Mock bind_enabled_from to be a no-op
        inp.bind_enabled_from = MagicMock()
        # Mock on to be a no-op
        inp.on = MagicMock()
        return inp
    mock_ui.input.side_effect = create_mock_input
    
    mock_ui.checkbox.return_value = MagicMock(value=True)

    project_path = "bindtools_project_20260619-224157.json.gz"
    with gzip.open(project_path, "rt", encoding="utf-8") as f:
        content = f.read()

    mock_storage = MagicMock()
    mock_storage.user = {"state-data": content}

    orig_storage = getattr(app, "storage", None)
    app.storage = mock_storage
    try:
        sm = StateManager(load_prior_state=True)
    finally:
        if orig_storage is not None:
            app.storage = orig_storage

    # Set active expt to v2
    expt_v2 = next(expt for expt in sm.expt_datas.values() if expt.name == "ethan1.xlsx v2")
    sm.active_expt_data_id = expt_v2.id
    sm.active_model_id = expt_v2.model_id

    # Create the panel
    panel = DataModelPanel(state_manager=sm)

    # Verify that panel.specDeltaInps matches expected length (4 chemical shift columns)
    assert len(panel.specDeltaInps) == 4

    # Verify concentration expressions set on the input widgets
    expected_expression = "[H_free]+[HG_free]+[HG2_free]"
    assert panel.specDeltaInps[0].value == expected_expression
    assert panel.specDeltaInps[1].value == expected_expression
    assert panel.specDeltaInps[2].value == expected_expression
    assert panel.specDeltaInps[3].value == expected_expression


@patch("bindmc.webgui.components.dataset_selector.ui")
@patch("bindmc.webgui.components.data_model.ui")
def test_data_model_panel_clear_input_behavior(mock_ui, mock_ui_selector):
    mock_element = MagicMock()
    for m in (mock_ui, mock_ui_selector):
        m.column.return_value = mock_element
        m.row.return_value = mock_element
        m.card.return_value = mock_element
        m.chip.return_value = mock_element
        m.label.return_value = mock_element
        m.button.return_value = mock_element
        m.element.return_value = mock_element
        m.dropdown_button.return_value = mock_element

    # We want input fields to store their value attribute
    def create_mock_input(*args, **kwargs):
        inp = MagicMock()
        inp.value = kwargs.get("value", "")
        inp.bind_enabled_from = MagicMock()
        inp.on = MagicMock()
        return inp
    mock_ui.input.side_effect = create_mock_input

    mock_ui.checkbox.return_value = MagicMock(value=True)

    project_path = "bindtools_project_20260619-224157.json.gz"
    with gzip.open(project_path, "rt", encoding="utf-8") as f:
        content = f.read()

    mock_storage = MagicMock()
    mock_storage.user = {"state-data": content}

    orig_storage = getattr(app, "storage", None)
    app.storage = mock_storage
    try:
        sm = StateManager(load_prior_state=True)
    finally:
        if orig_storage is not None:
            app.storage = orig_storage

    # Set active expt to v2
    expt_v2 = next(expt for expt in sm.expt_datas.values() if expt.name == "ethan1.xlsx v2")
    sm.active_expt_data_id = expt_v2.id
    sm.active_model_id = expt_v2.model_id

    # Create the panel
    panel = DataModelPanel(state_manager=sm)

    # 1. Test clearing component concentration input and inserting a term
    comp_input = panel.compConcInps[0]
    panel.last_focus = comp_input
    comp_input.value = None

    panel.insert_term("[H]")
    assert comp_input.value == "[H]"

    # 2. Test clearing fast exchange input and inserting a species chip
    fast_input = panel.specDeltaInps[0]
    panel.last_focus = fast_input
    fast_input.value = None

    panel._insert_species_into_fast_inp("H_free")
    assert fast_input.value == "[H_free]"

    # 3. Test that clearing the fast exchange input clears fast_ex_chem_shift_map[idx]
    # Set to a non-zero expression first, causing widgets to be mapped
    fast_input.value = "[H_free]"
    panel._handle_spec_delta_blur(0, fast_input)
    assert "H_free" in panel.fast_ex_chem_shift_map[0]

    # Now clear the input
    fast_input.value = ""
    panel._handle_spec_delta_blur(0, fast_input)
    # Check that the map is cleared!
    assert len(panel.fast_ex_chem_shift_map[0]) == 0

    # 4. Test _insert_expression_into_fast_inp
    fast_input.value = None
    panel._insert_expression_into_fast_inp("[H_free]+[HG_free]", fast_input)
    assert fast_input.value == "[H_free]+[HG_free]"

    # If it already has a value, check that it appends with +
    panel._insert_expression_into_fast_inp("[HG2_free]", fast_input)
    assert fast_input.value == "[H_free]+[HG_free]+[HG2_free]"
