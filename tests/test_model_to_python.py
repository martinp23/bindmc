from webgui.state import StateManager
from webgui.classes import *
import numpy as np
import pytest

# pytest_plugins = ['nicegui.testing.user_plugin']


async def test_dump_sim_1to1() -> None:
    # Import a state with a simple 1-to-1 binding model
    state_manager = StateManager(load_prior_state=False)
    with open('tests/test_data/1to1_test', 'r') as f:
        json_str = f.read()
    state_manager.from_json(json_str)

    outstr = state_manager.dump_simulation_to_python(state_manager.active_model)
    print(outstr)

    
    
    # Assert the result matches the expected output
   # assert np.array_equal(result, expected_result)