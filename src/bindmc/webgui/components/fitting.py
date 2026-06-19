import io
import json
import uuid
import re
import zipfile
import numpy as np
import pandas as pd
from nicegui import ui, run, events

import bindtools.binding as bd

from .base import BaseComponent
from .graph import Graph
from ..classes import FitResult
from ..utils import safe_filename, _infer_simple_fast_exchange_topology, custom_download
from functools import partial
from typing import cast

import logging

logger = logging.getLogger(__name__)


def _mapped_dependent_columns_for_fit(fit: FitResult) -> set[str]:
    """Infer which dependent columns are actually mapped for fitting."""
    expt = fit.expt_data
    dep_cols = {col for col in expt.columns if expt.col_details.get(col, {}).get("depindep") == "dep"}
    mapped_cols: set[str] = set()

    integ_to_spec = expt.integ_to_spec
    if isinstance(integ_to_spec, np.ndarray) and integ_to_spec.ndim == 2 and integ_to_spec.size > 0:
        max_cols = min(integ_to_spec.shape[1], len(expt.columns))
        for idx in range(max_cols):
            col_name = expt.columns[idx]
            if col_name not in dep_cols:
                continue
            values = pd.to_numeric(pd.Series(integ_to_spec[:, idx]), errors="coerce").to_numpy(dtype=float)
            finite_values = values[np.isfinite(values)]
            if finite_values.size == 0:
                continue
            if np.any(~np.isclose(finite_values, 0.0)):
                mapped_cols.add(col_name)

    for _, col_name in expt.limiting_shifts.keys():
        if col_name in dep_cols:
            mapped_cols.add(col_name)

    return mapped_cols


def _prepare_fit_plot_frames(fit: FitResult) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    """Return aligned (x, calc, expt) frames and list of skipped calc columns."""
    x_df = fit.comp_concs.copy().reset_index(drop=True)
    calc_df = fit.calc_obs.copy().reset_index(drop=True)
    # Use full experimental data, not selected_data, to avoid coupling to mutable UI state.
    # This ensures each fit's plot is based on its own calc_obs, not on the current state of expt_data.
    expt_df = fit.expt_data.data.copy().reset_index(drop=True)

    # Start with columns that exist in both calc and expt.
    # calc_df.columns is the source of truth for what was actually computed by the fit.
    common_cols = [col for col in calc_df.columns if col in expt_df.columns]

    # Remove columns with all NaN values
    common_cols = [col for col in common_cols if not calc_df[col].isna().all()]
    skipped_cols = [col for col in calc_df.columns if col not in common_cols]

    if not common_cols:
        return x_df.iloc[0:0], calc_df.iloc[:, 0:0], expt_df.iloc[:, 0:0], skipped_cols

    calc_plot = calc_df[common_cols]
    expt_plot = expt_df[common_cols]
    n_rows = min(len(x_df), len(calc_plot), len(expt_plot))

    return (
        x_df.iloc[:n_rows].reset_index(drop=True),
        calc_plot.iloc[:n_rows].reset_index(drop=True),
        expt_plot.iloc[:n_rows].reset_index(drop=True),
        skipped_cols,
    )


def _infer_analytical_fast_exchange_config(model, expt_data, expt_dtypes: dict) -> dict[str, object] | None:
    import warnings
    warnings.warn(
        "_infer_analytical_fast_exchange_config is deprecated. Topology detection has been relocated to bindtools.bindingModel.prepModel().",
        DeprecationWarning,
        stacklevel=2,
    )
    if model is None or expt_data is None:
        return None

    obs_list = [
        col_name
        for col_name in expt_data.sorted_data.columns
        if expt_data.col_details.get(col_name, {}).get("depindep") == "dep"
    ]
    if not obs_list:
        return None

    topology = _infer_simple_fast_exchange_topology(model.eq_mat, len(model.component_names))
    if topology is None:
        return None
    topo_name, complex_indices = topology

    # Classify each dependent column as NMR-shift or linear (UV-vis/fluorescence).
    has_nmr = False
    has_linear = False
    for col in obs_list:
        col_meta = expt_data.col_details.get(col, {})
        dtype_key = col_meta.get("dtype")
        dtype = expt_dtypes.get(dtype_key) if dtype_key is not None else None
        meas = getattr(dtype, "meas", None) if dtype is not None else None
        if meas == "nmr_ppm":
            has_nmr = True
        elif meas in ("uvvis", "fluorescence"):
            has_linear = True
        else: 
            return None  # Unknown or unsupported observable type for analytical path

    if has_nmr and has_linear:
        return None  # Mixed NMR + UV-vis not yet supported on analytical path

    # Pure linear (UV-vis / fluorescence) path: no NMR shift columns needed.
    if has_linear and not has_nmr:
        # If slow-exchange mapping is active, stay on generic backend.
        integ_to_spec = expt_data.integ_to_spec
        if isinstance(integ_to_spec, np.ndarray) and integ_to_spec.size > 0:
            numeric = pd.to_numeric(pd.Series(integ_to_spec.flatten()), errors="coerce").to_numpy(dtype=float)
            finite = numeric[np.isfinite(numeric)]
            if finite.size > 0 and np.any(~np.isclose(finite, 0.0)):
                return None
        return {
            "topology": topo_name,
            "complex_indices": complex_indices,
            "obs_columns": [],  # no NMR shift columns
            "obs_components": [],
        }

    # Pure NMR shift path (existing behaviour).

    # If slow-exchange mapping is active, stay on the generic backend.
    integ_to_spec = expt_data.integ_to_spec
    if isinstance(integ_to_spec, np.ndarray) and integ_to_spec.size > 0:
        numeric = pd.to_numeric(pd.Series(integ_to_spec.flatten()), errors="coerce").to_numpy(dtype=float)
        finite = numeric[np.isfinite(numeric)]
        if finite.size > 0 and np.any(~np.isclose(finite, 0.0)):
            return None

    component_free_labels = [f"{name}_free" for name in model.component_names]
    if len(component_free_labels) != 2:
        return None

    # Build optional hints from existing user mappings when available.
    shift_species_by_col: dict[str, set[str]] = {}
    if isinstance(expt_data.limiting_shifts, dict):
        for (species, col_name), _ in expt_data.limiting_shifts.items():
            if col_name is None:
                continue
            shift_species_by_col.setdefault(str(col_name), set()).add(str(species))

    delta_species_hints: dict[str, set[str]] = {}
    delta_to_spec = expt_data.delta_to_spec
    if isinstance(delta_to_spec, np.ndarray) and delta_to_spec.ndim == 2 and delta_to_spec.size > 0:
        # In this UI flow, delta_to_spec rows are created from fast-exchange observable columns.
        # For analytical mode all dependent observables are shift observables, so the row order
        # corresponds to obs_list.
        n_rows = min(delta_to_spec.shape[0], len(obs_list))
        n_species = min(delta_to_spec.shape[1], len(component_free_labels))
        for ridx in range(n_rows):
            col_name = obs_list[ridx]
            for sidx in range(n_species):
                try:
                    is_nonzero = not np.isclose(float(delta_to_spec[ridx, sidx]), 0.0)
                except Exception:
                    is_nonzero = bool(delta_to_spec[ridx, sidx])
                if is_nonzero:
                    delta_species_hints.setdefault(col_name, set()).add(component_free_labels[sidx])

    def _component_from_text_hints(col_name: str, dtype_key: str | None) -> int | None:
        # Tokenize to avoid over-matching short component names in arbitrary strings.
        tokens = []
        for src in (col_name, dtype_key or ""):
            parts = [t for t in re.split(r"[^A-Za-z0-9]+", str(src).lower()) if t]
            tokens.extend(parts)
        matches = [idx for idx, comp in enumerate(model.component_names) if str(comp).lower() in tokens]
        return matches[0] if len(matches) == 1 else None

    obs_components: list[int] = []
    unresolved: list[tuple[int, str]] = []
    for obs_idx, col in enumerate(obs_list):
        col_meta = expt_data.col_details.get(col, {})
        dtype_key = col_meta.get("dtype")

        included_species = set()
        included_species |= shift_species_by_col.get(col, set())
        included_species |= delta_species_hints.get(col, set())

        has_comp0 = component_free_labels[0] in included_species
        has_comp1 = component_free_labels[1] in included_species
        if has_comp0 != has_comp1:
            obs_components.append(0 if has_comp0 else 1)
            continue

        inferred = _component_from_text_hints(col, dtype_key)
        if inferred is not None:
            obs_components.append(inferred)
            continue

        unresolved.append((obs_idx, col))
        obs_components.append(-1)

    # Final fallback keeps analytical mode enabled even without manual shift metadata.
    if unresolved:
        for obs_idx, col in unresolved:
            fallback = obs_idx % len(component_free_labels)
            obs_components[obs_idx] = fallback
            logger.info(
                "Analytical fast-exchange: inferred observable '%s' as component %d by default fallback.",
                col,
                fallback,
            )

    return {
        "topology": topo_name,
        "complex_indices": complex_indices,
        "obs_columns": list(obs_list),
        "obs_components": obs_components,
    }


class FittingPanel(BaseComponent):
    def setup_nicegui(self) -> None:
        self._dark_species_visible = False  # must be set before bind_visibility_from
        self.container = ui.column().classes("w-full")

        with self.container:
            ui.label("Fitting panel").classes("text-lg font-bold mb-4")
            with ui.row().classes("w-full gap-4 items-start flex-col lg:flex-row"):
                with ui.card().classes("w-full lg:w-80 shrink-0"):
                    ui.label("Fitting options to go here.")
                    self.fit_alg_select = ui.select(
                        ["least_squares", "l-bfgs", "ampgo"],
                        label="Algorithm",
                        on_change=lambda e: print(f"Selected: {e.value}"),
                        value="least_squares",
                    ).classes("w-full")

                self.fit_results_card = FitResultsCard(state_manager=self.sm)

            with ui.row().classes("w-full mb-4"):
                self.fit_button = ui.button("Run Fit", on_click=self.run_fit)
                self.clear_fit_graph_button = ui.button("Clear Graph", on_click=self.clear_fit_graphs).classes("mb-4")
                self.download_fit_data_button = ui.button(
                    "Download Fit CSV", on_click=self.download_fit_data_csv
                ).classes("mb-4")
                self.export_fit_notebook_button = ui.button(
                    "Export to Notebook",
                    on_click=self.download_fit_notebook,
                ).classes("mb-4")
                self.delete_fit_dropdown = ui.dropdown_button("Delete Fit", auto_close=True).classes("mb-4")
                self.delete_fit_dropdown.clear()
                with self.delete_fit_dropdown:
                    for fit in self.sm.fits.values():
                        ui.item(
                            fit.name,
                            on_click=lambda e, fit=fit: self.delete_fit(fit),
                        )

            # Add name and comment inputs with save button
            with ui.card().classes("w-full mb-4"):
                ui.label("Fit Details")
                with ui.row().classes("w-full"):
                    self.fit_name_input = ui.input("Fit Name", placeholder="Enter fit name").classes("flex-1")
                    self.fit_comment_input = ui.input("Comment", placeholder="Enter comment").classes("flex-1")
                    ui.button(
                        "Auto-generate title",
                        on_click=lambda: self.fit_name_input.set_value(self.sm.active_model.name + " fit"),
                    ).classes("ml-4")
                    self.save_fit_details_button = ui.button(
                        "Save changes to name/comment", on_click=self.save_fit_details
                    ).classes("ml-4")
                    self.save_fit_details_button.set_enabled(False)

            with ui.row().classes("w-full"):
                with ui.column().classes("w-3/4"):
                    self.fit_graph = Graph(self.sm, mode="fit")
                    self.spinner = ui.spinner(size="xl").classes("absolute-center")
                    self.speciation_graph = Graph(self.sm, mode="fit_speciation")

            self.spinner.visible = False

            with ui.card().classes("w-full mb-4").bind_visibility_from(self, "_dark_species_visible"):
                ui.label("Dark / Silent Species").classes("text-base font-semibold mb-1")
                ui.label("Tick species whose ε / fluorescence amplitude is zero for each observable column.").classes(
                    "text-xs text-gray-500 mb-2"
                )
                self.dark_species_rows = ui.column().classes("w-full gap-1")

        self._rebuild_dark_species_card()
        self.graphs = [self.fit_graph, self.speciation_graph]

    def setup_bindings(self) -> None:
        super().setup_bindings()
        self.sm.add_listener("fit_results_updated", self._update_fit_graphs)
        self.sm.add_listener("fits_loaded", self._init_load_fits)
        self.sm.add_listener("active_context_changed", self._update_fit_graphs)
        self.sm.add_listener("fit_changed", self._refresh_for_active_fit)
        self.sm.add_listener("active_context_changed", self._rebuild_dark_species_card)
        self.sm.add_listener("data_model_processed", self._rebuild_dark_species_card)

        if len(self.sm.fits) > 0:
            self.fit_name_input.set_value(self.sm.active_fit.name)
            self.fit_comment_input.set_value(self.sm.active_fit.description)
            self.save_fit_details_button.set_enabled(True)

    def _refresh_for_active_fit(self, e=None) -> None:
        """Refresh fit name/comment inputs to reflect the current active fit."""
        active_fit = self.sm.active_fit_or_none
        if active_fit is None:
            self.fit_name_input.set_value("")
            self.fit_comment_input.set_value("")
            self.save_fit_details_button.set_enabled(False)
        else:
            self.fit_name_input.set_value(active_fit.name)
            self.fit_comment_input.set_value(active_fit.description)
            self.save_fit_details_button.set_enabled(True)

    def _set_fit_running(self, running: bool) -> None:
        """Toggle fitting UI state so teardown is consistent across all exit paths."""
        self.spinner.visible = running
        if running:
            self.fit_button.disable()
        else:
            self.fit_button.enable()

    def _rebuild_dark_species_card(self, *args) -> None:
        """Rebuild the dark-species toggle rows based on the active dataset."""
        expt_data = self.sm.active_expt_data_or_none
        if expt_data is None or not expt_data.has_linear_obs(self.sm._expt_dtypes):
            self._dark_species_visible = False
            return

        species = list(self.sm.species)
        lin_cols = expt_data.linear_obs_cols(self.sm._expt_dtypes)
        self._dark_species_visible = bool(lin_cols)

        self.dark_species_rows.clear()
        with self.dark_species_rows:
            for col, meas in lin_cols:
                dark_set = set(expt_data.dark_species.get(col, []))
                prefix = "UV-vis" if meas == "uvvis" else "Fluorescence"
                with ui.row().classes("items-center gap-4 flex-wrap"):
                    ui.label(f"{prefix}: {col}").classes("font-medium w-40")
                    for sp in species:

                        def _toggle(e, _col=col, _sp=sp) -> None:
                            ed = self.sm.active_expt_data
                            d = list(ed.dark_species.get(_col, []))
                            if e.value:
                                if _sp not in d:
                                    d.append(_sp)
                            else:
                                d = [s for s in d if s != _sp]
                            ed.dark_species[_col] = d

                        ui.checkbox(sp, value=(sp in dark_set), on_change=_toggle).classes("text-sm")

    async def run_fit(self) -> None:
        if self.sm.active_expt_data_id is None:
            ui.notify("No experimental data loaded. Please import data first.", type="negative")
            return

        # Check if the simulation name looks auto-generated but doesn't match the current auto-generated value
        auto_name = self.sm.active_model.name + " " + "fit"  # move to a function

        if (
            self.sm.active_fit_id is not None
            and hasattr(self.sm.active_fit, "name")
            and self.fit_name_input.value.startswith(self.sm.active_fit.name)
            and self.fit_name_input.value != auto_name
        ):
            with ui.dialog() as dialog, ui.card():
                ui.label(
                    "Warning: The fit name appears auto-generated but does not match the current model name. Consider updating the name."
                )
                with ui.row():
                    ui.button("Continue", on_click=lambda: dialog.submit("continue"))
                    ui.button(
                        "Generate new name and run",
                        on_click=lambda: dialog.submit("update"),
                    )
                    ui.button("Cancel", on_click=lambda: dialog.submit("cancel"))

            async def show_dialog():
                result = await dialog
                return result

            res = await show_dialog()
            if res == "cancel":
                ui.notify(
                    "Fit not run. Please choose a different name or update the current one.",
                    type="info",
                )
                return
            elif res == "continue":
                ui.notify("Continuing with the fit.", type="info")
            elif res == "update":
                # Update the fit name to the auto-generated value
                self.fit_name_input.set_value(auto_name)
                ui.notify(
                    f"Fit name updated to '{auto_name}'; now running.",
                    type="info",
                )

        if any(fit.name == self.fit_name_input.value for fit in self.sm.fits.values()):
            with ui.dialog() as dialog, ui.card():
                ui.label(f"A fit named '{self.fit_name_input.value}' already exists. Do you want to overwrite it?")
                with ui.row():
                    ui.button("Overwrite", on_click=lambda: dialog.submit(True))
                    ui.button("Cancel", on_click=lambda: dialog.submit(False))

            async def show_dialog():
                result = await dialog
                return result

            res = await show_dialog()
            if not res:
                ui.notify(
                    "Fit not run. Please choose a different name or delete the old fit.",
                    type="info",
                )
                return
            else:
                # Delete the existing simulation with that name
                existing_fit = next(
                    (fit for fit in self.sm.fits.values() if fit.name == self.fit_name_input.value),
                    None,
                )
                if existing_fit:
                    self.sm.delete_fit(existing_fit, notify_user=False, notify_listeners=False)
                ui.notify(
                    f"Overwriting fit '{self.fit_name_input.value}'.",
                    type="info",
                )

        self.m1 = self.sm.generate_binding_model_for_fit()
        if self.m1.analytical_fast_exchange:
            ui.notify(
                f"Using analytical fast-exchange backend ({self.m1.analytical_topology}).",
                type="info",
            )

        for param in self.m1.params:
            logger.info(f"Parameter before fit: {param} = {self.m1.params[param]}")

        self._set_fit_running(True)
        try:
            # self.m1.prepModel()
            # set parameter values/limits here... later.
            self.m1 = await run.cpu_bound(
                partial(
                    self.m1.runModel,
                    ret=True,
                    skip_col=np.shape(self.sm.active_expt_data.col_to_comp)[0],
                    method=str(self.fit_alg_select.value),
                )
            )
            if self.m1 is None:
                ui.notify("Fit failed to run. Check the console for details.", type="negative")
                return

            calc_obs = await run.cpu_bound(
                partial(bd.getCalcData, self.m1)
            )  # TODO resolve inconsistency between this and following line in bindtools
            speciation = await run.cpu_bound(self.m1.calcSpeciation)

            if self.m1.miniResult is None:
                ui.notify("Fit failed to converge. Check the console for details.", type="negative")
                return

            new_fit = FitResult(
                model_id=self.sm.active_model.id,
                expt_data_id=self.sm.active_expt_data_id,
                name=self.fit_name_input.value,
                description=self.fit_comment_input.value,
                aic=self.m1.miniResult.aic,
                bic=self.m1.miniResult.bic,
                chisqr=self.m1.miniResult.chisqr,
                termination_message=self.m1.miniResult.message if hasattr(self.m1.miniResult, "message") else "N/A",  # type: ignore
                success=getattr(self.m1.miniResult, "success", None),
                fit_method=str(self.fit_alg_select.value),
                init_expt_data=self.sm.active_expt_data,
                init_model=self.sm.active_model,
                bd_model=self.m1,
                analytical_fast_exchange=self.m1.analytical_fast_exchange,
                analytical_topology=self.m1.analytical_topology,
                analytical_obs_columns=[str(x) for x in self.m1.analytical_obs_columns],
                analytical_obs_components=[int(x) for x in self.m1.analytical_obs_components],
                analytical_complex_indices=self.m1.analytical_complex_indices,
            )
            self.sm.add_fit(new_fit)

            for k, v in self.m1.miniResult.params.items():  # type: ignore
                self.sm.active_fit.params[k] = {
                    "value": v.value,
                    "stderr": v.stderr,
                    "min": v.min,
                    "max": v.max,
                    "vary": v.vary,
                    "initial_value": v.init_value,
                }

            self.sm.active_fit.calc_obs = pd.DataFrame(calc_obs, columns=self.m1.obsList)

            self.sm.active_fit.fit_speciation = pd.DataFrame(speciation, columns=[x + "_free" for x in self.sm.species])

            self.sm.notify_listeners("redraw_fits_table")
            self.sm.notify_listeners("fit_completed")
            self._update_fit_graphs()
        except Exception:
            logger.exception("Fit run failed with an unhandled exception.")
            raise
        finally:
            self._set_fit_running(False)

    def _update_fit_graphs(self, e=None) -> None:
        """Update the fit results display."""
        logger.info("Updating fit results...")
        self.fit_graph.clear_graph(update=False)
        if len(self.sm.fits) > 0:
            self.speciation_graph.clear_graph(update=False)
            skipped_fit_names: list[str] = []
            for fit in self.sm.fits.values():
                x_plot, calc_plot, expt_plot, _ = _prepare_fit_plot_frames(fit)
                if calc_plot.empty:
                    skipped_fit_names.append(fit.name)
                    continue

                self.fit_graph.add_graph_lines_xy(x_plot, calc_plot, run_name=fit.name, run_id=fit.id, scatter="lines")
                self.fit_graph.add_graph_lines_xy(
                    x_plot, expt_plot, run_name=fit.name, run_id=fit.id, scatter="markers"
                )
                self.speciation_graph.add_graph_lines_xy(
                    fit.comp_concs, fit.fit_speciation, run_name=fit.name, run_id=fit.id, scatter="lines"
                )
            if skipped_fit_names:
                ui.notify(
                    "Skipped plotting non-fitted or invalid observable columns for: " + ", ".join(skipped_fit_names),
                    type="warning",
                )
        self.sync_graphs()
        self.generate_delete_fit_dropdown()

    def _init_load_fits(self, e=None) -> None:
        """Load initial set of fits"""
        fits_to_delete = []
        skipped_plot_fits: list[str] = []
        for fit in self.sm.fits.values():
            if (
                hasattr(fit, "fit_speciation")
                and not fit.fit_speciation.empty
                and hasattr(fit, "calc_obs")
                and not fit.calc_obs.empty
                and hasattr(fit, "comp_concs")
                and not fit.comp_concs.empty
            ):
                x_plot, calc_plot, expt_plot, _ = _prepare_fit_plot_frames(fit)
                if calc_plot.empty:
                    skipped_plot_fits.append(fit.name)
                    continue
                self.fit_graph.add_graph_lines_xy(x_plot, calc_plot, scatter="lines", run_name=fit.name, run_id=fit.id)
                self.fit_graph.add_graph_lines_xy(
                    x_plot, expt_plot, scatter="markers", run_name=fit.name, run_id=fit.id
                )
                self.speciation_graph.add_graph_lines_xy(
                    fit.comp_concs, fit.fit_speciation, scatter="lines", run_name=fit.name, run_id=fit.id
                )
                self.sync_graphs()
            else:
                fits_to_delete.append(fit)
                ui.notify(f"Fit {fit.name} is missing data and will be deleted.", type="negative")
        if skipped_plot_fits:
            ui.notify(
                "Skipped plotting non-fitted or invalid observable columns for: " + ", ".join(skipped_plot_fits),
                type="warning",
            )
        for fit in fits_to_delete:
            self.sm.delete_fit(fit, notify_user=False, notify_listeners=False)
        active_fit = self.sm.active_fit_or_none
        if active_fit is not None:
            self.fit_name_input.set_value(active_fit.name)
            self.fit_comment_input.set_value(active_fit.description)
            self.save_fit_details_button.set_enabled(True)
        else:
            self.fit_name_input.set_value("")
            self.fit_comment_input.set_value("")
            self.save_fit_details_button.set_enabled(False)

    def delete_fit(self, fit: FitResult) -> None:
        if fit.id in self.sm.fits:
            self.sm.delete_fit(fit)
            self.sm.notify_listeners("fits_loaded")
            self.sm.notify_listeners("fit_results_updated")
            ui.notify(f"Deleted fit: {fit.name}")
            self.sync_graphs()
            self.generate_delete_fit_dropdown()

        else:
            ui.notify(f"Fit {fit.name} not found in the list of fits.", type="negative")

    def sync_graphs(self) -> None:
        """Sync the graphs to the current state."""

        for x in self.graphs:
            x.update_x_axis_selects()
            x.update_graph_x()
            x.graph.update()

    def clear_fit_graphs(self) -> None:
        """Clear both fit graphs."""
        self.fit_graph.clear_graph(update=True)
        self.speciation_graph.clear_graph(update=True)
        ui.notify("Fit graphs cleared.", type="info")

    def generate_delete_fit_dropdown(self) -> None:
        """Generate the dropdown for deleting fits."""
        self.delete_fit_dropdown.clear()
        with self.delete_fit_dropdown:
            for fit in self.sm.fits.values():
                ui.item(
                    fit.name,
                    on_click=lambda e, fit=fit: self.delete_fit(fit),
                )

    def save_fit_details(self) -> None:
        self.sm.active_fit.name = self.fit_name_input.value
        self.sm.active_fit.description = self.fit_comment_input.value

    async def download_fit_data_csv(self) -> None:
        if self.sm.active_fit_id is None:
            ui.notify("No active fit to download.", type="negative")
            return

        fit = self.sm.active_fit
        if fit.calc_obs is None or fit.calc_obs.empty:
            ui.notify("No calculated fit data available to download.", type="negative")
            return

        export_frames: list[pd.DataFrame] = []
        expt_obj = getattr(fit, "_expt_data", None)

        if expt_obj is not None:
            comp_concs = fit.comp_concs.copy()
            if isinstance(comp_concs, pd.DataFrame) and not comp_concs.empty:
                export_frames.append(comp_concs.add_suffix("_component_conc"))

        expt_source = expt_obj.data if expt_obj is not None else pd.DataFrame()
        if isinstance(expt_source, pd.DataFrame) and not expt_source.empty:
            matching_cols = [col for col in fit.calc_obs.columns if col in expt_source.columns]
            if matching_cols:
                expt_df = expt_source[matching_cols].copy().reindex(fit.calc_obs.index)
                expt_df.columns = [f"{col}_expt" for col in expt_df.columns]
                export_frames.append(expt_df)

        calc_df = fit.calc_obs.copy()
        calc_df.columns = [f"{col}_calc" for col in calc_df.columns]
        export_frames.append(calc_df)

        if fit.fit_speciation is not None and not fit.fit_speciation.empty:
            spec_df = fit.fit_speciation.copy()
            spec_df.columns = [f"{col}_calc_species" for col in spec_df.columns]
            export_frames.append(spec_df)

        export_df = pd.concat(export_frames, axis=1)
        filename = f"fit_{safe_filename(fit.name, fallback='fit')}_data.csv"
        csv = export_df.to_csv(index=False, encoding="utf-8", float_format="{:.5e}".format)
        await custom_download(csv, filename=filename)
        ui.notify(f"Fit data downloaded as {filename}.", type="info")

    async def download_fit_notebook(self) -> None:
        """Export the active fit as a zip containing a Jupyter notebook and a data CSV."""
        if self.sm.active_fit_id is None:
            ui.notify("No active fit to export.", type="negative")
            return

        fit = self.sm.active_fit
        try:
            notebook, csv_df = self.sm.dump_fit_notebook(fit)
        except Exception as exc:
            ui.notify(f"Notebook export failed: {exc}", type="negative")
            return

        stem = safe_filename(fit.name, fallback="fit")
        nb_bytes = json.dumps(notebook, indent=1).encode()
        csv_bytes = csv_df.to_csv(index=False, float_format="{:.5e}".format).encode()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{stem}.ipynb", nb_bytes)
            zf.writestr(f"{stem}_data.csv", csv_bytes)
        buf.seek(0)

        zip_filename = f"{stem}_notebook.zip"
        await custom_download(buf.read(), filename=zip_filename)
        ui.notify(f"Notebook exported as {zip_filename}.", type="positive")


class FitResultsCard(BaseComponent):
    def setup_nicegui(self) -> None:

        with ui.card().classes("w-full lg:flex-1 min-w-0 overflow-hidden"):
            # ui.label("Fitting Results to go here.")
            with ui.row().classes("w-full"):
                ui.label("Results:")
                self._show_params_cb = ui.checkbox("Show params", value=True, on_change=self._load_fits_to_table)
                self._show_stats_cb = ui.checkbox("Show stats", value=False, on_change=self._load_fits_to_table)
            with ui.element("div").classes("w-full overflow-x-auto"):
                self.default_columns = [
                    {"name": "name", "label": "Name", "field": "name", "align": "left"},
                    {"name": "K1", "label": "K1", "field": "K1"},
                    {"name": "chisqr", "label": "ChiSqr", "field": "chisqr"},
                    {"name": "aic", "label": "AIC", "field": "aic"},
                    {"name": "bic", "label": "BIC", "field": "bic"},
                    {"name": "message", "label": "Message", "field": "message"},
                    {
                        "name": "fit_id",
                        "label": "Fit ID",
                        "field": "fit_id",
                        "classes": "hidden",
                        "headerClasses": "hidden",
                    },
                ]

                rows = [{"name": ""}]

                self.table = ui.table(columns=self.default_columns, rows=rows, row_key="name")

                self.table.add_slot(
                    "header",
                    r"""
    <q-tr :props="props">
        <q-th auto-width />
        <q-th v-for="col in props.cols" :key="col.name" :props="props" style="white-space:normal; word-break:break-all; max-width:64px">
            {{ col.label }}
        </q-th>
    </q-tr>
""",
                )

                # self.add_body_slot()
                self.table.on("delete", self.delete_row)
                self.table.on("rename", self.rename_fit)
                self.table.on("select", self.select_fit)

    # https://github.com/zauberzeug/nicegui/blob/main/examples/editable_table/main.py

    def setup_bindings(self) -> None:
        super().setup_bindings()
        self.sm.add_listener("fits_loaded", self._load_fits_to_table)
        self.sm.add_listener("redraw_fits_table", self._load_fits_to_table)
        self.sm.add_listener("fit_changed", self._load_fits_to_table)

    def _load_fits_to_table(self, e=None) -> None:
        """Load fits into the table."""
        show_params = getattr(self, "_show_params_cb", None)
        show_params = show_params.value if show_params is not None else True
        show_stats = getattr(self, "_show_stats_cb", None)
        show_stats = show_stats.value if show_stats is not None else False

        self.table.rows = []
        fitParams = []
        for fit in self.sm.fits.values():
            if hasattr(fit, "params"):
                fitParams += [x for x in list(fit.params.keys()) if x[3:] not in fit.model.component_names]

        fitParams = list(dict.fromkeys(fitParams))  # Remove duplicates

        paramCols = [
            {
                "name": param,
                "label": f"logK({param[3:]})" if param.startswith("log") else param,
                "field": param,
            }
            for param in fitParams
        ]

        stat_col_names = {"chisqr", "aic", "bic", "message", "covariance"}
        stat_cols = [c for c in self.default_columns if c["name"] in stat_col_names]
        hidden_cols = [c for c in self.default_columns if c.get("classes") == "hidden"]

        cols = [self.default_columns[0]]
        if show_params:
            cols.extend(paramCols)
        if show_stats:
            cols.extend(stat_cols)
        cols.extend(hidden_cols)

        self.table.columns = cols

        for fit in self.sm.fits.values():
            row = {
                "name": fit.name,
                "chisqr": self.rounded_value(fit.chisqr),
                "aic": self.rounded_value(fit.aic, dp=1),
                "bic": self.rounded_value(fit.bic, dp=1),
                "message": fit.termination_message,
                "fit_id": str(fit.id),
                "is_active": str(fit.id) == str(self.sm.active_fit_id),
                # 'covariance': fit.miniResult.covariance if hasattr(fit.miniResult, 'covariance') else 'N/A'
            }
            for param in fitParams:
                if param in fit.params:
                    row[param] = self.rounded_value(fit.params[param]["value"])
                else:
                    row[param] = "N/A"
            self.table.rows.append(row)
        self.add_body_slot()
        self.table.update()

    def rounded_value(self, value: float, dp: int = 3) -> str:
        """Round the value for display."""
        if abs(value) >= 10000 or abs(value) < 0.001:
            return f"{value:.4e}"
        else:
            return f"{value:.{dp}f}" if isinstance(value, float) else str(value)

    def add_body_slot(self) -> None:
        """Add the body slot for the table."""
        self.table.add_slot(
            "body",
            r"""
    <q-tr :props="props" :class="props.row.is_active ? 'bg-blue-1' : ''" @click="() => $parent.$emit('select', props.row)" style="cursor: pointer">
        <q-td auto-width >
            <q-btn size="xs" color="warning" round dense icon="delete"
                @click="() => $parent.$emit('delete', props.row)"
            />
        </q-td>
        <q-td key="name" :props="props">
            {{ props.row.name }}
            <q-popup-edit v-model="props.row.name" v-slot="scope"
                @update:model-value="() => $parent.$emit('rename', props.row)"
            >
                <q-input v-model="scope.value" dense autofocus counter @keyup.enter="scope.set" />
            </q-popup-edit>
        </q-td>"""
            + "".join(
                [
                    f'''
        <q-td key="{col["name"]}" :props="props">
            {{{{ props.row.{col["field"]} }}}}
            </q-td>'''
                    for col in self.table.columns[1:]
                ]
            )
            + """</q-tr>
""",
        )

    def delete_row(self, e: events.GenericEventArguments) -> None:
        """Delete a row from the table."""
        fit_id = uuid.UUID(e.args["fit_id"])
        fit = self.sm.fits.get(fit_id)
        if fit is None:
            return
        self.sm.delete_fit(fit)
        self.sm.notify_listeners("fits_loaded")
        self.sm.notify_listeners("fit_results_updated")

    def select_fit(self, e: events.GenericEventArguments) -> None:
        fit_id = uuid.UUID(e.args["fit_id"])
        if fit_id in self.sm.fits:
            self.sm.active_fit_id = fit_id
            self.sm.notify_listeners("fit_changed")
            self.sm.notify_listeners("active_context_changed", {})

    def rename_fit(self, e: events.GenericEventArguments) -> None:
        print(e)
