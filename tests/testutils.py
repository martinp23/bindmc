from nicegui import ui
import asyncio
from selenium.webdriver.common.keys import Keys
import sys

CTRL_KEY = Keys.COMMAND if sys.platform == "darwin" else Keys.CONTROL



# This function sets a numeric value in the NiceGUI UI and ensures the value change is processed correctly - especially important for elements that
# have data bindings
async def setNumberVal(user, marker, numberVal):
    u = user.find(marker)
    for element in u.elements:
        assert isinstance(element, ui.number)
        element.value = numberVal
        if hasattr(element, "_handle_value_change"):
            element._handle_value_change(numberVal)
        await asyncio.sleep(0.05)
        # Verify the value was set
        assert element.value == numberVal
