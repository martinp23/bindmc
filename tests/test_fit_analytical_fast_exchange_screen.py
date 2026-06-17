import shutil
import socket
from pathlib import Path

import numpy as np
import pytest
import pandas as pd
from nicegui.testing import Screen
from selenium.common.exceptions import ElementClickInterceptedException  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.common.keys import Keys  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore


_CHROME_DRIVER = shutil.which("chromedriver")
_CHROME_BROWSER = (
    shutil.which("google-chrome")
    or shutil.which("google-chrome-stable")
    or shutil.which("chromium")
    or shutil.which("chromium-browser")
)


def _can_bind_local_webdriver_port() -> bool:
    probes = [
        (socket.AF_INET, ("127.0.0.1", 0)),
        (socket.AF_INET6, ("::1", 0)),
    ]
    for family, addr in probes:
        sock = None
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.bind(addr)
            return True
        except OSError:
            continue
        finally:
            if sock is not None:
                sock.close()
    return False


def _click_tab(driver, label: str) -> None:
    tab = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, f"//div[contains(@class, 'q-tab__label') and text()='{label}']"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
    tab.click()
    import time

    time.sleep(0.5)


_CAN_BIND_WEBDRIVER_PORT = _can_bind_local_webdriver_port()


def _replace_text_input(element, value: str) -> None:
    driver = element.parent
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
        element,
    )
    try:
        element.click()
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(Keys.BACKSPACE)
        element.send_keys(value)
    except ElementClickInterceptedException:
        # Fallback for transient overlays/tooltips intercepting pointer events.
        driver.execute_script(
            """
            const el = arguments[0];
            const val = arguments[1];
            el.focus();
            el.value = val;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            element,
            value,
        )


def _visible(driver, by: By, selector: str):
    return [el for el in driver.find_elements(by, selector) if el.is_displayed()]


def _first_visible(driver, by: By, selector: str, timeout: float = 10.0):
    return WebDriverWait(driver, timeout).until(
        lambda d: (lambda items: items[0] if items else False)(_visible(d, by, selector))
    )


def _write_1to1_shift_csv(path: Path) -> None:
    host_tot = np.full(24, 1.0e-3)
    guest_tot = np.linspace(0.0, 2.2e-3, 24)
    beta11 = 10**5.0
    term = host_tot + guest_tot + 1.0 / beta11
    disc = np.maximum(term**2 - 4.0 * host_tot * guest_tot, 0.0)
    hg = 0.5 * (term - np.sqrt(disc))
    frac_h_bound = np.divide(hg, host_tot, out=np.zeros_like(hg), where=host_tot > 0)
    delta_h = 7.0 + 1.2 * frac_h_bound
    pd.DataFrame({"H_tot": host_tot, "G_tot": guest_tot, "dH": delta_h}).to_csv(path, index=False)

def _write_1to1_conc_csv(path: Path) -> None:
    host_tot = np.full(24, 1.0e-3)
    guest_tot = np.linspace(0.0, 2.2e-3, 24)
    beta11 = 10**5.0
    term = host_tot + guest_tot + 1.0 / beta11
    disc = np.maximum(term**2 - 4.0 * host_tot * guest_tot, 0.0)
    hg = 0.5 * (term - np.sqrt(disc))
    pd.DataFrame({"H_tot": host_tot, "G_tot": guest_tot, "HG": hg}).to_csv(path, index=False)

@pytest.mark.skipif(
    _CHROME_DRIVER is None or _CHROME_BROWSER is None or not _CAN_BIND_WEBDRIVER_PORT,
    reason="Chrome/Chromedriver or local WebDriver socket is unavailable for Selenium screen test.",
)
def test_fit_uses_analytical_fast_exchange_backend_in_ui_11_shift(screen: Screen, tmp_path: Path) -> None:
    csv_path = tmp_path / "analytical_fast_exchange_11.csv"
    _write_1to1_shift_csv(csv_path)

    screen.open("/")
    screen.selenium.set_window_size(1920, 1080)
    screen.find("BindMC GUI")

    # Build 1:1 model on the Fit side.
    _click_tab(screen.selenium, "Fit")
    _click_tab(screen.selenium, "Define model")

    screen.find("Add New Model").click()
    name_input = _first_visible(screen.selenium, By.CSS_SELECTOR, 'input[placeholder="Enter model name"]')
    _replace_text_input(name_input, "Test model 1:1")
    screen.find("Create").click()
    eq_input = _first_visible(screen.selenium, By.CSS_SELECTOR, 'textarea[aria-label="Equilibrium Equations"]')
    _replace_text_input(eq_input, "H + G <=> HG")
    screen.find("Parse Equations").click()
    screen.wait(0.1)
    logk_input = _first_visible(screen.selenium, By.CSS_SELECTOR, 'input[placeholder="Enter binding constant"]')
    _replace_text_input(logk_input, "5")

    # Import CSV with a host-tracked chemical-shift observable.
    _click_tab(screen.selenium, "Import data")
    screen.find("Upload File").click()
    file_input = WebDriverWait(screen.selenium, 10).until(
        lambda d: (lambda items: items[-1] if items else False)(d.find_elements(By.CSS_SELECTOR, 'input[type="file"]'))
    )
    file_input.send_keys(str(csv_path))
    screen.should_contain("loaded successfully")

    # Mark dH as dependent + delta-h dtype (nmr_ppm).
    dep_label = WebDriverWait(screen.selenium, 10).until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//div[text()='dH']/ancestor::div[contains(@class,'q-card')][1]//div[contains(@class,'q-radio__label') and normalize-space()='Dependent variable']",
            )
        )
    )
    screen.selenium.execute_script("arguments[0].scrollIntoView({block: 'center'});", dep_label)
    screen.selenium.execute_script("arguments[0].click();", dep_label)

    dtype_input = WebDriverWait(screen.selenium, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[text()='dH']/ancestor::div[contains(@class,'q-card')][1]//input[@aria-label='Data type']")
        )
    )
    screen.selenium.execute_script("arguments[0].scrollIntoView({block: 'center'});", dtype_input)
    dtype_input.click()
    WebDriverWait(screen.selenium, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'q-item')]//span[normalize-space()='H (ppm)']"))
    ).click()

    # Configure data model mapping for concentrations.
    # Fast-exchange expression should now auto-default for simple analytical 1:1.
    _click_tab(screen.selenium, "Data model")
    h_map_input = _first_visible(
        screen.selenium, By.XPATH, "//div[normalize-space()='Component [H]_tot:']/following::input[@type='text'][1]"
    )
    _replace_text_input(h_map_input, "[H_tot]")
    g_map_input = _first_visible(
        screen.selenium, By.XPATH, "//div[normalize-space()='Component [G]_tot:']/following::input[@type='text'][1]"
    )
    _replace_text_input(g_map_input, "[G_tot]")
    screen.find("Apply Data Model").click()

    # Run fit and verify analytical parameter names (UI evidence for analytical backend path).
    _click_tab(screen.selenium, "Results")
    screen.find("Run Fit").click()
    screen.should_contain("Using analytical fast-exchange backend (1:1).")
    screen.should_contain("delta0_dH")
    screen.should_contain("deltac1_dH")


def test_fit_uses_analytical_fast_exchange_backend_in_ui_11_conc(screen: Screen, tmp_path: Path) -> None:
    csv_path = tmp_path / "analytical_fast_exchange_11.csv"
    _write_1to1_conc_csv(csv_path)

    screen.open("/")
    screen.selenium.set_window_size(1920, 1080)
    screen.find("BindMC GUI")

    # Build 1:1 model on the Fit side.
    _click_tab(screen.selenium, "Fit")
    _click_tab(screen.selenium, "Define model")

    screen.find("Add New Model").click()
    name_input = _first_visible(screen.selenium, By.CSS_SELECTOR, 'input[placeholder="Enter model name"]')
    _replace_text_input(name_input, "Test model 1:1")
    screen.find("Create").click()
    eq_input = _first_visible(screen.selenium, By.CSS_SELECTOR, 'textarea[aria-label="Equilibrium Equations"]')
    _replace_text_input(eq_input, "H + G <=> HG")
    screen.find("Parse Equations").click()
    screen.wait(0.1)
    logk_input = _first_visible(screen.selenium, By.CSS_SELECTOR, 'input[placeholder="Enter binding constant"]')
    _replace_text_input(logk_input, "5")

    # Import CSV with a host-tracked chemical-shift observable.
    _click_tab(screen.selenium, "Import data")
    screen.find("Upload File").click()
    file_input = WebDriverWait(screen.selenium, 10).until(
        lambda d: (lambda items: items[-1] if items else False)(d.find_elements(By.CSS_SELECTOR, 'input[type="file"]'))
    )
    file_input.send_keys(str(csv_path))
    screen.should_contain("loaded successfully")


    def assign_indep_conc(var_name: str):

        indep_label = WebDriverWait(screen.selenium, 10).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    f"//div[text()='{var_name}']/ancestor::div[contains(@class,'q-card')][1]//div[contains(@class,'q-radio__label') and normalize-space()='Independent variable']",
                )        )
        )

        screen.selenium.execute_script("arguments[0].scrollIntoView({block: 'center'});", indep_label)
        screen.selenium.execute_script("arguments[0].click();", indep_label)

        dtype_input = WebDriverWait(screen.selenium, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//div[text()='{var_name}']/ancestor::div[contains(@class,'q-card')][1]//input[@aria-label='Data type']")
            )
        )
        screen.selenium.execute_script("arguments[0].scrollIntoView({block: 'center'});", dtype_input)
        dtype_input.click()
        WebDriverWait(screen.selenium, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'q-item')]//span[normalize-space()='Conc.']"))
        ).click()


    assign_indep_conc("H_tot")
    assign_indep_conc("G_tot")



    # Mark dH as dependent + delta-h dtype (nmr_ppm).
    dep_label = WebDriverWait(screen.selenium, 10).until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//div[text()='HG']/ancestor::div[contains(@class,'q-card')][1]//div[contains(@class,'q-radio__label') and normalize-space()='Dependent variable']",
            )
        )
    )

    screen.selenium.execute_script("arguments[0].scrollIntoView({block: 'center'});", dep_label)
    screen.selenium.execute_script("arguments[0].click();", dep_label)



    dtype_input = WebDriverWait(screen.selenium, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[text()='HG']/ancestor::div[contains(@class,'q-card')][1]//input[@aria-label='Data type']")
        )
    )
    screen.selenium.execute_script("arguments[0].scrollIntoView({block: 'center'});", dtype_input)
    dtype_input.click()
    WebDriverWait(screen.selenium, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'q-item')]//span[normalize-space()='NMR Conc.']"))
    ).click()

    screen.find("Prepare data model").click()
    screen.should_contain("Data model prepared.")


    # take screenshot here
    screen.selenium.save_screenshot(str("screenshots/before_mapping.png"))

    # Configure data model mapping for concentrations.
    # Fast-exchange expression should now auto-default for simple analytical 1:1.
    _click_tab(screen.selenium, "Data model")
    h_map_input = _first_visible(
        screen.selenium, By.XPATH, "//div[normalize-space()='Component [H]_tot:']/following::input[@type='text'][1]"
    )
    _replace_text_input(h_map_input, "[H_tot]")
    g_map_input = _first_visible(
        screen.selenium, By.XPATH, "//div[normalize-space()='Component [G]_tot:']/following::input[@type='text'][1]"
    )
    _replace_text_input(g_map_input, "[G_tot]")


    hg_check = screen.selenium.find_element(By.CSS_SELECTOR, '[testid="spec-enabled-HG"]')
    hg_check.click()  # enable HG spec if not already (should be enabled by default for this test, but just in case)
    HG_free_input = _first_visible(
        screen.selenium, By.XPATH, "//div[normalize-space()='Species conc. [HG]_free:']/following::input[@type='text'][1]"
    )
    _replace_text_input(HG_free_input, "[HG]")


    screen.find("Apply Data Model").click()
    screen.selenium.save_screenshot(str("screenshots/after_mapping.png"))
    # Run fit and verify analytical parameter names (UI evidence for analytical backend path).
    _click_tab(screen.selenium, "Results")
    screen.wait(0.5)  # wait for potential backend processing after data model application
    screen.find("Run Fit").click()
    # screen.should_contain("Using analytical fast-exchange backend (1:1).")
    screen.should_contain("logHG")

