# State Management API Reference

`StateManager` is the central source of truth and event bus for the `bindmc` web application.

---

::: bindmc.webgui.state.statemanager.StateManager
    options:
      show_root_heading: true

---

## Central Event / Listener Names

Components subscribe to updates by registering listeners via `sm.add_listener(event_name, callback)`:

| Listener Event Name | Description | Triggered When |
|---|---|---|
| `model_changed` | Active model selection or properties changed | Switching models or updating name |
| `model_parsed` | Equilibrium equations parsed into matrix | User edits reaction equations |
| `comp_concs_updated` | Component concentrations grid updated | User inputs titration points |
| `data_imported` | File uploaded into Data Import | New CSV/Excel file loaded |
| `fit_completed` | Non-linear fit finished | User clicks Run Fit |
| `simulation_completed` | MCMC sampling finished | MCMC sampler finishes |
