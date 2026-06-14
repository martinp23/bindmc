from nicegui import ui
from nicegui.testing import User
import pandas as pd
import numpy as np
from .testutils import setNumberVal
import pytest

pytest_plugins = ['nicegui.testing.user_plugin']


async def test_1to1_sim(user: User) -> None:
    # Set up test data
    
    await user.open('/')
    await user.should_see('BindTools')
    user.find('Simulate').click()
    user.find('Define model').click()

    a=user.find('Equilibrium Equations').click()

    # Need to do it like this because we have two Equilibrium Equations elements. If we jsut use .type(str) then we
    # get two copies of the text.
    for i,e in enumerate(a.elements):
        if i == 0:
            e.clear()
            e.set_value('H + G <=> HG') # type: ignore
    
    user.find('Parse Equations').click()
    user.find('Data Generation').click()
    await user.should_see('Data Generation Panel')
    await setNumberVal(user,'num-steps',20)
        # Set component 1 as constant
    user.find('Component 1')
    assert list(user.find('comp-name-1').elements)[0].value == 'H'
    assert list(user.find('comp-name-2').elements)[0].value == 'G'
    #user.find('comp-name-1').clear().type('Calcium')
    user.find('constant-conc-1-checkbox').click()
    #user.find('start-conc-1-val').type('100')
    await setNumberVal(user,'start-conc-1-val',5)

    user.find('start-conc-1-unit') # nothing to do
    # Set component 2 as varying
    user.find('Component 2')
    await setNumberVal(user,'start-conc-2-val',10)
    user.find('start-conc-2-unit')
    await setNumberVal(user,'end-conc-2-val',50)
    user.find('end-conc-2-unit')
    user.find('Generate Component Concentrations').click()

    # Check that the component concentrations are generated correctly
    table = user.find("gen-data-table").elements.pop()
    assert len(table.rows) == 20

    user.find(content='Simulation',kind=ui.tab).click()
    await user.should_see(target='Simulation',kind=ui.tab_panel)

    user.find('Run Simulation').click()
    
    
