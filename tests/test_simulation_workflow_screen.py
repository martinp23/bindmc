import pytest
from nicegui.testing import Screen
from selenium.webdriver.common.keys import Keys
import time
import os
import glob
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore
import pandas as pd
from .testutils import CTRL_KEY

def test_simulation_workflow_screen(screen: Screen) -> None:
    # Open root
    screen.open("/")
    # Require Chrome for stable headless downloads
    caps = getattr(screen.selenium, "capabilities", {}) or {}
    browser_name = str(caps.get("browserName", "")).lower()
    if "chrome" not in browser_name:
        pytest.skip("Download verification requires Chrome driver")

    screen.selenium.set_window_size(1920, 1080)
    # Configure download path for headless Chrome using CDP
    download_dir = os.path.join(os.getcwd(), "tests", "downloads")
    os.makedirs(download_dir, exist_ok=True)
    try:
        screen.selenium.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": download_dir},
        )
    except Exception:
        pass
    # Basic presence check (header label)
    screen.find("BindMC GUI")

    # Wait for the page/Vue components to fully load 
    screen.wait(1.0)

    # Helper function to click tabs robustly
    def click_tab(label: str) -> None:
        tab = WebDriverWait(screen.selenium, 10).until(
            EC.element_to_be_clickable((By.XPATH, f"//div[contains(@class, 'q-tab__label') and text()='{label}']"))
        )
        screen.selenium.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
        tab.click()
        screen.wait(0.5)

    # Helper function to click buttons robustly
    def click_button(text: str) -> None:
        btn = WebDriverWait(screen.selenium, 10).until(
            EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{text}')]"))
        )
        screen.selenium.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        btn.click()

    # Navigate to Model Setup
    click_tab("Simulate")
    click_tab("Define model")
    screen.shot("simulation_model_setup", failed=False)
    # Enter equilibrium equations and parse (use marker for unique selection)
    click_button("Add New Model")
    name_input = WebDriverWait(screen.selenium, 10).until(
        lambda d: next(
            (
                el
                for el in d.find_elements(By.CSS_SELECTOR, 'input[placeholder="Enter model name"]')
                if el.is_displayed()
            ),
            False,
        )
    )
    name_input.click()
    name_input.send_keys(CTRL_KEY, "a")
    name_input.send_keys(Keys.BACKSPACE)
    name_input.send_keys("Test Model")
    click_button("Create")
    screen.shot("simulation_model_setup_1", failed=False)

    # screen.type((Keys.CONTROL, 'a'))

    el = screen.selenium.find_element(By.CSS_SELECTOR, '[aria-label="Equilibrium Equations"]')
    el.click()
    screen.type("H + G <=> HG")
    click_button("Parse Equations")

    try:
        screen.should_contain("H + G ⇋ HG" or "G + H ⇋ HG")
    except AssertionError:
        try:
            screen.should_contain("G + H ⇋ HG")
        except AssertionError:
            raise

    el = screen.selenium.find_element(By.CSS_SELECTOR, '[placeholder="Enter binding constant"]')
    el.click()
    screen.type("4")

    # Go to Data Generation tab
    click_tab("Data Generation")
    screen.should_contain("Data Generation Panel")

    # Set number of steps and component concentrations
    el = screen.selenium.find_element(By.CSS_SELECTOR, '[aria-label="Number of steps"]')
    el.send_keys(CTRL_KEY, "a")
    el.send_keys(Keys.BACKSPACE)
    el.click()
    screen.type("40")

    screen.should_contain_input("H")

    # Updated selector to match the actual input for "Component 1" name
    el = screen.selenium.find_element(
        By.XPATH, "//div[contains(text(), 'Component 1')]/following::input[@type='text' and @aria-label='Name'][1]"
    )
    el.click()

    # Re-locate the element just before interacting to avoid stale reference
    # el = screen.selenium.find_element(By.XPATH, "//input[contains(@value, 'H') or contains(@aria-label, 'H') or contains(@placeholder, 'H')]")
    # el.click()
    el.send_keys(Keys.TAB)
    screen.type(Keys.SPACE)  # activate fixed concentration checkbox
    screen.type(Keys.TAB)
    screen.type("5")  # conc

    screen.type(Keys.TAB)  # units
    screen.type(Keys.TAB)  # next component label (G)
    screen.type(Keys.TAB)  # checkbox
    screen.type(Keys.TAB)  # start conc
    screen.type("0")  # start conc value
    screen.type(Keys.TAB)  # units
    screen.type(Keys.TAB)  # end conc
    screen.type("20")  # end conc value

    click_button("Generate Component Concentrations")

    # Switch to Simulation tab and run
    click_tab("Simulation")

    click_button("Run Simulation")
    click_button("Use auto-generated name")
    # Expect success notification
    WebDriverWait(screen.selenium, 15).until(lambda d: "completed successfully" in d.page_source)

    # Wait for Plotly to render the simulation results graph title
    WebDriverWait(screen.selenium, 10).until(lambda d: "Simulation Results" in d.page_source)
    screen.should_contain("Test Model HG=4.0")
    screen.shot("simulation_results", failed=False)
    # Download the simulation data CSV
    click_button("Download Simulation Data")

    # Wait for the download and get the file path

    download_dir = os.path.join(os.getcwd(), "tests", "downloads")
    timeout_s = 10
    csv_file = None
    end_time = time.time() + timeout_s
    while time.time() < end_time:
        # Prefer finished .csv, otherwise check for .crdownload in progress
        files = glob.glob(os.path.join(download_dir, "simulation_*_data.csv"))
        if files:
            candidate = max(files, key=os.path.getctime)
            # ensure file is non-empty and stable across a short interval
            size1 = os.path.getsize(candidate)
            time.sleep(0.3)
            size2 = os.path.getsize(candidate)
            if size2 > 0 and size2 == size1:
                csv_file = candidate
                break
        time.sleep(0.2)
    assert csv_file is not None, "CSV file was not downloaded"

    ref_dir = os.path.join(os.getcwd(), "tests", "references")
    ref_csv = os.path.join(ref_dir, "sim_1to1_4.csv")
    
    df_downloaded = pd.read_csv(csv_file)
    df_reference = pd.read_csv(ref_csv)
    pd.testing.assert_frame_equal(df_downloaded, df_reference, rtol=1e-4, atol=1e-8)

    # Teardown: delete the downloaded CSV file
    if csv_file and os.path.exists(csv_file):
        os.remove(csv_file)

