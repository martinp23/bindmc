import io
import math

import pandas as pd
from nicegui import ui
from nicegui.events import UploadEventArguments, ClickEventArguments

from .base import BaseComponent
from .graph import Graph
from .dataset_selector import DatasetSelector
from ..classes import ExptData, RawData, ExptDataType


class DataImportPanel(BaseComponent):
    def __init__(self, sm):
        super().__init__(sm)
        self.dep_indep_dropdowns = []
        self.dep_indep_labels = []
        self.ignore_checkboxes = []

        self.dtype_labels = []
        self.dtype_dropdowns = []
        self._restore_point = self._backup_expt(self.sm.active_expt_data_or_none)

    def setup_nicegui(self):
        self.container = ui.column().classes("w-full")

        with self.container:
            ui.label("Data Import panel").classes("text-lg font-bold mb-4")
            # Responsive layout:
            # - narrow screens: stack cards top-to-bottom
            # - wide screens: show cards side-by-side (controls left, table/graph right)
            with ui.row().classes("w-full gap-4 items-start flex-col lg:flex-row"):
                with ui.card().classes("w-full lg:flex-1 min-w-0"):
                    self.selector = DatasetSelector(self.sm)

                    ui.label("Upload Data File (CSV or Excel)")
                    ui.button("Upload File", on_click=self.load_exptdata)

                    self.expt_data_col_block = ui.element()
                    with self.expt_data_col_block:
                        ui.label("Column Metadata:")

                    self.make_model_button = ui.button("Prepare data model", on_click=self.prepare_data_model)

                with ui.card().classes("w-full lg:flex-1 min-w-0"):
                    ui.label("Data")
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
                                self.expt_data_table_block = ui.element().classes("w-full")

                            with ui.tab_panel(self.graph_tab):
                                ui.label("Experimental data preview")
                                self.preview_graph = Graph(self.sm, mode="expt_preview")

    def _table_graph_tab_changed(self, e) -> None:
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

    def setup_bindings(self):
        super().setup_bindings()
        self.sm.add_listener("data_imported", self._load_data_to_table)
        self.sm.add_listener("active_context_changed", self._load_data_to_table)
        self.sm.add_listener(
            "expt_data_columns_changed", self._load_data_to_table
        )  # Update when column selection changes

    def _backup_expt(self, old_expt: ExptData) -> ExptData:
        """Return a copy of old_expt with the SAME UUID and name (a true backup)."""
        if old_expt is None:
            return None
        from ..classes import ChemicalShiftParam
        d = old_expt.to_dict()
        limiting_shifts_raw = d.pop("limiting_shifts", []) or []
        new_expt = ExptData(**d)
        new_expt.limiting_shifts = {}
        for cs in limiting_shifts_raw:
            csp = ChemicalShiftParam(**cs)
            key = (csp.species, csp.col)
            new_expt.limiting_shifts[key] = csp
        new_expt.find_and_link_model(self.sm.models)
        new_expt.find_and_link_raw_data(self.sm.raw_datas)
        return new_expt



    def prepare_data_model(self, e: ClickEventArguments):
        active_raw = self.sm.active_raw_data_or_none
        active_expt = self.sm.active_expt_data_or_none
        if self.sm.active_raw_data_id is not None and active_raw is not None:
            if active_expt is not None and active_expt.raw_data_id == active_raw.id:
                # Check if selected columns or details have changed from the restore point
                has_changes = False
                if hasattr(self, "_restore_point") and self._restore_point is not None:
                    if set(active_expt.selected_columns) != set(self._restore_point.selected_columns):
                        has_changes = True
                    else:
                        for col in active_expt.selected_columns:
                            old_det = self._restore_point.col_details.get(col, {})
                            new_det = active_expt.col_details.get(col, {})
                            if old_det.get("depindep") != new_det.get("depindep") or old_det.get("dtype") != new_det.get("dtype"):
                                has_changes = True
                                break
                
                # Check if there are changes in the unassigned auto-deselect columns too
                for col in active_expt.data.columns:
                    col_details = active_expt.col_details.get(col, {})
                    is_component = col.startswith("[") and col.endswith("]")
                    has_assignment = (col_details.get("depindep") in ["dep", "indep"]) and (
                        col_details.get("dtype") is not None
                    )
                    if not is_component and not has_assignment:
                        if col in active_expt.selected_columns:
                            has_changes = True

                if has_changes:
                    # Detect if there is existing work associated with this ExptData
                    has_model_work = False
                    if (
                        (active_expt.limiting_shifts and len(active_expt.limiting_shifts) > 0)
                        or (active_expt.delta_to_spec is not None and active_expt.delta_to_spec.size > 0)
                        or (active_expt.integ_to_spec is not None and active_expt.integ_to_spec.size > 0)
                    ):
                        has_model_work = True
                    
                    has_fits = any(fit.expt_data_id == active_expt.id for fit in self.sm.fits.values())
                    has_mcmc = any(mcmc.expt_data_id == active_expt.id for mcmc in self.sm.mcmcs.values())
                    
                    if has_model_work or has_fits or has_mcmc:
                        # Existing work exists, prompt user to Overwrite or Rename
                        self.prompt_overwrite_or_rename(active_expt, has_fits, has_mcmc, has_model_work)
                    else:
                        # No existing work to lose, perform direct overwrite in-place
                        self.prepare_data_model_overwrite(active_expt, delete_dependents=False)
                else:
                    self._load_expt_data_col_details()
                    self._load_data_to_table()
                    ui.notify("Data model prepared.", type="positive")
            else:
                rd = active_raw
                new_expt_data = ExptData(name=rd.filename, init_raw_data=rd, init_model=self.sm.active_model)
                self.sm.add_expt_data(new_expt_data)
                self._restore_point = self._backup_expt(new_expt_data)
            self.sm.notify_listeners("data_imported")
        else:
            ui.notify("No raw data selected to prepare data model from.", type="negative")

    def prompt_overwrite_or_rename(self, active_expt, has_fits, has_mcmc, has_model_work):
        with ui.dialog() as dialog, ui.card().classes("p-4"):
            ui.label("Existing Work Detected").classes("text-lg font-bold")
            
            msg = f"The active data model '{active_expt.name}' has existing work associated with it"
            reasons = []
            if has_model_work:
                reasons.append("data model configuration")
            if has_fits:
                reasons.append("dependent fit results")
            if has_mcmc:
                reasons.append("MCMC simulation results")
            msg += " (" + ", ".join(reasons) + ")."
            
            ui.label(msg).classes("text-sm text-gray-700 mb-2")
            
            if has_fits or has_mcmc:
                ui.label(
                    "WARNING: Overwriting this data model will PERMANENTLY delete all dependent fits and MCMC simulations."
                ).classes("text-sm text-red-600 font-semibold mb-4")
            
            with ui.row().classes("justify-end gap-2 w-full"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                
                # Rename / Create New button
                def on_rename():
                    dialog.close()
                    self.prepare_data_model_rename(active_expt)
                ui.button("Rename (Create New)", on_click=on_rename).props("outline color=primary")
                
                # Overwrite button
                def on_overwrite():
                    dialog.close()
                    self.prepare_data_model_overwrite(active_expt, delete_dependents=True)
                ui.button("Overwrite", on_click=on_overwrite).props("unelevated color=negative")

    def prepare_data_model_overwrite(self, active_expt, delete_dependents=True):
        # Auto-deselect unassigned columns in place
        for col in active_expt.data.columns:
            col_details = active_expt.col_details.get(col, {})
            is_component = col.startswith("[") and col.endswith("]")
            has_assignment = (col_details.get("depindep") in ["dep", "indep"]) and (
                col_details.get("dtype") is not None
            )
            if not is_component and not has_assignment:
                if col in active_expt.selected_columns:
                    active_expt.selected_columns.remove(col)

        # In-place reconciliation
        active_expt.reconcile_matrices()

        if delete_dependents:
            # Delete dependent fits & mcmcs
            to_delete = []
            for fit in list(self.sm.fits.values()):
                if fit.expt_data_id == active_expt.id:
                    to_delete.append(fit)
            for mcmc in list(self.sm.mcmcs.values()):
                if mcmc.expt_data_id == active_expt.id:
                    to_delete.append(mcmc)
            
            for obj in to_delete:
                self.sm.delete_object(obj)

        # Update restore point to current reconciled state
        self._restore_point = self._backup_expt(active_expt)
        
        self._load_expt_data_col_details()
        self._load_data_to_table()
        ui.notify(f"Data model '{active_expt.name}' updated and reconciled.", type="positive")

    def prepare_data_model_rename(self, active_expt):
        import numpy as np
        from dataclasses import asdict
        from ..classes import ChemicalShiftParam

        # 1. Clone the current mutated active_expt to create a new version
        existing_names = [ed.name for ed in self.sm.expt_datas.values()]
        new_name = self.selector.get_next_version_name(self._restore_point.name, existing_names)
        target = self.selector._clone_expt_data(active_expt, new_name)
        
        # 2. Seed target's old matrix column associations from the restore point
        target._matrix_columns = list(self._restore_point.selected_columns)
        if self._restore_point.integ_to_spec is not None:
            target._matrix_integ_columns = list(self._restore_point.selected_columns)
        
        fast_ex_cols = []
        if self._restore_point.col_details:
            for name, col in self._restore_point.col_details.items():
                if col.get("dtype") is None:
                    continue
                dtype_key = str(col.get("dtype", "")).lower()
                if col.get("depindep") == "dep" and ("delta" in dtype_key or "ppm" in dtype_key or "shift" in dtype_key):
                    fast_ex_cols.append(name)
        target._matrix_fast_ex_columns = fast_ex_cols

        # Auto-deselect unassigned columns in place on the clone
        for col in target.data.columns:
            col_details = target.col_details.get(col, {})
            is_component = col.startswith("[") and col.endswith("]")
            has_assignment = (col_details.get("depindep") in ["dep", "indep"]) and (
                col_details.get("dtype") is not None
            )
            if not is_component and not has_assignment:
                if col in target.selected_columns:
                    target.selected_columns.remove(col)

        # 3. Reconcile the new clone
        target.reconcile_matrices()
        
        # 4. Restore the original active_expt back to the restore point
        active_expt.selected_columns = list(self._restore_point.selected_columns)
        active_expt.col_details = {k: dict(v) for k, v in self._restore_point.col_details.items()}
        active_expt.col_to_comp = np.copy(self._restore_point.col_to_comp) if isinstance(self._restore_point.col_to_comp, np.ndarray) else self._restore_point.col_to_comp
        active_expt.integ_to_spec = np.copy(self._restore_point.integ_to_spec) if isinstance(self._restore_point.integ_to_spec, np.ndarray) else self._restore_point.integ_to_spec
        active_expt.delta_to_spec = np.copy(self._restore_point.delta_to_spec) if isinstance(self._restore_point.delta_to_spec, np.ndarray) else self._restore_point.delta_to_spec
        active_expt.limiting_shifts = {k: ChemicalShiftParam(**asdict(v)) for k, v in self._restore_point.limiting_shifts.items()}
        
        # 5. Add the clone to StateManager (becomes active, reconciles active ID, notify context changed)
        self.sm.add_expt_data(target)
        self._restore_point = self._backup_expt(target)
        self.sm.notify_listeners("active_context_changed")
        self.sm.notify_listeners("data_imported")
        
        ui.notify(f"New data model version '{new_name}' prepared. Original version preserved.", type="positive")

    async def load_exptdata(self):
        try:
            with ui.dialog() as dialog, ui.card():
                ui.label("Load experimental data file")
                upload_box = ui.upload(label="Choose file", auto_upload=True).props('accept=".csv, .xlsx, .xls"')
                ui.button("Cancel", on_click=lambda: dialog.submit("cancel"))

                def on_upload_complete(e: UploadEventArguments):
                    dialog.submit(e)  # Store result for later

                upload_box.on_upload(on_upload_complete)

            result = await dialog
            if isinstance(result, str) and result == "cancel":
                ui.notify("Experimental data loading cancelled", type="info")
                return
            elif isinstance(result, UploadEventArguments):
                data = pd.DataFrame()  # Initialize an empty DataFrame
                if result.file.name.endswith(".xlsx") or result.file.name.endswith(".xls"):
                    # If the file is an Excel file, read it into a DataFrame
                    file_content = await result.file.read()
                    data = pd.read_excel(io.BytesIO(file_content))

                elif result.file.name.endswith(".csv"):
                    # If the file is a CSV file, read it into a DataFrame
                    file_content = await result.file.text(encoding="utf-8")
                    data = pd.read_csv(io.StringIO(file_content))

                name = result.file.name
                # if result.name is already in the list of expt_datas, append a number to the name
                if any(ed.name == name for ed in self.sm.expt_datas.values()):
                    count = 1
                    while any(ed.name == f"{name}_({count})" for ed in self.sm.expt_datas.values()):
                        count += 1
                    name = f"{name}_({count})"

                rd = RawData(filename=name, data=data)
                self.sm.add_raw_data(rd)  # Add raw data to the state manager
                self.sm.add_expt_data(
                    ExptData(name=name, init_raw_data=rd, init_model=self.sm.active_model)
                )  # Load CSV data into a DataFrame

                # self.sm.expt_data.col_details = {c: {'depindep': None} for i,c in enumerate(self.sm.expt_data.data.columns)}
                ui.notify("Experimental data loaded successfully", type="info")
                self.sm.notify_listeners("data_imported")
            else:
                ui.notify("No file uploaded or unsupported file type", type="negative")
                return
        except Exception as e:
            print(f"Error loading data: {str(e)}")
            ui.notify("Failed to load data", type="negative")

    def _load_data_to_table(self, e=None):
        """Load the experimental data into the table."""
        self.expt_data_table_block.clear()
        if (
            self.sm.active_expt_data_id is not None
            and self.sm.active_expt_data.data is not None
            and not self.sm.active_expt_data.data.empty
        ):
            with self.expt_data_table_block:
                if not self.sm.active_expt_data.data.empty:
                    ui.label("Experimental Data:")
                    with (
                        ui.element("div")
                        .classes("w-full max-h-[30rem] overflow-y-scroll")
                        .style("scrollbar-gutter: stable;")
                    ):
                        # Show selected data in the table if column selection is active
                        data_to_display = self.sm.active_expt_data.selected_data
                        if data_to_display.empty:
                            data_to_display = self.sm.active_expt_data.data  # Fallback to all data if no selection

                        self.expt_dataTable = (
                            ui.table.from_pandas(data_to_display)
                            .classes("w-full")
                            .props('dense hide-bottom :pagination="{rowsPerPage: 0}"')
                            .mark("expt-data-table")
                        )
                else:
                    ui.label("No experimental data loaded.")
            self._load_expt_data_col_details()
            self.preview_graph.clear_graph()
            # Show only selected data in the graph preview
            selected_data_to_show = self.sm.active_expt_data.selected_data
            if not selected_data_to_show.empty:
                self.preview_graph.add_graph_lines(
                    selected_data_to_show,
                    run_name="Expt (selected)",
                    run_id=str(self.sm.active_expt_data_id),
                    scatter="markers",
                )
            self.preview_graph.update_graph()
        else:  # i.e. there is no data, we have deleted the last data
            self.expt_data_col_block.clear()
            self.preview_graph.clear_graph()
            self.preview_graph.update_graph()

    def _load_expt_data_col_details(self):
        self.expt_data_col_block.clear()
        # Clear UI element lists to prevent stale references
        self.dep_indep_dropdowns.clear()
        self.dep_indep_labels.clear()
        self.ignore_checkboxes.clear()
        self.dtype_labels.clear()
        self.dtype_dropdowns.clear()

        # Update restore point if active context has changed
        active_expt = self.sm.active_expt_data_or_none
        if active_expt is not None:
            if not hasattr(self, "_restore_point") or self._restore_point is None or self._restore_point.id != active_expt.id:
                self._restore_point = self._backup_expt(active_expt)

        with self.expt_data_col_block:
            if not self.sm.active_expt_data.data.empty:
                ui.label("Experimental Data Columns:")
                # populate column details dict
                # {col: {'depindep': None, ...}}

                # Ensure selected_columns is initialized once before creating UI
                if not self.sm.active_expt_data.selected_columns:
                    self.sm.active_expt_data.selected_columns = self.sm.active_expt_data.data.columns.tolist()

                for col in self.sm.active_expt_data.data.columns:  # Show all original columns
                    with ui.card() as card:
                        with ui.row().classes("items-center gap-2"):
                            # Column name label
                            label = ui.label(col).classes("text-sm font-semibold")
                            self.dep_indep_labels.append(label)

                            # "Include this column" checkbox
                            is_selected = col in self.sm.active_expt_data.selected_columns
                            include_cb = ui.checkbox("Include this column", value=is_selected)
                            self.ignore_checkboxes.append(include_cb)  # Reuse existing list for simplicity

                        # Dep/Indep radio buttons
                        with ui.row().classes("items-center gap-2"):
                            dep_indep_radio = (
                                ui.radio({"indep": "Independent variable", "dep": "Dependent variable"})
                                .props("inline")
                                .bind_value(self.sm.active_expt_data.col_details[col], "depindep")
                            )
                            self.dep_indep_dropdowns.append(dep_indep_radio)

                        # Data type dropdown
                        with ui.row().classes("items-center gap-2"):
                            dtype_label = ui.label("Data type:").classes("text-sm").props("inline")
                            self.dtype_labels.append(dtype_label)

                            opts = {k: v.name for k, v in self.sm._expt_dtypes.items()}
                            dtype_select = (
                                ui.select(opts, label="Data type")
                                .props("inline")
                                .bind_value(self.sm.active_expt_data.col_details[col], "dtype")
                            )
                            dtype_select.classes("w-40")
                            self.dtype_dropdowns.append(dtype_select)

                        # Set up column selection functionality
                        def setup_selection_behavior(card, dep_radio, dtype_sel, dtype_lbl, include_checkbox, col_name):
                            def update_selection_state(notify_listeners=True):
                                is_selected = include_checkbox.value
                                if is_selected:
                                    # Add to selected columns if not already there
                                    if col_name not in self.sm.active_expt_data.selected_columns:
                                        self.sm.active_expt_data.selected_columns.append(col_name)
                                    # Enable controls
                                    card.classes(remove="opacity-50")
                                    dep_radio.set_enabled(True)
                                    dtype_sel.set_enabled(True)
                                else:
                                    # Remove from selected columns
                                    if col_name in self.sm.active_expt_data.selected_columns:
                                        self.sm.active_expt_data.selected_columns.remove(col_name)
                                    # Grey out and clear other controls
                                    card.classes("opacity-50")
                                    dep_radio.set_enabled(False)
                                    dtype_sel.set_enabled(False)
                                    # Clear assignments when deselected
                                    self.sm.active_expt_data.col_details[col_name]["depindep"] = None
                                    self.sm.active_expt_data.col_details[col_name]["dtype"] = None

                                # Only notify listeners if not during initial setup
                                if notify_listeners:
                                    self.sm.notify_listeners("expt_data_columns_changed")

                            # Update state when checkbox changes (with notification)
                            include_checkbox.on_value_change(lambda: update_selection_state(True))
                            # Set initial state without triggering events
                            update_selection_state(False)

                        setup_selection_behavior(card, dep_indep_radio, dtype_select, dtype_label, include_cb, col)

                with ui.row():
                    ui.button("Add new data type", on_click=self.add_new_expt_data_type).props(
                        "unelevated color=primary"
                    ).classes("q-mx-xs")
            else:
                ui.label("No columns available in experimental data.")

    async def add_new_expt_data_type(self):
        """Add a new experimental data type."""
        with ui.dialog() as dialog, ui.card():
            ui.label("Add New Experimental Data Type")
            name_input = ui.input("Name", placeholder="Enter data type name").props("clearable")
            with ui.row().classes("items-center gap-2"):
                ui.label("Measurement Method")
                meas_input = (
                    ui.select(
                        label="Measurement Method",
                        options={
                            "grav_vol": "Grav/volumetric",
                            "nmr_integ": "NMR integration",
                            "nmr_ppm": "NMR chemical shift",
                            "uv_abs": "UV-vis",
                            "fluorescence": "Fluorescence",
                        },
                    )
                    .props("clearable")
                    .on_value_change(lambda e: method_changed(e.value))
                    .classes("w-40")
                )

            with ui.row().classes("items-center gap-2"):
                ui.label("Units")
                units_input = (
                    ui.select(label="Units", options=["ppm", "M", "mM", "uM", "nM", "absorbance", "intensity"])
                    .props("clearable")
                    .classes("w-15")
                )

            variance_input = (
                ui.number("Variance", placeholder="Enter variance", min=1e-20)
                .props("clearable")
                .tooltip("Give the variance in the data, using the same units as the measurements. Default: 0.005")
            )

            def method_changed(value):
                if value == "nmr_ppm":
                    units_input.value = "ppm"
                elif value in ["grav_vol", "nmr_integ"]:
                    units_input.value = "M"
                elif value == "uv_abs":
                    units_input.value = "absorbance"
                elif value == "fluorescence":
                    units_input.value = "intensity"

            def on_submit():
                if name_input.value and meas_input.value and units_input.value:
                    lnsigma_centre = float(math.log(variance_input.value)) if variance_input.value else -5
                    lnsigma = (lnsigma_centre - 3, lnsigma_centre, lnsigma_centre + 3)
                    new_dtype = ExptDataType(
                        name=name_input.value,
                        init_meas=meas_input.value,
                        units=units_input.value,
                        lnsigma=lnsigma[1],
                        lnsigma_min=lnsigma[0],
                        lnsigma_max=lnsigma[2],
                    )
                    try:
                        self.sm.add_expt_data_type(new_dtype)
                    except ValueError as e:
                        ui.notify(str(e), type="negative")
                    dialog.submit(True)
                else:
                    ui.notify("Please fill in all fields.", type="negative")

            ui.button("Submit", on_click=on_submit).props("unelevated color=primary")
            ui.button("Cancel", on_click=lambda: dialog.close()).props("unelevated color=secondary")
        result = await dialog
        if result:
            ui.notify(f"New experimental data type '{name_input.value}' added.", type="positive")
            self._load_expt_data_col_details()


