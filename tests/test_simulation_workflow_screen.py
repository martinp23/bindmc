import pytest
from nicegui.testing import Screen
from selenium.webdriver.common.keys import Keys
import time
import os
import glob
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore
import filecmp

def test_simulation_workflow_screen(screen: Screen) -> None:
    # Open root
    screen.open('/')
    # Require Chrome for stable headless downloads
    caps = getattr(screen.selenium, 'capabilities', {}) or {}
    browser_name = str(caps.get('browserName', '')).lower()
    if 'chrome' not in browser_name:
        pytest.skip('Download verification requires Chrome driver')

    screen.selenium.set_window_size(1920, 1080)
    # Basic presence check (header label)
    screen.find('BindTools GUI')

    # Navigate to Model Setup
    screen.find('Simulate').click()
    screen.find('Define model').click()
    screen.shot('simulation_model_setup',failed=False)
    # Enter equilibrium equations and parse (use marker for unique selection)

    el = screen.selenium.find_element(By.CSS_SELECTOR, '[aria-label="Model Name"]')
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.BACKSPACE)
    el.click()
    screen.type('Test Model')
    screen.shot('simulation_model_setup_1',failed=False)

    #screen.type((Keys.CONTROL, 'a'))

    el = screen.selenium.find_element(By.CSS_SELECTOR, '[aria-label="Equilibrium Equations"]')
    el.click()
    screen.type('H + G <=> HG')    
    screen.find('Parse Equations').click()

    try:
        screen.should_contain('H + G ⇋ HG' or 'G + H ⇋ HG')
    except AssertionError:
        try:
            screen.should_contain('G + H ⇋ HG')
        except AssertionError:
            raise

        

    el = screen.selenium.find_element(By.CSS_SELECTOR, '[placeholder="Enter binding constant"]')
    el.click()
    screen.type('4')

    # Go to Data Generation tab
    screen.find('Data Generation').click()
    screen.should_contain('Data Generation Panel')

    # Set number of steps and component concentrations
    el = screen.selenium.find_element(By.CSS_SELECTOR, '[aria-label="Number of steps"]')
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.BACKSPACE)
    el.click()
    screen.type('40')    


    screen.should_contain_input('H')
    
    # Updated selector to match the actual input for "Component 1" name
    el = screen.selenium.find_element(
        By.XPATH,
        "//div[contains(text(), 'Component 1')]/following::input[@type='text' and @aria-label='Name'][1]"
    )
    el.click()

    # Re-locate the element just before interacting to avoid stale reference
   # el = screen.selenium.find_element(By.XPATH, "//input[contains(@value, 'H') or contains(@aria-label, 'H') or contains(@placeholder, 'H')]")
    #el.click()
    el.send_keys(Keys.TAB)
    screen.type(Keys.SPACE) # activate fixed concentration checkbox
    screen.type(Keys.TAB)
    screen.type('5') # conc

    screen.type(Keys.TAB)  # units
    screen.type(Keys.TAB)  # next component label (G)
    screen.type(Keys.TAB) # checkbox
    screen.type(Keys.TAB)  # start conc
    screen.type('0')  # start conc value
    screen.type(Keys.TAB)  # units
    screen.type(Keys.TAB)  # end conc
    screen.type('20')  # end conc value

    screen.find('Generate Component Concentrations').click()

    # Switch to Simulation tab and run
    simulation_tab = screen.selenium.find_element(By.XPATH, "//div[contains(@class, 'q-tab__label') and text()='Simulation']")
    screen.selenium.execute_script("arguments[0].scrollIntoView({block: 'center'});", simulation_tab)
    simulation_tab.click()

    
    screen.find('Run Simulation').click()
    screen.find("Use auto-generated name").click()
    # Expect success notification
    screen.should_contain('completed successfully')

    screen.should_contain('Simulation Results')
    screen.should_contain('Test Model HG=4.0')
    screen.shot('simulation_results',failed=False)
    # Download the simulation data CSV
    screen.find('Download Simulation Data').click()

    # Wait for the download and get the file path

    download_dir = os.path.join(os.getcwd(), 'tests', 'downloads')    
    timeout_s = 10
    csv_file = None
    end_time = time.time() + timeout_s
    while time.time() < end_time:
        # Prefer finished .csv, otherwise check for .crdownload in progress
        files = glob.glob(os.path.join(download_dir, 'simulation_*_data.csv'))
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
    assert csv_file is not None, 'CSV file was not downloaded'

    # # Compare to reference file
    ref_dir = os.path.join(os.getcwd(), 'tests', 'references')   
    ref_csv = os.path.join(ref_dir, 'sim_1to1_4.csv')
    assert filecmp.cmp(csv_file, ref_csv, shallow=False), "Downloaded CSV does not match reference"

    # Teardown: delete the downloaded CSV file
    if csv_file and os.path.exists(csv_file):
        os.remove(csv_file)