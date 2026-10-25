# Testing Guide

`bindmc` features an extensive test suite covering unit calculations, equation parsing, state management, and UI workflows.

---

## Running Tests

Execute tests using `pytest` within your development environment:

```bash
uv run pytest
```

---

## Test Categories

### 1. Unit & Solver Tests
- `tests/test_analytical_fast_exchange_backend.py`: Verifies analytical solvers against numerical Newton-Raphson solvers.
- `tests/test_model_setups.py`: Verifies equation parsing into stoichiometric matrices.
- `tests/test_notebook_export.py`: Tests generation of Jupyter `.ipynb` notebooks.

### 2. Fast UI Component Tests (`User` fixture)
- Uses `nicegui.testing.User` to simulate fast async user interactions without launching a real browser:
```bash
uv run pytest tests/test_sim_flow.py -v
```

### 3. End-to-End Browser Tests (`Screen` fixture)
- Uses `nicegui.testing.Screen` with Selenium to test full end-to-end browser workflows:
```bash
uv run pytest tests/test_simulation_workflow_screen.py -v
```

---

## UI Test Markers

When creating or modifying UI components, preserve element markers (`.mark("...")`) so automated test selectors find controls reliably. Example:

```python
ui.number("Initial Conc").mark("start-conc-1-val")
```
