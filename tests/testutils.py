from nicegui import ui
import asyncio
import sys



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


def open_screen(screen, path: str = "/") -> None:
    import time
    from selenium.common.exceptions import TimeoutException

    # Give uvicorn/NiceGUI server a moment to bind and settle on Windows
    if sys.platform == "win32":
        time.sleep(0.5)

    for attempt in range(3):
        try:
            screen.open(path)
            return
        except TimeoutException:
            if attempt == 2:
                raise
            time.sleep(1.0)

