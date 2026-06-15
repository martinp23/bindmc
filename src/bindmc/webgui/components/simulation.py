import json
import numpy as np
import pandas as pd
from nicegui import run, ui
import bindtools.binding as bd

from ..classes import Simulation
from ..utils import safe_filename, custom_download
from .base import BaseComponent
from .graph import Graph


class SimulationPanel(BaseComponent):
    def setup_nicegui(self):

        self.container = ui.column().classes("w-full")
        with self.container:
            with ui.row().classes("w-full mb-4"):
                ui.button("Run Simulation", on_click=self.run_simulation).classes("mb-4")
                self.clear_graph_button = ui.button("Clear Graph").classes("mb-4")
                # Dropdown for loading and deleting simulations
                self.sim_dropdown = ui.dropdown_button("Load/Delete Simulation", auto_close=True).classes("mb-4")
                self.generate_sims_dropdown()

            # Add name and comment inputs with save button
            with ui.card().classes("w-full mb-4"):
                ui.label("Simulation Details")
                with ui.row().classes("w-full"):
                    self.sim_name_input = ui.input("Simulation Name", placeholder="Enter simulation name").classes(
                        "flex-1"
                    )
                    self.sim_comment_input = ui.input("Comment", placeholder="Enter comment").classes("flex-1")
                    ui.button(
                        "Auto-generate title",
                        on_click=lambda: self.sim_name_input.set_value(
                            self.sm.active_model.name
                            + " "
                            + ", ".join(
                                [
                                    f"{k.species}={k.logK}"
                                    for k in self.sm.active_model.binding_constants
                                    if not k.isComp
                                ]
                            )
                        ),
                    ).classes("ml-4")
                    self.save_sim_details_button = ui.button(
                        "Save changes to name/comment", on_click=self.save_sim_details
                    ).classes("ml-4")
                    self.save_sim_details_button.set_enabled(False)
                    self.download_sim_button = ui.button(
                        "Download Simulation Data",
                        on_click=self.download_sim_data,
                    ).classes("ml-4")
                    self.export_sim_notebook_button = ui.button(
                        "Export to Notebook",
                        on_click=self.download_sim_notebook,
                    ).classes("ml-4")

            self.graphEl = ui.element().classes("w-full lg:w-[min(60vw,80vh)] relative")
            with self.graphEl:
                self.graph = Graph(self.sm, mode="sim")
                self.spinner = ui.spinner(size="xl").classes("absolute-center")

            self.clear_graph_button.on_click(self.graph.clear_graph)
            self.spinner.visible = False

    def setup_bindings(self):
        active_sim = self.sm.active_sim_or_none
        if active_sim is not None:
            self.sim_name_input.set_value(active_sim.name)
            self.sim_comment_input.set_value(active_sim.comment)
            self.save_sim_details_button.set_enabled(True)

        self.sm.add_listener("simulation_deleted", self.update_after_sim_deleted)
        self.sm.add_listener("sim_changed", self._refresh_for_active_sim)

    def _refresh_for_active_sim(self, e=None):
        """Refresh the simulation panel to reflect the current active simulation."""
        self.generate_sims_dropdown()
        active_sim = self.sm.active_sim_or_none
        if active_sim is None:
            self.sim_name_input.set_value("")
            self.sim_comment_input.set_value("")
            self.save_sim_details_button.set_enabled(False)
            self.graph.clear_graph()
            ui.notify("No simulations for the current context.", type="warning")
            return
        self.sim_name_input.set_value(active_sim.name)
        self.sim_comment_input.set_value(active_sim.comment)
        self.save_sim_details_button.set_enabled(True)
        if active_sim.results is not None and not active_sim.results.empty:
            self.graph.clear_graph()
            self.graph.add_graph_lines_xy(
                active_sim.comp_concs, active_sim.results, active_sim.name, str(active_sim.id)
            )
            self.graph.update_graph()

    async def run_simulation(self, e):
        """Run the simulation based on the current model data."""

        # Check if the simulation name looks auto-generated but doesn't match the current auto-generated value
        auto_name = (
            self.sm.active_model.name
            + " "
            + ", ".join([f"{k.species}={k.logK}" for k in self.sm.active_model.binding_constants if not k.isComp])
        )

        # if there is no simulation name, prmopt the user to cancel or use the auto-generated name
        if not self.sim_name_input.value:
            with ui.dialog() as dialog, ui.card():
                ui.label(f"Simulation name is empty. Do you want to use the auto-generated name: \n{auto_name}?").style(
                    "white-space: pre-wrap;"
                )
                with ui.row():
                    ui.button("Use auto-generated name", on_click=lambda: dialog.submit(auto_name))
                    ui.button("Cancel", on_click=lambda: dialog.submit(None))

            async def show_dialog():
                result = await dialog
                return result

            res = await show_dialog()
            if res is None:
                ui.notify(
                    "Simulation not run. Please enter a simulation name.",
                    type="info",
                )
                return
            else:
                self.sim_name_input.set_value(res)

        if self.sim_name_input.value.startswith(self.sm.active_model.name) and self.sim_name_input.value != auto_name:
            with ui.dialog() as dialog, ui.card():
                ui.label(
                    "Warning: The simulation name appears auto-generated but does not match the current model and constants. Consider updating the name."
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
                    "Simulation not run. Please choose a different name or update the current one.",
                    type="info",
                )
                return
            elif res == "continue":
                ui.notify("Continuing with the simulation.", type="info")
            elif res == "update":
                # Update the simulation name to the auto-generated value
                self.sim_name_input.set_value(auto_name)
                ui.notify(
                    f"Simulation name updated to '{auto_name}'; now running.",
                    type="info",
                )

        if any(sim.name == self.sim_name_input.value for sim in self.sm.simulations.values()):
            with ui.dialog() as dialog, ui.card():
                ui.label(
                    f"A simulation named '{self.sim_name_input.value}' already exists. Do you want to overwrite it?"
                )
                with ui.row():
                    ui.button("Overwrite", on_click=lambda: dialog.submit(True))
                    ui.button("Cancel", on_click=lambda: dialog.submit(False))

            async def show_dialog():
                result = await dialog
                return result

            res = await show_dialog()
            if not res:
                ui.notify(
                    "Simulation not run. Please choose a different name or delete the old simulation.",
                    type="info",
                )
                return
            else:
                # Delete the existing simulation with that name
                existing_sim = next(
                    (sim for sim in self.sm.simulations.values() if sim.name == self.sim_name_input.value),
                    None,
                )
                if existing_sim:
                    self.sm.delete_simulation(existing_sim, notify_listeners=False)
                ui.notify(
                    f"Overwriting simulation '{self.sim_name_input.value}'.",
                    type="info",
                )

        try:
            eq_mat = []
            if self.sm.eq_mat_str:  # TODO this is weird. fix it.
                eq_mat = np.array(self.sm.eq_mat)

            comp_concs = self.sm.comp_concs.to_numpy()
            m1 = bd.bindingModel(eq_mat, self.sm.component_names, self.sm.species, compConcs=comp_concs)
            m1.prepModel()

            # set parameter values
            for s in self.sm.species:
                k = [k for k in self.sm.binding_constants if k.species == s][0]
                m1.params["log" + k.species].set(
                    value=k.logK,
                    max=k.logK + 1 if k.logK is not None else None,
                    min=k.logK - 1 if k.logK is not None else None,
                )

            self.spinner.visible = True

            spec = await run.cpu_bound(m1.calcSpeciation)
            calc_result = pd.DataFrame(spec, columns=[x + "_free" for x in self.sm.species])

            new_sim = Simulation(
                comp_concs=self.sm.comp_concs.copy(),
                model_id=self.sm.active_model.id,
                name=self.sim_name_input.value,
                comment=self.sim_comment_input.value,
            )

            self.sm.add_sim(new_sim)
            currSim = new_sim
            currSim.find_and_link_model(self.sm.models)
            currSim.comp_concs.columns = [f"{c}_tot" for c in currSim.comp_concs.columns]
            # cols = [f'{c}_tot' for c in self.sm.comp_concs.columns]
            # currSim.comp_concs.columns = [f'{c}_tot' for c in currSim.comp_concs.columns]

            comp_concs_df = currSim.comp_concs  # pd.DataFrame(self.sm.comp_concs.values,columns=cols)

            # # Fix index mismatch - reset both indexes to ensure they match
            comp_concs_df = comp_concs_df.reset_index(drop=True)
            calc_result = calc_result.reset_index(drop=True)

            currSim.results = comp_concs_df.merge(calc_result, left_index=True, right_index=True, how="inner")

            # Enable save button
            self.save_sim_details_button.set_enabled(True)

            self.spinner.visible = False

            self.graph.add_graph_lines_xy(comp_concs_df, calc_result, currSim.name, str(currSim.id))
            self.graph.update_graph()
            self.generate_sims_dropdown()
            self.sm.save_to_storage()
            ui.notify(f"Simulation {currSim.name} completed successfully.", type="info")

        except Exception as e:
            ui.notify("Error creating binding model: " + str(e), type="negative")
            return

    def generate_sims_dropdown(self):
        self.sim_dropdown.clear()
        with self.sim_dropdown:
            for sim in self.sm.simulations.values():
                with ui.row():
                    ui.item(
                        sim.name,
                        on_click=lambda sim=sim: self.load_simulation(sim),
                    )
                    ui.button(
                        "Delete",
                        color="negative",
                        icon="delete",
                        on_click=lambda sim=sim: self.delete_simulation(sim),
                    ).classes("ml-2")

    def save_sim_details(self, e):
        """Save the simulation name and comment."""
        if self.sm.active_sim:
            self.sm.active_sim.name = self.sim_name_input.value
            self.sm.active_sim.comment = self.sim_comment_input.value
            ui.notify(f"Simulation details saved: {self.sm.active_sim.name}", type="info")
            self.sm.save_to_storage(e)

    def update_after_sim_deleted(self, e=None):
        """Update the UI after (one or more) simulation is deleted."""
        self.generate_sims_dropdown()
        active_sim = self.sm.active_sim_or_none
        if self.sm.active_sim_id is not None and active_sim is not None:
            self.sim_name_input.set_value(active_sim.name)
            self.sim_comment_input.set_value(active_sim.comment)
        else:
            self.sim_name_input.set_value("")
            self.sim_comment_input.set_value("")
        self.save_sim_details_button.set_enabled(False)

        sim_ids = [str(sim.id) for sim in self.sm.simulations.values()]
        missing_ids = list(
            set(
                [row["trace_id"][0:36] for row in self.graph.graph_data["data"] if row["trace_id"][0:36] not in sim_ids]
            )
        )

        for id in missing_ids:
            self.graph.remove_data(id)

        self.generate_sims_dropdown()
        self.graph.update_x_axis_selects()
        self.graph.update_graph_x()
        self.graph.graph.update()

    def load_simulation(self, sim):
        """Load a simulation and update the UI."""
        self.sm.active_sim_id = sim.id
        self.sim_name_input.set_value(sim.name)
        self.sim_comment_input.set_value(sim.comment)
        self.save_sim_details_button.set_enabled(True)

        # Update the graph with the loaded simulation data
        self.graph.clear_graph()
        self.graph.add_graph_lines_xy(sim.comp_concs, sim.results, sim.name, str(sim.id))
        self.graph.update_graph()
        ui.notify(f"Loaded simulation: {sim.name}", type="info")

    def delete_simulation(self, sim):
        """Delete a simulation and update the UI."""
        self.sm.delete_simulation(sim)

    async def download_sim_data(self):
        """Download the current simulation data as a CSV file."""
        active_sim = self.sm.active_sim_or_none
        if active_sim is None:
            ui.notify("No active simulation to download.", type="negative")
            return

        sim_data = active_sim.results
        csv = sim_data.to_csv(index=False, encoding="utf-8", float_format="{:.5e}".format)
        filename = f"simulation_{safe_filename(active_sim.name, fallback='simulation')}_data.csv"
        await custom_download(csv, filename=filename)
        ui.notify(f"Simulation data downloaded as {filename}.", type="info")

    async def download_sim_notebook(self) -> None:
        """Export the active simulation as a Jupyter notebook (.ipynb) and download it."""
        active_sim = self.sm.active_sim_or_none
        if active_sim is None:
            ui.notify("No active simulation to export.", type="negative")
            return

        try:
            notebook = self.sm.dump_simulation_notebook(active_sim)
        except Exception as exc:
            ui.notify(f"Notebook export failed: {exc}", type="negative")
            return

        stem = safe_filename(active_sim.name, fallback="simulation")
        filename = f"{stem}.ipynb"
        content = json.dumps(notebook, indent=1)
        await custom_download(content, filename=filename)
        ui.notify(f"Notebook exported as {filename}.", type="positive")
