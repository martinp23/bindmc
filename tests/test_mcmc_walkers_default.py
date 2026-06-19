from unittest.mock import MagicMock, patch
import pytest
from bindmc.webgui.state import StateManager


def _load_state_1to1() -> StateManager:
    sm = StateManager(load_prior_state=False)
    with open("tests/test_data/1to1_test") as f:
        json_str = f.read()
    sm.from_json(json_str)
    return sm


@patch("bindmc.webgui.components.bayes.ui")
def test_bayes_panel_get_ndim_and_defaults(mock_ui):
    # Setup mocks for number inputs
    mock_nwalkers_input = MagicMock()

    # Configure mock_ui to return mock elements
    mock_number_el = MagicMock()
    mock_number_el.classes.return_value = mock_number_el
    mock_ui.number.return_value = mock_number_el

    # Mock ui elements
    mock_ui.column.return_value = MagicMock()
    mock_ui.card.return_value = MagicMock()
    mock_ui.row.return_value = MagicMock()
    mock_ui.grid.return_value = MagicMock()
    mock_ui.tabs.return_value = MagicMock()
    mock_ui.tab_panels.return_value = MagicMock()
    mock_ui.tab_panel.return_value = MagicMock()
    mock_ui.matplotlib.return_value = MagicMock()

    from bindmc.webgui.components.bayes import BayesPanel

    sm = _load_state_1to1()
    panel = BayesPanel(sm)

    # Override nwalkers_input with a distinct mock for assertions
    panel.nwalkers_input = mock_nwalkers_input

    # 1. Test get_ndim
    ndim = panel.get_ndim()

    active_fit = sm.active_fit
    varying_params = sum(
        1 for p in active_fit.params.values() if isinstance(p, dict) and p.get("vary") is True
    )

    unique_dtypes = set()
    for col, details in sm.active_expt_data.col_details.items():
        if details.get("depindep") == "dep":
            dtype_key = details.get("dtype")
            if dtype_key is not None:
                edt = sm._expt_dtypes.get(dtype_key)
                if edt is not None:
                    unique_dtypes.add(edt.meas)

    expected_ndim = varying_params + len(unique_dtypes)
    assert ndim == expected_ndim
    assert ndim > 0

    # 2. Test update_default_walkers
    panel.update_default_walkers()
    mock_nwalkers_input.set_value.assert_called_with(2 * ndim)
    assert mock_nwalkers_input.min == 2 * ndim


@pytest.mark.anyio
@patch("bindmc.webgui.components.bayes.ui")
async def test_run_analysis_validation_blocks(mock_ui):
    mock_nwalkers_input = MagicMock()
    mock_nwalkers_input.value = 2  # artificially low walker count

    mock_number_el = MagicMock()
    mock_number_el.classes.return_value = mock_number_el
    mock_ui.number.return_value = mock_number_el

    mock_ui.column.return_value = MagicMock()
    mock_ui.card.return_value = MagicMock()
    mock_ui.row.return_value = MagicMock()
    mock_ui.grid.return_value = MagicMock()
    mock_ui.tabs.return_value = MagicMock()
    mock_ui.tab_panels.return_value = MagicMock()
    mock_ui.tab_panel.return_value = MagicMock()
    mock_ui.matplotlib.return_value = MagicMock()

    from bindmc.webgui.components.bayes import BayesPanel

    sm = _load_state_1to1()
    panel = BayesPanel(sm)
    panel.nwalkers_input = mock_nwalkers_input

    panel.nsteps_input = MagicMock()
    panel.nsteps_input.value = 1000

    # Call run_analysis
    await panel.run_analysis()

    # It should have blocked and notified
    mock_ui.notify.assert_called_once()
    args, kwargs = mock_ui.notify.call_args
    assert "You need at least" in args[0]
    assert "parameters" in args[0]
    assert kwargs.get("type") == "warning"
