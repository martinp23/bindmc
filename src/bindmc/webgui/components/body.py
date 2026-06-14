from .base import BaseComponent
from nicegui import ui
import numpy as np
import pandas as pd
from . import (
    BayesPanel,
    BindingModelPanel,
    BindToolsHeader,
    DataGenerationPanel,
    DataImportPanel,
    DataModelPanel,
    FittingPanel,
    SimulationPanel,
)
from typing import Any

TabKey = tuple[str, ...]


def _append_reason(reason_map: dict[TabKey, list[str]], tab_key: TabKey, reason: str) -> None:
    if tab_key not in reason_map:
        reason_map[tab_key] = []
    if reason not in reason_map[tab_key]:
        reason_map[tab_key].append(reason)


def _compute_tab_disable_reasons(sm) -> dict[TabKey, list[str]]:
    """Return deterministic disable reasons for each tab key."""
    reasons: dict[TabKey, list[str]] = {}

    active_model = getattr(sm, "active_model", None)
    model_is_valid = True
    if active_model is None:
        model_is_valid = False
    else:
        eq_str = getattr(active_model, "eq_str", None)
        binding_constants = getattr(active_model, "binding_constants", []) or []
        missing_logk = any(getattr(k, "logK", None) is None for k in binding_constants)
        model_is_valid = bool(eq_str is not None and str(eq_str).strip()) and not missing_logk

    if not model_is_valid:
        msg = "Model is incomplete. Define/parse equations and set all binding constants."
        _append_reason(reasons, ("Simulate", "Data Generation"), msg)
        _append_reason(reasons, ("Simulate", "Simulation"), msg)
        _append_reason(reasons, ("Fit", "Data model"), msg)
        _append_reason(reasons, ("Fit", "MCMC"), msg)

    comp_concs = getattr(active_model, "component_concs", None) if active_model is not None else None
    has_comp_concs = isinstance(comp_concs, pd.DataFrame) and not comp_concs.empty
    if not has_comp_concs:
        _append_reason(
            reasons,
            ("Simulate", "Simulation"),
            "Generate component concentrations first (Simulate > Data Generation).",
        )

    active_expt = getattr(sm, "active_expt_data_or_none", None)
    has_expt_data = (
        active_expt is not None
        and getattr(active_expt, "data", None) is not None
        and not active_expt.data.empty
    )
    if not has_expt_data:
        msg = "Import/select experimental data first (Fit > Import data)."
        _append_reason(reasons, ("Fit", "Fit results"), msg)
        _append_reason(reasons, ("Fit", "Data model"), msg)
        _append_reason(reasons, ("Fit", "MCMC"), msg)

    has_raw_for_expt = False
    if has_expt_data:
        raw_obj = getattr(active_expt, "raw_data", None)
        raw_df = getattr(raw_obj, "data", None) if raw_obj is not None else None
        has_raw_for_expt = raw_df is not None and not raw_df.empty
    if not has_raw_for_expt:
        _append_reason(
            reasons,
            ("Fit", "Data model"),
            "Active dataset has no raw data backing it.",
        )

    if has_expt_data:
        integ_to_spec = getattr(active_expt, "integ_to_spec", None)
        limiting_shifts = getattr(active_expt, "limiting_shifts", None)
        is_analytical_fast_ex = bool(getattr(active_expt, "is_analytical_fast_ex", False))
        has_linear_obs = False
        has_linear_obs_fn = getattr(active_expt, "has_linear_obs", None)
        if callable(has_linear_obs_fn):
            expt_dtypes = getattr(sm, "_expt_dtypes", {})
            has_linear_obs = bool(has_linear_obs_fn(expt_dtypes))
        has_integ_mapping = isinstance(integ_to_spec, np.ndarray) and integ_to_spec.size > 0
        has_shift_mapping = isinstance(limiting_shifts, dict) and len(limiting_shifts) > 0
        has_data_model = has_integ_mapping or has_shift_mapping or is_analytical_fast_ex or has_linear_obs
        if not has_data_model:
            msg = "Configure a data model first (Fit > Data model)."
            _append_reason(reasons, ("Fit", "Fit results"), msg)
            _append_reason(reasons, ("Fit", "MCMC"), msg)

    if getattr(sm, "active_fit_id", None) is None:
        _append_reason(reasons, ("Fit", "MCMC"), "Run a fit first (Fit > Results).")

    return reasons


def _format_disable_tooltip(reasons: list[str]) -> str:
    if not reasons:
        return ""
    if len(reasons) == 1:
        return reasons[0]
    return "\n\n".join([f"- {reason}" for reason in reasons])


class Body(BaseComponent):
    
    def setup_nicegui(self):
        self.tabs = {}
        self.components = {}
        self._tab_tooltip_elements: dict[TabKey, Any] = {}
        self._tab_help_cues: dict[TabKey, Any] = {}
        self._generate_body()
        self.enable_disable_tabs()

    def setup_bindings(self):
        super().setup_bindings()
    
        self.sm.add_listener("data_imported", self.enable_disable_tabs)
        self.sm.add_listener("model_changed", self.enable_disable_tabs)
        self.sm.add_listener("model_parsed", self.enable_disable_tabs)
        self.sm.add_listener("comp_concs_updated", self.enable_disable_tabs)
        self.sm.add_listener("k_changed", self.enable_disable_tabs)
        self.sm.add_listener("data_model_processed", self.enable_disable_tabs)
        self.sm.add_listener("fit_completed", self.enable_disable_tabs)
        self.sm.add_listener("active_context_changed", self.enable_disable_tabs)

    def _generate_body(self):
        """Generate the body of the application."""
        with ui.row().classes("w-full flex-grow p-4"):
            with ui.tabs().classes("w-full").on(
                "update:model-value", self.sm.save_to_storage
            ) as tabs_main:
                self.tabs[('Simulate',)]=ui.tab("Simulate", icon="insights")
                self.tabs[('Fit',)]=ui.tab("Fit", icon="model_training")

            with ui.tab_panels(tabs_main).classes("w-full"):
                with ui.tab_panel("Simulate"):
                    with ui.tabs().classes("w-full").on(
                        "update:model-value", self.sim_tab_changed) as sim_tabs:
                        # self.tabs[('Simulate','Model Setup')]=ui.tab("Model Setup", icon="science")
                        self.tabs[('Simulate','Binding model setup')]=ui.tab(
                            "Binding model setup", label="Define model", icon="settings"
                        )
                        self.tabs[('Simulate','Data Generation')]=ui.tab("Data Generation", icon="add")
                        self.tabs[('Simulate','Simulation')]=ui.tab("Simulation", icon="insights")

                    with ui.tab_panels(sim_tabs).classes("w-full"):
                        with ui.tab_panel("Binding model setup"):
                            self.components["model_setup"] = BindingModelPanel(
                                self.sm, mode="sim"
                            )

                        with ui.tab_panel("Data Generation"):
                            self.components["data_generation"] = DataGenerationPanel(
                                self.sm
                            )

                        with ui.tab_panel("Simulation"):
                            self.components["simulation"] = SimulationPanel(
                                self.sm
                            )

                with ui.tab_panel("Fit"):
                    with ui.tabs().classes("w-full").on(
                        "update:model-value", self.fit_tab_changed
                    ) as fit_tabs:
                        self.tabs[('Fit','Binding model setup')]=ui.tab(
                            "Binding model setup", label="Define model", icon="settings"
                        )
                        self.tabs[('Fit','Data import')]=ui.tab("Data import", label="Import data", icon="file_upload")
                        self.tabs[('Fit','Data model')]=ui.tab(
                            "Data model setup", label="Data model", icon="data_usage"
                        )
                        self.tabs[('Fit','Fit results')]=ui.tab("Fit results", label="Results", icon="check_circle")
                        self.tabs[('Fit','MCMC')]=ui.tab("MCMC", label="MCMC analysis", icon="calculate")

                    with ui.tab_panels(fit_tabs).classes("w-full"):
                        with ui.tab_panel("Binding model setup"):
                            self.components["fit_binding_model"] = BindingModelPanel(
                                self.sm, mode="fit"
                            )

                        with ui.tab_panel("Data import"):
                            self.components["data_import"] = DataImportPanel(
                                self.sm
                            )

                        with ui.tab_panel("Data model setup"):
                            self.components["data_model"] = DataModelPanel(
                                self.sm
                            )

                        with ui.tab_panel("Fit results"):
                            self.components["fit_results"] = FittingPanel(
                                self.sm
                            )

                        with ui.tab_panel("MCMC"):
                            self.components["mcmc"] = BayesPanel(
                                self.sm
                            )

    def sim_tab_changed(self, e):
        if e.args == 'Simulation':
            # Ensure the simulation graph is updated when switching to the Simulation tab
            self.components["simulation"].graph.update_graph()
        self.sm.save_to_storage()

    def fit_tab_changed(self, e):
        if e.args == 'Data model setup':
            # Ensure the data model is updated when switching to the Data model setup tab
            self.components["data_model"]._populate_blocks()
        if e.args == 'Fit Results':
            pass
            # Ensure the fit results graph is updated when switching to the Fit Results tab
            # self.components["fit_results"].graph.update_graph_x()
            # self.components["fit_results"].graph.graph.update()
        self.sm.save_to_storage()

    def enable_disable_tabs(self,e=None):
        """Enable or disable tabs based on the current state."""
        reason_map = _compute_tab_disable_reasons(self.sm)
        tabs_to_disable = set(reason_map.keys())
        tabs_to_enable = [x for x in self.tabs.keys() if x not in tabs_to_disable]
        self.disable_tabs(reason_map)
        self.enable_tabs(tabs_to_enable)

    def _clear_tab_guidance(self, tab_key: TabKey) -> None:
        tooltip = self._tab_tooltip_elements.pop(tab_key, None)
        cue = self._tab_help_cues.pop(tab_key, None)
        if tooltip is not None:
            tooltip.delete()
        if cue is not None:
            cue.delete()

    def disable_tabs(self, tab_reasons: dict[TabKey, list[str]]) -> None:
        for k, reason_list in tab_reasons.items():
            if k in self.tabs:
                self.tabs[k].disable()
                self._clear_tab_guidance(k)
                # Ensure we can absolutely-position the help cue over the tab icon.
                self.tabs[k].classes("relative overflow-visible")
                with self.tabs[k]:
                    cue = (
                        ui.icon("help_outline")
                        .classes("text-black-7")
                        .style(
                            "position:absolute;"
                            "left:calc(50% + 15px);"
                            "top:15px;"
                            "transform:translate(-50%, -50%);"
                            "font-size:12px;"
                            "z-index:2;"
                            "pointer-events:none;"
                        )
                    )
                    tooltip = ui.tooltip(_format_disable_tooltip(reason_list)).style('white-space: pre-wrap')
                self._tab_help_cues[k] = cue
                self._tab_tooltip_elements[k] = tooltip
            else:
                print(f"Tab {k} not found in tabs dictionary.")
    
    def enable_tabs(self, tab_keys: list[TabKey]) -> None:
        for k in tab_keys:
            if k in self.tabs:
                self.tabs[k].enable()
                self._clear_tab_guidance(k)
            else:
                print(f"Tab {k} not found in tabs dictionary.")
