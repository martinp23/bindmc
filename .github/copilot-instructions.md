# Copilot instructions for `binding-ms`

## Big picture (where to start)
- This repo is a **NiceGUI native app** that wraps a scientific binding/simulation engine.
- App entrypoint: `main.py` (constructs `webgui.app.BindToolsServer`, then `ui.run(..., native=True, ...)`).
- UI layer: `webgui/` (tabs/panels + persistence + tests).
- Computation core: `bindtools/binding.py` (Newton–Raphson equilibrium solver with `numba`, plus fitting/MCMC helpers).

## Architecture + data flow
- `webgui/app.py:BindToolsServer` registers the `/` page and instantiates the UI (`BindToolsHeader`, `Body`).
- `webgui/state/statemanager.py:StateManager` is the single source of truth:
  - Holds `models`, `simulations`, `fits`, `expt_datas`, etc. keyed by UUID.
  - Persists state into `nicegui.app.storage.user["state-data"]` and restores on startup.
  - Uses an **event/listener bus** (`add_listener`/`notify_listeners`) to keep panels in sync.
- Domain objects are dataclasses in `webgui/classes/` (e.g., `Model`, `Simulation`, `ExptData`). They typically:
  - Store UUIDs as `uuid.UUID` (accept strings on load).
  - Serialize via `to_dict()`; DataFrames are serialized via `.to_dict(...)`.
- Equilibrium equations entered by the user are parsed/validated in `webgui/utils.py` (e.g., `eq_mat_from_equation_str_infer_components`).

## UI conventions (important for tests)
- UI “panels” live in `webgui/components/` and usually subclass `BaseComponent`:
  - Implement `setup_nicegui()` to build controls.
  - Implement `setup_bindings()` to register listeners (`self.sm.add_listener(...)`).
- Keep **test markers stable**: controls are discovered in tests via `.mark("...")`.
  - Examples: `webgui/components/data_gen.py` marks `num-steps`, `gen-data-table`, `start-conc-1-val`.
  - Example: `webgui/components/binding_model.py` marks `eq-input`, `logK-<species>-val`.
- When doing heavy computation from UI, run it off the event loop:
  - Pattern: `await nicegui.run.cpu_bound(...)` (see `webgui/components/simulation.py`).

## Listener/event names
- Prefer notifying the central state manager rather than wiring components directly.
- Event names are effectively part of the API; see `LISTENERS.md`.
  - Common ones: `model_changed`, `model_parsed`, `comp_concs_updated`, `simulation_completed`, `fit_completed`.

## Developer workflows
- Run the app (local/dev): `python main.py` (or VS Code task “Run main.py”).
  - Note: `README.md` currently mentions `python webgui/server.py`, but that file does not exist; `main.py` is the real entrypoint.
- Tests: **always run via** `conda run -n binding_gui pytest <paths> -v` (the active shell is the `base` env which lacks `nicegui`; invoking `pytest` directly will fail with `ModuleNotFoundError`).
  - UI tests use `nicegui.testing`:
    - Fast async UI tests use the `User` fixture (e.g., `tests/test_sim_flow.py`).
    - End-to-end browser tests use the `Screen` fixture + Selenium; download checks require **Chrome** (see `tests/test_simulation_workflow_screen.py`).
  - Numeric input helpers: `tests/testutils.py:setNumberVal` calls NiceGUI internal value handlers—if you replace `ui.number` with a different widget, update tests accordingly.

## Dependencies / environment
- Conda environment is described in `environment.yaml` (Python >= 3.12; `nicegui[plotly]`, `numba`, `lmfit`, `emcee`, etc.).
- Pip constraints exist in `requirements.in`.
- Formatting/linting uses Ruff (`pyproject.toml`): line length 120.

## Packaging notes
- There are PyInstaller/NiceGUI packaging hints in `main.py` and `Your App Name.spec`. If changing imports, keep an eye on “hidden import” style requirements (e.g., the matplotlib SVG backend import in `main.py`).
