from nicegui.testing import User
import pandas as pd
import numpy as np
from .testutils import setNumberVal
import pytest

pytest_plugins = ["nicegui.testing.user_plugin"]


async def test_component_concentration_generation(user: User) -> None:
    # Set up test data

    await user.open("/")
    await user.should_see("BindMC")
    user.find("Simulate").click()
    user.find("Define model").click()

    a = user.find("Equilibrium Equations").click()

    # Need to do it like this because we have two Equilibrium Equations elements. If we jsut use .type(str) then we
    # get two copies of the text.
    for i, e in enumerate(a.elements):
        if i == 0:
            e.clear()
            e.set_value("H + G <=> HG")  # type: ignore

    user.find("Parse Equations").click()

    user.find("Data Generation").click()
    await user.should_see("Data Generation Panel")

    await setNumberVal(user, "num-steps", 5)

    # Set component 1 as constant
    user.find("Component 1")
    # user.find('comp-name-1').clear().type('Calcium')
    user.find("constant-conc-1-checkbox").click()
    # user.find('start-conc-1-val').type('100')
    await setNumberVal(user, "start-conc-1-val", 100)
    # u = user.find('start-conc-1-val')
    # for element in u.elements:
    #     assert (isinstance(element, ui.number))
    #     element.value = 100

    user.find("start-conc-1-unit")  # nothing to do
    # Set component 2 as varying
    user.find("Component 2")
    # user.find('comp-name-2').clear().type('Magnesium')
    # comp2.find('Constant conc?').checkbox(False)
    await setNumberVal(user, "start-conc-2-val", 10)
    user.find("start-conc-2-unit")
    await setNumberVal(user, "end-conc-2-val", 50)
    user.find("end-conc-2-unit")

    # # Set component 3 as varying
    # user.find('Component 3')
    # user.find('comp-name-3').clear().type('Potassium')
    # #comp3.find('Constant conc?').checkbox(False)
    # setNumberVal(user,'start-conc-3-val',10)
    # user.find('start-conc-3-unit').click()
    # user.find('µM').click()  # Select 'µM' from the dropdown
    # setNumberVal(user,'end-conc-3-val',50)
    # user.find('end-conc-3-unit').click()
    # user.find('µM').click()  # Select 'µM' from the dropdown
    # After setting values, force a refresh

    # Trigger concentration calculation
    user.find("Generate Component Concentrations").click()

    # Verify results
    expected_concs = pd.DataFrame(
        {
            "H": [0.1] * 5,
            "G": np.linspace(10e-3, 50e-3, 5),
            #'Potassium': np.linspace(10e-6, 50e-6, 5)
        }
    )

    table = user.find("gen-data-table").elements.pop()

    # Compare against the expected DataFrame
    assert [c["name"] for c in table.columns] == list(expected_concs.columns)
    assert len(table.rows) == len(expected_concs)

    for i, row in enumerate(table.rows):
        for j, col in enumerate(expected_concs.columns):
            assert row[col] == pytest.approx(expected_concs.iloc[i, j])
