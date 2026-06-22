import uuid
import re
from nicegui import ui
from .base import BaseComponent
from ..classes import ExptData, RawData


class DatasetSelector(BaseComponent):
    """Reusable dropdown selection and management component for RawData and ExptData."""

    def setup_nicegui(self):
        self.container = ui.column().classes("w-full gap-2 p-0 m-0")
        with self.container:
            # Raw Dataset dropdown
            with ui.row().classes("items-center gap-2 mb-2 no-wrap"):
                ui.label("Raw Data:").classes("text-sm font-semibold w-24")
                self.raw_data_dropdown_button = (
                    ui.dropdown_button("Choose raw dataset", auto_close=True)
                    .classes("w-80")
                )

            # Interpretation / Data Model dropdown
            with ui.row().classes("items-center gap-2 mb-4 no-wrap"):
                ui.label("Data Model:").classes("text-sm font-semibold w-24")
                self.expt_data_dropdown_button = (
                    ui.dropdown_button("Choose data model", auto_close=True)
                    .classes("w-80")
                )
                self.rename_expt_button = (
                    ui.button(icon="edit", on_click=self.rename_active_expt)
                    .props("flat dense")
                    .classes("q-px-sm")
                    .tooltip("Rename current data model")
                )
                self.duplicate_expt_button = (
                    ui.button(icon="content_copy", on_click=self.duplicate_active_expt)
                    .props("flat dense")
                    .classes("q-px-sm")
                    .tooltip("Duplicate current configuration")
                )
        self.update_dropdown_visibility()
        self.generate_dropdowns()

    def setup_bindings(self):
        super().setup_bindings()
        self.sm.add_listener("data_imported", self.generate_dropdowns)
        self.sm.add_listener("active_context_changed", self.generate_dropdowns)
        self.sm.add_listener("expt_data_columns_changed", self.generate_dropdowns)

    def update_dropdown_visibility(self):
        has_raw = len(self.sm.raw_datas) > 0
        has_expt = len(self.sm.expt_datas) > 0
        
        if hasattr(self, "raw_data_dropdown_button"):
            self.raw_data_dropdown_button.visible = has_raw
        if hasattr(self, "expt_data_dropdown_button"):
            self.expt_data_dropdown_button.visible = has_expt
        if hasattr(self, "rename_expt_button"):
            self.rename_expt_button.visible = has_expt
        if hasattr(self, "duplicate_expt_button"):
            self.duplicate_expt_button.visible = has_expt

    def generate_dropdowns(self, e=None):
        """Generate the dropdowns for selecting raw datasets and data models."""
        self.update_dropdown_visibility()
        
        if hasattr(self, "raw_data_dropdown_button"):
            self.raw_data_dropdown_button.clear()
            active_raw = self.sm.active_raw_data_or_none
            if active_raw is not None:
                self.raw_data_dropdown_button.set_text(active_raw.filename)
            else:
                self.raw_data_dropdown_button.set_text("Choose raw dataset")
                
            if len(self.sm.raw_datas) > 0:
                with self.raw_data_dropdown_button:
                    for raw in list(self.sm.raw_datas.values()):
                        ui.item(raw.filename, on_click=lambda e, raw=raw: self.load_raw_data(raw))

        if hasattr(self, "expt_data_dropdown_button"):
            self.expt_data_dropdown_button.clear()
            active_expt = self.sm.active_expt_data_or_none
            active_raw = self.sm.active_raw_data_or_none
            
            if active_expt is not None:
                self.expt_data_dropdown_button.set_text(active_expt.name)
            else:
                self.expt_data_dropdown_button.set_text("Choose data model")
                
            if active_raw is not None:
                # Filter interpretations to only those belonging to the active raw dataset
                matching_expts = [
                    expt for expt in self.sm.expt_datas.values()
                    if expt.raw_data_id == active_raw.id
                ]
                if matching_expts:
                    with self.expt_data_dropdown_button:
                        for expt in matching_expts:
                            with ui.row().classes("p-1 items-center justify-between w-full no-wrap"):
                                ui.item(expt.name, on_click=lambda e, expt=expt: self.load_expt_data(expt)).classes("flex-grow min-w-0")
                                ui.icon("delete").on("click", lambda e, expt=expt: self.delete_expt_data(expt)).classes(
                                    "cursor-pointer text-red-600 flex-shrink-0 self-center"
                                ).tooltip("Delete data model")

    def load_raw_data(self, raw):
        self.sm.active_raw_data_id = raw.id
        self.sm.reconcile_active_context(reason="load_raw_data", emit_events=True)
        self.sm.notify_listeners("active_context_changed")
        self.sm.notify_listeners("data_imported")

    def load_expt_data(self, expt):
        self.sm.active_expt_data_id = expt.id
        self.sm.active_raw_data_id = expt.raw_data_id
        
        active_fit = self.sm.active_fit_or_none
        if active_fit is None or active_fit.expt_data_id != expt.id:
            self.sm.active_fit_id = None
            for f in reversed(list(self.sm.fits.values())):
                if f.expt_data_id == expt.id:
                    self.sm.active_fit_id = f.id
                    break

        self.sm.reconcile_active_context(reason="load_expt_data", emit_events=True)
        self.sm.notify_listeners("active_context_changed")
        self.sm.notify_listeners("data_imported")

    def delete_expt_data(self, expt):
        self.sm.delete_expt_data(expt)
        self.sm.notify_listeners("data_imported")

    def get_next_version_name(self, base_name: str, existing_names: list[str]) -> str:
        """Return the next incremented version name for base_name."""
        match = re.search(r" v(\d+)$", base_name)
        if match:
            version = int(match.group(1))
            prefix = base_name[:match.start()]
        else:
            version = 1
            prefix = base_name
        
        new_version = version + 1
        candidate = f"{prefix} v{new_version}"
        while candidate in existing_names:
            new_version += 1
            candidate = f"{prefix} v{new_version}"
        return candidate

    def _clone_expt_data(self, old_expt: ExptData, new_name: str) -> ExptData:
        """Return a copy of old_expt with a new UUID and name, linked to the same model and raw data."""
        from ..classes import ChemicalShiftParam
        d = old_expt.to_dict()
        d["id"] = str(uuid.uuid4())
        d["name"] = new_name
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

    def duplicate_active_expt(self):
        active_expt = self.sm.active_expt_data_or_none
        if active_expt is not None:
            # Clone active_expt to create a new version
            existing_names = [ed.name for ed in self.sm.expt_datas.values()]
            new_name = self.get_next_version_name(active_expt.name, existing_names)
            target = self._clone_expt_data(active_expt, new_name)
            
            # Reconcile target matrices to align with its current columns
            target.reconcile_matrices()
            
            # Add to StateManager and set as active
            self.sm.add_expt_data(target)
            ui.notify(f"Configuration duplicated as '{new_name}'.", type="positive")
            self.sm.notify_listeners("data_imported")
        else:
            ui.notify("No active data model to duplicate.", type="warning")

    async def rename_active_expt(self):
        active_expt = self.sm.active_expt_data_or_none
        if active_expt is not None:
            with ui.dialog() as dialog, ui.card().classes("w-96"):
                ui.label("Rename Data Model").classes("font-semibold text-lg")
                name_input = ui.input("Data model name", value=active_expt.name).classes("w-full")
                with ui.row().classes("justify-end gap-2 mt-2"):
                    ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
                    ui.button("Rename", on_click=lambda: dialog.submit(name_input.value)).props("color=primary")
            result = await dialog
            if result is not None and result.strip() != "":
                new_name = result.strip()
                if new_name != active_expt.name:
                    active_expt.name = new_name
                    self.sm.save_to_storage()
                    ui.notify(f"Data model renamed to '{new_name}'.", type="positive")
                    self.sm.notify_listeners("active_context_changed")
                    self.sm.notify_listeners("data_imported")
        else:
            ui.notify("No active data model to rename.", type="warning")
