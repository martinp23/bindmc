# Architecture Overview

`bindmc` is built as a state-decoupled web application utilizing NiceGUI for UI rendering and `bindtools` for numerical computations.

```
+-------------------------------------------------------------------+
|                        NiceGUI UI Components                      |
| (Header, BindingModel, DataImport, Fitting, Bayes, Simulation)    |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                           StateManager                            |
|             (Dict Storage + Pub/Sub Listener Bus)                 |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                         bindtools Engine                          |
|    (Numba Newton–Raphson, lmfit Minimization, emcee MCMC)         |
+-------------------------------------------------------------------+
```

---

## Directory Organization

```
bindmc/
├── src/bindmc/                  # Application code
│   ├── main.py                  # Entry point (NiceGUI runner / PyInstaller wrapper)
│   └── webgui/
│       ├── app.py               # BindToolsServer & page routing
│       ├── classes/             # Dataclass domain objects (Model, ExptData, FitResult)
│       ├── components/          # NiceGUI UI panel implementations
│       ├── state/
│       │   └── statemanager.py  # Central state bus
│       └── utils.py             # Equation parsing & matrix conversion helpers
├── bindtools/                   # Calculation engine package (submodule)
│   └── src/bindtools/
│       └── binding.py           # Numba speciation, lmfit fitting, emcee MCMC
├── tests/                       # Unit, UI, and integration tests
├── pyproject.toml               # Package configuration & dependencies
└── mkdocs.yml                   # Documentation configuration
```

---

## State Management Architecture

- `StateManager` (`statemanager.py`) maintains dictionaries of domain objects (`models`, `expt_datas`, `fits`, `simulations`).
- All state updates trigger notifications to registered listeners (`self.sm.notify_listeners("event_name")`).
- Heavy computations (e.g. non-linear fitting or MCMC sampling) are run off the main event loop using `await nicegui.run.cpu_bound(...)` to maintain UI responsiveness.
