import uuid as _uuid
from .base import BaseComponent
from nicegui import ui


class BindMCHeader(BaseComponent):
    # (label, dialog_title, collection_attr, active_id_attr, name_attr, reason)
    _ROW_CONFIGS = [
        ("Model:", "Select Model", "models", "active_model_id", "name", "header_model_select"),
        ("Raw data:", "Select Raw Data", "raw_datas", "active_raw_data_id", "filename", "header_raw_data_select"),
        ("Data model:", "Select Data Model", "expt_datas", "active_expt_data_id", "name", "header_data_model_select"),
        ("Fit:", "Select Fit", "fits", "active_fit_id", "name", "header_fit_select"),
    ]

    def setup_nicegui(self):
        ui.add_css("""
            .header-menu-btn { position: relative !important; overflow: visible !important; }
            .header-menu-btn.disabled::after {
                content: '';
                position: absolute;
                top: 50%; left: 10%; width: 80%; height: 2px;
                background: currentColor;
                transform: translateY(-50%) rotate(-45deg);
                pointer-events: none;
            }
        """)
        # Dialogs must be created outside the header element (page-level overlays)
        self._rows = []
        for cfg in self._ROW_CONFIGS:
            dialog, radio = self._build_dialog(cfg)
            self._rows.append({"cfg": cfg, "dialog": dialog, "radio": radio})

        with ui.header().classes("w-full flex justify-between items-center px-4 py-1 bg-black-600 text-white"):
            ui.label("BindMC GUI").classes("text-xl font-bold")
            with ui.column().classes("gap-0"):
                for row in self._rows:
                    with ui.row().classes("items-center gap-1 p-0 leading-none"):
                        row["menu_btn"] = (
                            ui.button(icon="menu", on_click=row["dialog"].open)
                            .props("flat round dense size=xs")
                            .classes("text-white opacity-60 header-menu-btn")
                        )
                        ui.label(row["cfg"][0]).classes("text-sm opacity-70")
                        row["value_label"] = ui.label("").classes("text-sm")
            self._apply_visibility_states()

            with ui.row():
                ui.button("New Project", on_click=self.sm.new_project).props("unelevated color=primary").classes(
                    "q-mx-xs"
                )
                ui.button("Open", on_click=self.sm.open_project).props("unelevated color=secondary").classes("q-mx-xs")
                ui.button("Save", on_click=self.sm.save_project).props("unelevated color=accent").classes("q-mx-xs")

    def _active_id_str(self, uid) -> str | None:
        return str(uid) if uid is not None else None

    def _get_options(self, cfg) -> dict:
        _, _, coll_attr, _, name_attr, _ = cfg
        return {str(o.id): getattr(o, name_attr) for o in getattr(self.sm, coll_attr).values()}

    def _get_active_str(self, cfg) -> str | None:
        return self._active_id_str(getattr(self.sm, cfg[3]))

    def _apply_visibility_states(self):
        for row in self._rows:
            _, _, coll_attr, active_attr, name_attr, _ = row["cfg"]
            coll = getattr(self.sm, coll_attr)
            obj = coll.get(getattr(self.sm, active_attr))
            row["value_label"].set_text(getattr(obj, name_attr) if obj is not None else "—")
            row["menu_btn"].set_enabled(len(coll) > 1)

    def _build_dialog(self, cfg):
        _, title, _, _, _, reason = cfg
        with ui.dialog() as dialog, ui.card().classes("min-w-64"):
            ui.label(title).classes("text-base font-bold q-mb-sm")
            radio = ui.radio(options=self._get_options(cfg), value=self._get_active_str(cfg))
            with ui.row().classes("justify-end gap-2 q-mt-sm"):
                ui.button("Cancel", on_click=lambda: self._cancel_dialog(dialog, radio, cfg)).props("flat")
                ui.button("OK", on_click=lambda: self._ok_dialog(dialog, radio, cfg)).props("unelevated color=primary")
        return dialog, radio

    def _ok_dialog(self, dialog, radio, cfg) -> None:
        _, _, _, active_attr, _, reason = cfg
        val = radio.value
        dialog.close()
        if val is not None:
            setattr(self.sm, active_attr, _uuid.UUID(val))
            self.sm.reconcile_active_context(reason)

    def _cancel_dialog(self, dialog, radio, cfg) -> None:
        radio.value = self._get_active_str(cfg)
        dialog.close()

    def setup_bindings(self):
        super().setup_bindings()
        for event in (
            "model_changed",
            "expt_data_changed",
            "fit_changed",
            "fit_completed",
            "fit_deleted",
            "sim_changed",
            "data_imported",
            "active_context_changed",
        ):
            self.sm.add_listener(event, self.refresh_ui_bindings)

    def refresh_ui_bindings(self, changes=None, *args):
        for row in self._rows:
            row["radio"].options = self._get_options(row["cfg"])
            row["radio"].value = self._get_active_str(row["cfg"])
        self._apply_visibility_states()

        if isinstance(changes, dict):
            _warn_attrs = {
                "_active_sim_id": "simulation",
                "_active_fit_id": "fit",
                "_active_expt_data_id": "data model",
                "_active_raw_data_id": "raw data",
            }
            for attr, label in _warn_attrs.items():
                entry = changes.get(attr)
                if entry and entry[0] is not None and entry[1] is None:
                    ui.notify(f"No {label} available for the selected context.", type="warning")
