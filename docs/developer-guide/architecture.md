# Architecture Overview

`bindmc` is built as a state-decoupled web application utilizing NiceGUI for UI rendering and `bindtools` for numerical computations.

---

## High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph UI_Layer [NiceGUI UI Components]
        Header[BindToolsHeader]
        BindingModel[BindingModelPanel]
        DataImport[DataImportPanel]
        Fitting[FittingPanel]
        Bayes[BayesPanel]
        Simulation[SimulationPanel]
    end

    subgraph State_Layer [Central State Management]
        SM[StateManager]
        Bus[Pub/Sub Listener Bus]
        Storage[(nicegui.app.storage.user)]
    end

    subgraph Core_Engine [bindtools Calculation Core]
        NR[Numba Newton-Raphson Solver]
        LMFit[lmfit Optimizer]
        Emcee[emcee MCMC Sampler]
    end

    UI_Layer -->|Dispatch Events / Mutate State| SM
    SM -->|Persist JSON State| Storage
    SM -->|Notify Listeners| Bus
    Bus -->|Update Controls & Plots| UI_Layer
    SM -->|Off-Loop Execution via nicegui.run.cpu_bound| Core_Engine
    Core_Engine -->|Return Fit/MCMC Dataclasses| SM
```

---

## Reactive Event Lifecycle (UI Event Bus)

When a user interacts with a control in the UI (for example, modifying an equilibrium equation or running a fit):

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Panel as UI Component (BaseComponent)
    participant SM as StateManager
    participant Core as bindtools Engine
    participant Browser as Local Storage

    User->>Panel: Edits parameter / Clicks 'Run Fit'
    Panel->>SM: Mutate active Model / call run_fit()
    SM->>Browser: Save updated state-data JSON
    SM->>Core: await nicegui.run.cpu_bound(fitfun, ...)
    Core-->>SM: Returns FitResult dataclass
    SM->>SM: notify_listeners("fit_completed")
    SM->>Panel: Trigger registered callbacks
    Panel->>User: Re-render Plotly charts & results grid
```

---

## State Persistence & Deserialization

All application state is serialized to dictionary representations (`to_dict()`) and stored in `nicegui.app.storage.user["state-data"]`.

```mermaid
flowchart LR
    A[Browser Session / User Startup] --> B{state-data exists?}
    B -- Yes --> C[StateManager._load_prior_state]
    B -- No --> D[Load default models template JSON]
    C --> E[Reconstruct Dataclasses: Model, ExptData, FitResult, MCMCSim]
    D --> E
    E --> F[Set active_model_id & notify model_changed]
    F --> G[Render Workspace UI]
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
