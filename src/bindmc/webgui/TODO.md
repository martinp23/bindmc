# BindTools WebGUI Release Checklist

Use this as the source of truth for shipping readiness.

Legend:
- `Priority`: `P0` (must ship), `P1` (should ship), `P2` (hardening)
- `Effort`: `S`, `M`, `L`
- `Owner`: set to initials or role (`@unassigned` until assigned)

## P0 - Must Ship

- [ ] Streamline analytical methods in bindtools package binding.py

- Check obs_list is right in tests/elsewhere, and/or check "uvvis" vs "absorbance" dtype
- Add timing trial done/starting real run popups
- Dark species do not appear in fit and mcmc any mroe - check obslist change!
- [ ] Fix fit graph mismatch when only subset of dependent variables are fitted.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/fitting.py`, `webgui/components/graph.py`

- [X] Make active object handling robust after delete/change (model, data, fit, sim).
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/state/statemanager.py`

- [ ] Implement explicit expt data load/select/delete workflow in UI.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/data_import.py`, `webgui/components/body.py`, `webgui/state/statemanager.py`

- [ ] Add strict validation + actionable inline errors for data-model mapping (col->comp, integ->spec, fast-exchange).
  - Owner: `@unassigned`
  - Effort: `L`
  - Files: `webgui/components/data_model.py`, `webgui/classes/ExptData.py`

- [X] Sanitize chemical-shift parameter names (spaces/special chars) before lmfit parameter creation.
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: `webgui/classes/ExptData.py`

- [ ] Apply consistent long-task UI state handling (disable/re-enable buttons + spinner + no double-submit).
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/simulation.py`, `webgui/components/fitting.py`, `webgui/components/data_import.py`

- [ ] Add destructive action confirmations and unsaved-change protection.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/header.py`, `webgui/state/statemanager.py`, relevant panel files

- [X] Fix disabled-tab guidance so reason is always visible and correct.
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: `webgui/components/body.py`

## P1 - Should Ship

- [ ] UI polish pass (spacing, naming consistency, remove placeholder text, responsive fit/focus).
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/*.py`

- [ ] Add raw-data quick plot/preview during import to validate selected columns.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/data_import.py`, `webgui/components/graph.py`

- [ ] Complete graph export UX (PNG options/resolution, fit/sim parity, clear labels).
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: `webgui/components/fitting.py`, `webgui/components/simulation.py`

- [ ] Persist graph view preferences (x-axis, ratio, legend visibility) across reload.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/graph.py`, `webgui/state/statemanager.py`

- [ ] Replace broad `except Exception` with specific exceptions + targeted user notifications.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: multiple `webgui/components/*.py`, `webgui/state/statemanager.py`

- [ ] Replace remaining `print` calls with structured logging.
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: multiple `webgui/**/*.py`

- [ ] Improve first-run empty states and inline guidance for main workflows.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/body.py`, panel files

## P2 - Hardening

- [ ] Add end-to-end test for fit workflow including CSV/PNG export.
  - Owner: `@unassigned`
  - Effort: `L`
  - Files: `tests/`

- [ ] Add regression tests for cascade deletion and active-ID reassignment.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `tests/`, `webgui/state/statemanager.py`

- [ ] Add serialization round-trip tests for fast-exchange (`delta_to_spec`, `limiting_shifts`).
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `tests/`, `webgui/classes/ExptData.py`

- [ ] Create packaging smoke-test checklist (platform launch, downloads, save/open, project import/export).
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: `docs/` (new release checklist doc)

- [ ] Add release process doc (version bump, changelog, sign-off criteria).
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: `docs/` (new release process doc)

## Post-Ship Backlog

- [ ] Complete MCMC analysis workflow.
  - Owner: `@unassigned`
  - Effort: `L`

- [X] Add analytical-mode simulation support for simple 1:1/1:2/2:1 fast-exchange systems.
  - Owner: `@unassigned`
  - Effort: `M`
  - Note: Until this ships, point users to supramolecular.org for these simulations.

- [ ] Add graph log-scale options and richer plot controls.
  - Owner: `@unassigned`
  - Effort: `M`

- [ ] Improve model comments/metadata editing UX.
  - Owner: `@unassigned`
  - Effort: `S`

## Legacy Notes (Untriaged)

Carried forward from the previous TODO for reference:

- Enable choosing of graph elements:
  - What should be y-axis? Plot all species ideally
- allow comments alongside equilibria
- graphs - y/x log options
- fast exchange work
- add refresh-bindings as in model tab to other tabs
- precompile numba (part done)

## Sprint-Ready Breakdown (Top 3 P0)

### A) Fix fit graph mismatch for partially fitted dependent variables

- [ ] A1. Reproduce and lock down failing scenario with test data containing multiple dependent columns where only a subset is fitted.
  - Owner: `@unassigned`
  - Effort: `S`

- [ ] A2. Ensure graph plotting uses only columns present in `fit.calc_obs` and aligned index lengths.
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: `webgui/components/fitting.py`, `webgui/components/graph.py`

- [ ] A3. Add guardrail notifications when expected columns are missing, without crashing render.
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: `webgui/components/fitting.py`

- [ ] A4. Add regression test for fit graph rendering with partial dependent-variable fitting.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `tests/`

Acceptance criteria:
- Fit results tab renders both experimental markers and calculated lines with no exceptions when only subset of dependent variables is fitted.
- No mismatch warnings/errors appear for valid partial-fit cases.
- Regression test fails on old behavior and passes on fix.

### B) Make active-object handling robust after delete/change (model/data/fit/sim)

- [ ] B1. Audit all delete/change paths to identify where active IDs may become stale.
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: `webgui/state/statemanager.py`, `webgui/components/*.py`

- [ ] B2. Implement centralized helper(s) in `StateManager` to set safe fallback active IDs after deletion.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/state/statemanager.py`

- [ ] B3. Replace scattered manual active-ID patching in components with calls to the centralized helper.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/simulation.py`, `webgui/components/fitting.py`, others as needed

- [ ] B4. Add tests for cascade delete and active object reassignment across model/data/fit/sim.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `tests/`, `webgui/state/statemanager.py`

Acceptance criteria:
- After any delete/change action, all active IDs are either valid existing IDs or `None`.
- UI header and relevant panels refresh without exceptions after deletions.
- Cascade deletion behavior is deterministic and covered by tests.

### C) Implement explicit expt data load/select/delete workflow

- [ ] C1. Add expt-data selector UI with active-item indicator and load action.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/data_import.py`

- [ ] C2. Add expt-data delete action with confirmation dialog and post-delete fallback selection logic.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `webgui/components/data_import.py`, `webgui/state/statemanager.py`

- [ ] C3. Emit and consume consistent `expt_data_changed` notifications so dependent panels refresh correctly.
  - Owner: `@unassigned`
  - Effort: `S`
  - Files: `webgui/state/statemanager.py`, `webgui/components/body.py`, `webgui/components/header.py`, `webgui/components/data_model.py`, `webgui/components/fitting.py`

- [ ] C4. Add tests for selecting, loading, deleting multiple expt datasets and preserving app stability.
  - Owner: `@unassigned`
  - Effort: `M`
  - Files: `tests/`

Acceptance criteria:
- User can select among multiple expt datasets, and active dataset is clearly shown.
- Deleting active expt dataset selects a valid fallback (or `None`) without stale references.
- Data Model and Fit panels always reflect the currently active expt dataset.
