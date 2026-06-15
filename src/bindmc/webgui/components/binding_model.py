from .base import BaseComponent
from nicegui import ui, binding
from ..utils import (
    get_components_from_species,
)
from ..state.statemanager import StateManager


class BindingModelPanel(BaseComponent):
    def __init__(self, state_manager: StateManager, mode="sim"):
        self.mode = mode
        super().__init__(state_manager)
        self.generate_eq_const_rows()

    def setup_bindings(self):
        """Set up data bindings and listeners."""

        self.sm.add_listener("model_changed", self.generate_eq_const_rows)
        self.sm.add_listener("model_changed", self.generate_models_dropdown)
        self.sm.add_listener("model_changed", self.refresh_ui_bindings)

    def refresh_ui_bindings(self, e=None):
        """Refresh UI bindings after model changes."""
        # Check if UI elements exist before trying to bind them
        if not hasattr(self, "model_name_inp") or self.model_name_inp is None:
            return

        binding.remove(
            [
                self.model_name_inp,
                self.eqn_inp,
                self.model_dropdown_button,
                self.modeleq_mat,
                self.modelComp,
                self.modelSpec,
            ]
        )

        self.model_name_inp.bind_text_from(self.sm.active_model, "name")
        self.eqn_inp.bind_value(self.sm.active_model, "eq_str")
        self.model_dropdown_button.bind_text_from(self.sm.active_model, "name")
        if len(self.sm.models) > 1 or len(self.sm.active_model.eq_mat_str) > 1:
            self.modelData.set_visibility(True)
            self.modeleq_mat.bind_value_from(self.sm.active_model, "eq_mat_str")
            self.modelComp.bind_value_from(self.sm.active_model, "component_names")
            self.modelSpec.bind_value_from(self.sm.active_model, "species")
        else:
            self.modelData.set_visibility(False)

        # if self.sm.active_model_id not in self.sm.default_model_ids:
        #     self.edit_name_btn.props("flat").classes("ml-2").tooltip("Rename model").on('click', self.show_rename_dialog)
        # else:
        #     self.edit_name_btn.props("flat").classes("ml-2").tooltip("Cannot rename default model")

    def show_model_data(self, e):
        """Show the model data output area when a model is parsed."""
        self.modelData.set_visibility(True)  # Show the model data output area

    def setup_nicegui(self):
        mode = self.mode
        self.container = ui.column().classes("w-full")

        with self.container:
            with ui.row().classes("w-full"):
                self.model_dropdown_button = (
                    ui.dropdown_button("Choose model", auto_close=True)
                    .bind_text_from(self.sm.active_model, "name")
                    .classes("mb-5")
                )
                self.generate_models_dropdown()
                ui.button("Add New Model", on_click=lambda e: self.add_new_model()).classes("mb-5")

        with ui.row().classes("w-full mb-4"):
            with ui.row().classes("w-full items-center"):
                ui.label("Model Name:").style("font-weight: bold")

                self.model_name_inp = (
                    ui.label("Model Name")
                    .bind_text_from(self.sm.active_model, "name")
                    .tooltip(
                        "This name will appear in the legends of any figures. Make it descriptive but short! You might mention key details about the model."
                    )
                )
                # if self.sm.active_model_id not in self.sm.default_model_ids:
                #     self.edit_name_btn = ui.button(icon="edit", on_click=self.show_rename_dialog).props("flat").classes("ml-2").tooltip("Rename model")
                # else:
                #     self.edit_name_btn = ui.button(icon="edit_off").props("flat").classes("ml-2").tooltip("Cannot rename default model")

        self.eqn_inp = (
            ui.textarea("Equilibrium Equations", placeholder="H+G<=>HG")
            .bind_value(self.sm.active_model, "eq_str")
            .classes("w-full mb-4")
            .tooltip("Use the format H+G=HG. Separate equations with semicolons or new lines.")
            .props("clearable rows=2 autogrow")
            .mark("eq-input")
        )

        ui.button("Parse Equations", on_click=self.sm.parse_equations).classes("mb-4")

        self.eqConstRows = ui.row().classes("w-full")
        with self.eqConstRows:
            ui.label("Equilibrium Constants:")
            self.logKchk = (
                ui.checkbox("Use log scale for constants", value=True).classes("mb-2").mark("log-scale-checkbox")
            )  # Checkbox to toggle log scale
            self.logKchk.set_enabled(False)
            if len(self.sm.active_model.binding_constants) > 0:
                self.generate_eq_const_rows(
                    mode
                )  # Generate equilibrium constants input rows if binding constants exist
            else:
                self.eqConstRows.set_visibility(False)  # Placeholder for equilibrium constants input

        self.modelData = ui.element("div").mark("model-setup-output")  # Placeholder for model setup output
        self.advDetails = ui.expansion("Advanced model details")
        # if the model already exists, show the constants/etc block
        if len(self.sm.models) > 1 or len(self.sm.active_model.eq_mat_str) > 1:
            self.modelData.set_visibility(True)  # Initially hidden
        else:
            self.modelData.set_visibility(False)  # Initially hidden

        with self.modelData:
            with self.advDetails:
                self.modeleq_mat = (
                    ui.textarea("Equation matrix")
                    .props("rows=1 autogrow")
                    .classes("w-full mb-4")
                    .bind_value(self.sm.active_model, "eq_mat_str")
                    .mark("eq-matrix-output")
                )
                self.modelComp = (
                    ui.input("Components", value="")
                    .classes("w-full mb-4")
                    .mark("components-output")
                    .bind_value(self.sm.active_model, "component_names")
                )
                self.modelSpec = (
                    ui.input("Species", value="")
                    .classes("w-full mb-4")
                    .mark("species-output")
                    .bind_value(self.sm.active_model, "species")
                )

                self.modeleq_mat.ignores_events_when_disabled = False
                self.modeleq_mat.disable()
                self.modelComp.ignores_events_when_disabled = False
                self.modelComp.disable()
                self.modelSpec.ignores_events_when_disabled = False
                self.modelSpec.disable()

    def generate_models_dropdown(self, e=None):
        """Generate the dropdown for model selection."""
        self.model_dropdown_button.clear()
        with self.model_dropdown_button:
            self.model_dropdown_rows = []
            for i, m in enumerate(self.sm.models.values()):
                with ui.row().classes("p-1 items-center justify-between w-full no-wrap") as x:
                    self.model_dropdown_rows.append(x)
                    with ui.item(on_click=lambda m=m: self.load_model(m)).classes(
                        "flex-grow min-w-0 flex items-center"
                    ):
                        ui.item_label().bind_text(m, "name").classes("leading-none")

                    if m.id not in self.sm.default_model_ids:  # default model IDs
                        ui.icon("delete").on("click", lambda m=m: self.delete_model(m)).classes(
                            "cursor-pointer text-red-600 flex-shrink-0 self-center"
                        ).tooltip("Delete model")
                        ui.icon("edit").on("click", lambda m=m: self.show_rename_dialog(m)).classes(
                            "cursor-pointer flex-shrink-0 self-center"
                        ).tooltip("Rename model")
                    else:
                        ui.icon("lock").classes("text-gray-600 flex-shrink-0 self-center").tooltip("Built-in model")
                        ui.icon("edit_off").classes("text-gray-600 flex-shrink-0 self-center").tooltip(
                            "Cannot rename default model"
                        )

    #   if self.sm.active_model_id not in self.sm.default_model_ids:
    #                 self.edit_name_btn = ui.button(icon="edit", on_click=self.show_rename_dialog).props("flat").classes("ml-2").tooltip("Rename model")
    #             else:
    #                 self.edit_name_btn = ui.button(icon="edit_off").props("flat").classes("ml-2").tooltip("Cannot rename default model")
    def delete_model(self, m):
        self.sm.delete_model(m)

    async def add_new_model(self):
        async def show_name_dialog():
            with ui.dialog() as dialog, ui.card():
                ui.label("Enter name for new model:")
                name_input = ui.input("Model name", placeholder="Enter model name")
                with ui.row():
                    ui.button("Cancel", on_click=dialog.close)
                    ui.button("Create", on_click=lambda: create_model_with_name(name_input.value))

            def create_model_with_name(name):
                def add_model():
                    self.sm.new_model(name.strip())
                    self.modelData.set_visibility(False)  # Hide the model data output area
                    self.eqConstRows.set_visibility(False)
                    self.sm.notify_listeners("model_changed")  # Notify listeners to update the UI
                    dialog.close()

                if name.strip():
                    if name.strip() in [m.name for m in self.sm.models.values()]:
                        with ui.dialog() as confirm_dialog, ui.card():
                            ui.label(f'A model named "{name.strip()}" already exists.')
                            ui.label("Would you like to overwrite it or choose a different name?")
                            with ui.row():
                                ui.button(
                                    "Choose Different Name",
                                    on_click=lambda: (confirm_dialog.close(), show_name_dialog()),
                                )
                                ui.button("Overwrite", on_click=lambda: add_model())
                        confirm_dialog.open()
                        return
                    else:
                        add_model()

            dialog.open()

        await show_name_dialog()

    async def show_rename_dialog(self, m):
        async def show_name_dialog():
            with ui.dialog() as dialog, ui.card():
                ui.label("Enter new name for model:")
                name_input = ui.input("Model name", placeholder="Enter model name", value=m.name)
                with ui.row():
                    ui.button("Cancel", on_click=dialog.close)
                    ui.button("Rename", on_click=lambda: rename_model_to(name_input.value))

            def rename_model_to(name):
                if name.strip() and name.strip() != m.name:
                    if name.strip() in [m.name for m in self.sm.models.values()]:
                        with ui.dialog() as confirm_dialog, ui.card():
                            ui.label(f'A model named "{name.strip()}" already exists.')
                            ui.label("Please choose a different name.")
                            with ui.row():
                                ui.button("OK", on_click=confirm_dialog.close)
                        confirm_dialog.open()
                        return
                    m.name = name.strip()
                    self.sm.notify_listeners("model_changed")  # Notify listeners to update the UI
                dialog.close()

            dialog.open()

        await show_name_dialog()

    def load_model(self, m):
        """Load an existing model and update the UI accordingly."""
        self.sm.active_model_id = m.id
        self.sm.notify_listeners("model_changed")

    def generate_eq_const_rows(self, mode="sim"):
        """Generate the equilibrium constants input rows."""
        # Re-generate equilibrium constants rows
        if len(self.sm.active_model.binding_constants) < 1:
            if len(self.sm.active_model.species) > 0:
                # If no binding constants exist, create a new one
                self.sm.generate_binding_constants()
            else:
                self.eqConstRows.set_visibility(False)
                return

        self.eqConstRows.set_visibility(True)  # Show the equilibrium constants input area

        if self.logKchk.value is True:
            logtxt = r"\\log"
        else:
            logtxt = ""
        # populate binding constant definition section
        with self.eqConstRows as block:
            block.clear()  # Clear previous content
            # now set up binding constant blocks either with existing bound content or with the newly-instantiated
            # BindingConstant objects
            for i, b in enumerate(self.sm.active_model.binding_constants):
                # if species is has no existing BC, add one
                if b.isComp:
                    continue

                bspecies = b.species
                comps = get_components_from_species(bspecies)
                # i_in_full_list = self.sm.active_model.species.index(bspecies)

                # comps will have format [A,B,B] for A + 2B
                # so convert to a string like 'A + 2B'
                with ui.card().classes("mb-2 w-72").mark(f"eq-const-row-{i + 1}"):
                    with ui.row(align_items="center").classes("w-full justify-center"):
                        ui.label(
                            "{} ⇋ {}".format(
                                " + ".join(
                                    [
                                        f"{comps.count(c) if comps.count(c) > 1 else ''}{c}"
                                        for c in list(dict.fromkeys(comps))  # not using set() to preserve order
                                    ]
                                ),
                                bspecies,
                            )
                        ).props("inline").style("font-weight: bold; font-size: larger")
                    with ui.row().classes("items-center"):
                        ui.markdown(r"$$" + logtxt + "{K_{" + bspecies + "}} =$$", extras=["latex"]).classes(
                            "mb-2 text-center"
                        ).props("inline")
                        ui.number("logK", placeholder="Enter binding constant").classes("mb-2 w-20").mark(
                            f"logK-{bspecies}-val"
                        ).bind_value(self.sm.active_model.binding_constants[i], "logK").props("inline").on_value_change(
                            lambda e="k_changed": self.sm.notify_listeners(e)
                        )
                        ui.label("(log-units)")
                    if self.mode == "fit":
                        with ui.row().classes("items-center"):
                            ui.checkbox("Vary", value=True).bind_value(
                                self.sm.active_model.binding_constants[i], "vary"
                            )
                            min_input = (
                                ui.number("min", placeholder="Minimum value", value=2)
                                .bind_value(self.sm.active_model.binding_constants[i], "min")
                                .classes("w-15")
                            )
                            max_input = (
                                ui.number("max", placeholder="Maxmimum value", value=20)
                                .bind_value(self.sm.active_model.binding_constants[i], "max")
                                .classes("w-15")
                            )

                            # Bind enabled state to the vary checkbox
                            min_input.bind_enabled_from(self.sm.active_model.binding_constants[i], "vary")
                            max_input.bind_enabled_from(self.sm.active_model.binding_constants[i], "vary")
