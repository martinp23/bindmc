from .base import BaseComponent
from nicegui import ui
import numpy as np
import pandas as pd
from ..classes import Component
from .graph import Graph
from ..utils import custom_download

from nicegui.events import UploadEventArguments
from collections import Counter
import io


class DataGenerationPanel(BaseComponent):
    def _create_comp_table(self, df: pd.DataFrame) -> None:
        self.compTable = (
            ui.table.from_pandas(
                df,
                column_defaults={
                    "align": "right",
                    ":format": """value => {
            if (value == null) return ''
            const v = Number(value)

            if (Math.abs(v) < 1e-16) return '0'

            return (Math.abs(v) >= 1e4 || Math.abs(v) < 1e-3)
                ? v.toExponential(3)
                : v.toFixed(3)
            }""",
                },
            )
            .classes("w-full")
            .props('dense hide-bottom :pagination="{rowsPerPage: 0}"')
            .mark("gen-data-table")
        )

    def setup_nicegui(self):
        self.container = ui.column().classes("w-full")

        with self.container:
            # Responsive layout:
            # - narrow screens: stack cards top-to-bottom
            # - wide screens: show cards side-by-side (generation left, table/graph right)
            with ui.row().classes("w-full gap-4 items-start flex-col lg:flex-row"):
                with ui.card().classes("w-full lg:flex-1 min-w-0"):
                    self.gen_settings = ui.element()
                    with self.gen_settings:
                        ui.label("Data Generation Panel").classes("text-lg font-bold mb-4")
                        ui.label("This panel contains data generation tools and options.")
                        with ui.row():
                            self.nCompInp = (
                                ui.input("Number of components")
                                .bind_value(self.sm, "nComp")
                                .mark("num-components")
                                .set_enabled(False)
                            )  # .on_value_change(self.simUpdateNumComponents)
                            # self.nCompEditable = ui.checkbox("",value=False).props('checked-icon=edit unchecked-icon=edit_off').classes('q-pa-md')
                            # self.nCompInp.bind_enabled_from(self.nCompEditable,'value')
                            # change this to be a nice pen icon that is crossed out
                            self.nStepInp = (
                                ui.number("Number of steps", precision=0, min=1)
                                .mark("num-steps")
                                .bind_value(self.sm, "nStep")
                            )
                            ui.button("Upload component concentrations", on_click=self.upload_comp_concs)
                        # Wrap component blocks left-to-right, then top-to-bottom
                        self.comp_gens = ui.row().classes("w-full flex-wrap items-start gap-4")

                        self.set_up_component_gen_rows(self.sm.nComp)
                        with ui.row().classes("mt-4 gap-4"):
                            ui.button("Generate Component Concentrations", on_click=self.calc_comp_concs)
                            ui.button("Reset", on_click=self.resetcomp_concs)

                with ui.card().classes("w-full lg:flex-1 min-w-0"):
                    self.table_and_graph = ui.element().classes("w-full")
                    with self.table_and_graph:
                        with (
                            ui.tabs()
                            .classes("w-full")
                            .props('align="justify"')
                            .on("update:model-value", self._table_graph_tab_changed)
                        ) as tabs:
                            self.table_tab = ui.tab("Table")
                            self.graph_tab = ui.tab("Graph")
                        with ui.tab_panels(tabs, value=self.table_tab).classes("w-full"):
                            with ui.tab_panel(self.table_tab):
                                self.tableBlock = ui.element().classes("w-full")
                                with self.tableBlock:
                                    ui.label("Generated data:")
                                    with (
                                        ui.element("div")
                                        .classes("w-full max-h-[30rem] overflow-y-scroll")
                                        .style("scrollbar-gutter: stable;")
                                    ):
                                        self._create_comp_table(self.sm.comp_concs)

                            with ui.tab_panel(self.graph_tab):
                                ui.label("Generated data:")
                                self.preview_graph = Graph(self.sm, mode="data_preview")
                                if len(self.sm.comp_concs) > 0:
                                    self.preview_graph.add_graph_lines(
                                        self.sm.comp_concs, run_name="Gen", run_id=str(self.sm.active_model_id)
                                    )  # Add graph lines for the generated data
                                    self.preview_graph.update_graph()

    def _table_graph_tab_changed(self, e) -> None:
        # Plotly elements often compute width incorrectly when created inside a hidden tab.
        # Forcing an update when the Graph tab becomes active makes it fill the card width.
        if getattr(e, "args", None) != "Graph":
            return
        if not hasattr(self, "preview_graph"):
            return
        try:
            self.preview_graph.graph.update()
        except Exception:
            pass
        try:
            ui.run_javascript('window.dispatchEvent(new Event("resize"));')
        except Exception:
            pass

    async def upload_comp_concs(self, e):

        with ui.dialog() as dialog, ui.card():
            ui.label("Upload concentrations (csv)").classes("w-full text-center text-2xl font-bold")
            template_text = ",".join([comp.name for comp in self.sm.components])
            template_text += "\nmM" + ",mM" * (len(self.sm.components) - 1)  # Header row with units
            template_text += "\n" + "0.001" + ",0" * (len(self.sm.components) - 1)  # Add a newline after the header

            async def download_template():
                await custom_download(template_text, "component_concentrations_template.csv")

            ui.button(
                "Download template CSV",
                on_click=download_template,
            )

            ui.label("""
1. Download the template CSV file and open it in Excel or your preferred spreadsheet software.
2. The first row contains the component names. Do not change this row.
3. The second row contains the units for each component (M, mM, µM/uM, nM). Ensure these are correct, and change them if needed.
4. Starting from the third row, enter the concentration values for each component. You can change the existing data.
5. Save as a CSV, then upload your file by pressing the (+) button below.""").style("white-space: pre-wrap")
            upload_box = ui.upload(label="Choose file", auto_upload=True).props('accept=".csv"')

            ui.button("Cancel", on_click=lambda: dialog.submit("cancel"))

            def on_upload_complete(e: UploadEventArguments) -> None:
                dialog.submit(e)  # Store result for later

            upload_box.on_upload(on_upload_complete)

        result: UploadEventArguments | str = await dialog

        if isinstance(result, str) and result == "cancel":
            ui.notify("Project loading cancelled", type="info")
            return

        elif isinstance(result, UploadEventArguments):
            filename = result.file.name

            if filename.endswith(".csv"):
                file_content = await result.file.text("utf-8")
            else:
                ui.notify("Unsupported file format. Please upload a .csv file.", type="negative")
                return
            concs = pd.read_csv(io.StringIO(file_content), header=0, index_col=False, skiprows=[1])
            units = file_content.splitlines()[1].split(",")

            # check names are all valid
            expected_names = [comp.name for comp in self.sm.components]
            if Counter(concs.columns) != Counter(expected_names):
                ui.notify(
                    f"Component names in uploaded file do not match expected names: {', '.join(expected_names)}",
                    type="negative",
                )
                return

            # check units are all valid
            valid_units = ["M", "mM", "uM", "µM", "nM"]
            for unit in units:
                if unit not in valid_units:
                    ui.notify(
                        f"Invalid unit '{unit}' found in uploaded file. Valid units are: {', '.join(valid_units)}",
                        type="negative",
                    )
                    return

            # do unit conversion to M
            for i, comp in enumerate(concs.columns):
                unit = units[i]
                if unit == "M":
                    factor = 1
                elif unit == "mM":
                    factor = 1e-3
                elif unit in ["uM", "µM"]:
                    factor = 1e-6
                elif unit == "nM":
                    factor = 1e-9
                else:
                    factor = 1  # should not happen due to earlier check
                concs[comp] = concs[comp] * factor

            self.sm.comp_concs = concs
            self.sm.active_model.component_concs = concs
            self.update_comp_table()

    def calc_comp_concs(self, e):
        """Calculate component concentrations based on user input."""

        # remove components that are no longer in the list
        compNames = [comp.name for comp in self.sm.components]
        self.sm.components = [comp for comp in self.sm.components if comp.name in compNames]

        df = pd.DataFrame({})
        try:
            for comp in self.sm.components:
                if comp.constant is True:
                    df[comp.name] = [comp.start_conc] * int(self.sm.nStep)

                else:
                    if comp.spacing == "lin":
                        df[comp.name] = np.linspace(
                            comp.start_conc if comp.start_conc is not None else 0,
                            comp.end_conc if comp.end_conc is not None else 0,
                            int(self.sm.nStep),
                        )

                    elif comp.spacing == "log":
                        pass
        except Exception as e:
            if isinstance(e, TypeError):
                ui.notify(
                    "Error in component concentration calculation. Most likely you have not provided start/end concentrations. "
                    + str(e),
                    type="negative",
                )
                return

        self.sm.comp_concs = df
        self.sm.active_model.component_concs = (
            df  # Update the active model's component concentrations # TODO make this a getter setter deal
        )
        # self.preview_graph.add_graph_lines(df, run_name="Gen", run_id=str(self.sm.active_model_id))  # Add graph lines for the generated data

        # self.preview_graph.update_graph()
        self.update_comp_table()

        self.sm.notify_listeners("comp_concs_updated")
        # self.compTable.clear()
        # self.compTable = ui.table.from_pandas(df)    # make it pretty - rounding, units, spacing reduction.

    def update_comp_table(self):
        self.tableBlock.clear()
        with self.tableBlock:
            ui.label("Generated data:")
            with ui.element("div").classes("w-full max-h-[30rem] overflow-y-scroll").style("scrollbar-gutter: stable;"):
                self._create_comp_table(self.sm.comp_concs)

        self.preview_graph.clear_graph()  # Clear existing graph data
        self.preview_graph.add_graph_lines(
            self.sm.comp_concs, run_name="Gen", run_id=str(self.sm.active_model_id)
        )  # Add graph lines for the generated data
        self.preview_graph.update_graph()

        self.sm.notify_listeners("comp_concs_updated")

    def resetcomp_concs(self, e):
        self.comp_concs = pd.DataFrame({})
        self.set_up_component_gen_rows(
            self.sm.nComp
        )  # Reset component generation rows based on the number of components

    # save states e.g. initial, after simrun, etc?
    # history/undo options?

    def setup_bindings(self):
        self.sm.add_listener("model_changed", self.regen_comps)

    def regen_comps(self, e=None):
        self.set_up_component_gen_rows(
            len(self.sm.components)
        )  # Update component generation rows based on the model's components
        self.tableBlock.clear()
        with self.tableBlock:
            ui.label("Generated data:")
            with ui.element("div").classes("w-full max-h-[30rem] overflow-y-scroll").style("scrollbar-gutter: stable;"):
                self._create_comp_table(self.sm.comp_concs)

    def set_up_component_gen_rows(self, n: int):
        """Set up the component generation rows based on the number of components."""

        self.comp_gens.clear()

        for ii in range(n):
            with self.comp_gens:
                if ii < len(self.sm.components):
                    # If the component already exists, use its data
                    self.addCompBox(
                        ii,
                        name=self.sm.components[ii].name,
                        constant=self.sm.components[ii].constant,
                        start=self.sm.components[ii].start_conc_nice,
                        startunit=self.sm.components[ii].start_units,
                        end=self.sm.components[ii].end_conc_nice,
                        endunit=self.sm.components[ii].end_units,
                    )
                else:
                    # If the component does not exist, create a new one with default values
                    # This allows for adding new components without losing existing ones
                    self.sm.components.append(Component(name=f"Component {ii + 1}"))  # Add a new component to the list
                    self.addCompBox(ii)

        if len(self.sm.components) > n:
            # If there are more components than requested, remove the excess
            self.sm.components = self.sm.components[:n]

    def addCompBox(
        self,
        n,
        name="",
        constant=False,
        start=None,
        startunit="mM",
        end=None,
        endunit="mM",
        new=False,
    ):

        c = ui.card().classes("w-full sm:w-56 md:w-64 flex-none")
        with c:
            ui.label(f"Component {n + 1}:").classes("w-full text-center text-lg font-bold")
            ui.input("Name").mark(f"comp-name-{n + 1}").bind_value(self.sm.components[n], "name")
            ui.checkbox("Constant conc?", value=constant, on_change=self.changeConstantConc).mark(
                f"constant-conc-{n + 1}-checkbox"
            ).bind_value(self.sm.components[n], "constant")
            with ui.row().classes("start-conc-row"):
                ui.number("Start:", step=0.001, value=start).classes("w-24").mark(f"start-conc-{n + 1}-val").bind_value(
                    self.sm.components[n], "start_conc_nice"
                )
                ui.select(["M", "mM", "µM", "nM"], value=startunit).classes("w-20").mark(
                    f"start-conc-{n + 1}-unit"
                ).bind_value(self.sm.components[n], "start_units")
            with ui.row().classes("end-conc-row"):
                ui.number("End:", step=0.001, value=end).classes("w-24").mark(f"end-conc-{n + 1}-val").bind_value(
                    self.sm.components[n], "end_conc_nice"
                )
                ui.select(["M", "mM", "µM", "nM"], value=endunit).classes("w-20").mark(
                    f"end-conc-{n + 1}-unit"
                ).bind_value(self.sm.components[n], "end_units")

        return c

    def getEventSiblings(self, e):
        """Get all siblings of the event sender."""
        compBlock = next(e.sender.ancestors())
        return compBlock.default_slot.children

    def changeConstantConc(self, e):
        """Handle changes to the constant concentration checkbox."""

        # Store references to UI elements when creating them instead of trying to find them later
        # For now, just print the checkbox state as a placeholder
        els = self.getEventSiblings(e)

        if e.value:
            for el in els:
                if isinstance(el, ui.row):
                    # these are start/end concentration rows
                    inStartRow = True
                    for child in el.default_slot.children:
                        if isinstance(child, ui.number) and child.label == "Start:":
                            inStartRow = True
                            child.label = "Conc:"
                        elif isinstance(child, ui.number) and child.label == "End:":
                            inStartRow = False
                            child.value = None
                            child.enabled = False
                        elif isinstance(child, ui.select) and not inStartRow:
                            child.value = "mM"
                            child.enabled = False

        else:
            self.resetCompConcBlock(els)

    def resetCompConcBlock(self, els):
        """Reset the concentration block for a component."""
        """Takes a list of elements, which should comprise a component block."""
        for el in els:
            if isinstance(el, ui.row):
                # these are start/end concentration rows
                inStartRow = True
                for child in el.default_slot.children:
                    if isinstance(child, ui.number) and child.label == "Conc:":
                        inStartRow = True
                        child.label = "Start:"
                    elif isinstance(child, ui.number) and child.label == "End:":
                        inStartRow = False
                        child.value = None
                        child.enabled = True
                    elif isinstance(child, ui.select) and not inStartRow:
                        child.value = "mM"
                        child.enabled = True
