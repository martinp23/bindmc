import re
import uuid

from nicegui import ui
from nicegui.events import ClickEventArguments
import numpy as np

from .base import BaseComponent
from ..classes import ChemicalShiftParam, ExptData
from ..utils import _infer_simple_fast_exchange_topology

# def _default_analytical_shift_species(
#     eq_mat: np.ndarray, component_names: list[str], species_names: list[str], n_fast_ex_cols: int
# ) -> str | None:
#     """Return a default shift-expression species token for simple analytical fast exchange.

#     """
#     # if n_fast_ex_cols != 1:
#     #     return None
#     if _infer_simple_fast_exchange_topology(eq_mat, len(component_names)) is None:
#         return None
#     if len(component_names) < 1:
#         return None

#     default_species = f"{component_names[0]}_free"
#     if default_species in species_names:
#         return default_species
#     return species_names[0] if species_names else None


class DataModelPanel(BaseComponent):
    def setup_nicegui(self):
        self.container = ui.column().classes("w-full")

        with self.container:
            ui.label("Data model setup panel").classes("text-lg font-bold mb-4")

            self.data_model_inp = ui.input(
                "Data model name", placeholder="Enter data model name"
            ).classes("mb-5").props("clearable")

            ui.label("Columns").classes("text-md font-semibold mt-4 mb-2")
            self.dataModel_col_block = ui.element()

            ui.label("Component mapping").classes("text-md font-semibold mt-4 mb-2")
            self.dataModel_colComp_block = ui.element()

            self.slow_ex_label = ui.label("Species mapping (slow exchange)").classes("text-md font-semibold mt-4 mb-2")
            self.dataModel_specInteg_block = ui.element()

            self.fast_ex_label = ui.label("Species mapping (fast exchange)").classes("text-md font-semibold mt-4 mb-2")
            self.dataModel_specFastExchange_block = ui.element()

            self.data_model_apply = ui.button(
                "Apply Data Model", on_click=self.process_data_model
            )
            if len(self.sm.expt_datas) > 0:
                self._populate_blocks()


    def setup_bindings(self):
        super().setup_bindings()
        self.sm.add_listener("data_imported", self._populate_blocks)
        return

    def _populate_blocks(self):
        # add column chips to data model page

        nmr_fast_ex = False
        nmr_slow_ex = False

        # work out what we need
        if self.sm.active_expt_data_or_none is not None:
            self._gen_column_chips()
            self._gen_col_comp_block()
            for f in self.sm.active_expt_data.col_details.values():
                if f.get('dtype') is not None:
                    dtype = self.sm._expt_dtypes.get(f['dtype'])
                    if getattr(dtype, 'meas', None) == 'nmr_ppm' and f.get('depindep') == 'dep':
                        nmr_fast_ex = True
                        self._gen_spec_fast_exchange_block()
                    elif getattr(dtype, 'meas', None) == 'nmr_conc' and f.get('depindep') == 'dep':
                        nmr_slow_ex = True
                        self._gen_spec_integ_block()

        if not nmr_fast_ex:
            self.fast_ex_label.visible = False
            self.dataModel_specFastExchange_block.visible = False
        if not nmr_slow_ex:
            self.slow_ex_label.visible = False
            self.dataModel_specInteg_block.visible = False

        if self.sm.active_expt_data_or_none is not None:
            self.data_model_inp.value = self.sm.active_expt_data.name[:] # copy it


    def _gen_column_chips(self):
        """Generate the column chips for the data model."""
        self.dataModel_col_block.clear()
        active_expt = self.sm.active_expt_data_or_none
        if active_expt is not None:
            with self.dataModel_col_block:
                with ui.row().classes("gap-1"):
                    for col in active_expt.columns:
                        text = col
                        ui.chip(
                            text,
                            color="blue",
                            on_click=lambda h=text: self.insert_term(f'[{h}]'),
                        )

    def _gen_col_comp_block(self):
        """Generate the column to component mapping block."""
        # add col to comp boxes
        self.dataModel_colComp_block.clear()

        active_expt = self.sm.active_expt_data_or_none
        if active_expt is None:
            return # stop now if there is no active data

        with self.dataModel_colComp_block:
            self.compConcInps = []
            for i, comp in enumerate(self.sm.active_model.components):
                with ui.row().classes("items-center"):
                    ui.label(f"Component [{comp.name}]_tot:")
                    self.compConcInps.append(
                        ui.input().classes("flex-1").props("clearable")
                    )
                    self.compConcInps[-1].on(
                        "blur", lambda c=self.compConcInps[-1]: self.set_focus(c)
                    )
                    if hasattr(active_expt, "col_to_comp") and len(active_expt.col_to_comp) > 0:
                        self.compConcInps[-1].value = self.vec_to_conc_expression(
                            active_expt.col_to_comp[i], active_expt.columns
                        )


    def _gen_spec_integ_block(self):
        """Generate the species integration block."""
        self.dataModel_specInteg_block.clear()

        active_expt = self.sm.active_expt_data_or_none
        if active_expt is None:
            return # stop now if there is no active data

        with self.dataModel_specInteg_block:
            self.spec_integ_inps: dict[str,ui.input] = {}
            for i, spec in enumerate(self.sm.species):
                with ui.row().classes("items-center"):
                    ui.label(f"Species conc. [{spec}]_free:")
                    self.spec_integ_inps[spec]=  ui.input().classes("flex-1").props("clearable")
                    
                    self.spec_integ_inps[spec].on(
                        "blur", lambda c=self.spec_integ_inps[spec]: self.set_focus(c)
                    )
                    b = ui.checkbox("Enabled", value=True)
                    self.spec_integ_inps[spec].bind_enabled_from(b, "value")
                    if hasattr(active_expt, 'integ_to_spec') and active_expt.integ_to_spec is not None and len(active_expt.integ_to_spec) > 0:
                        self.spec_integ_inps[spec].value = self.vec_to_conc_expression(
                            active_expt.integ_to_spec[i], active_expt.columns
                        )
                        if self.spec_integ_inps[spec].value == "":
                            b.value = False
                    else:
                        b.value = False

    def _gen_spec_fast_exchange_block(self):
        """Generate the species fast exchange block.

        For each column mapped to NMR chemical shifts (nmr_ppm) and marked as dependent,
        create an input row to enter the concentration expression (specDeltaInps). When a
        non-empty/valid expression is provided, create a parameter block immediately below
        the input with: Chemical shift (number), Fixed (checkbox), Minimum (number), Maximum (number).

        If Fixed is checked, Minimum/Maximum are disabled.
        """
        self.dataModel_specFastExchange_block.clear()
        active_expt = self.sm.active_expt_data_or_none
        if active_expt is None:
            self.fast_ex_label.visible = False
            self.dataModel_specFastExchange_block.visible = False
            return # stop now if there is no active data
        active_expt.is_analytical_fast_ex = False

        # find columns that are NMR chemical-shift dependent variables
        fast_ex_list = []
        dep_list = []
        if active_expt.col_details:
            for name, col in active_expt.col_details.items():
                if col.get('dtype') is None:
                    continue
                dtype = self.sm._expt_dtypes.get(col['dtype'])
                if dtype and getattr(dtype, 'meas', None) == 'nmr_ppm' and col.get('depindep') == 'dep':
                    fast_ex_list.append(name)
                if col.get('depindep') == 'dep':
                    dep_list.append(name)

        if not fast_ex_list:
            self.fast_ex_label.visible = False
            self.dataModel_specFastExchange_block.visible = False
            return

        # if dep_list contains columns that are not in fast_ex_list, warn the user that those dependent variables will be ignored in the fast-exchange processing
        extra_deps = [col for col in dep_list if col not in fast_ex_list]
        simple_model= _infer_simple_fast_exchange_topology(self.sm.active_model.eq_mat, len(self.sm.active_model.component_names))
        if simple_model is not None:
            if len(extra_deps) == 0:
                self.fast_ex_label.visible = False
                with self.dataModel_specFastExchange_block:
                    ui.label(f"This is a simple model ({simple_model[0]} binding) with only fast-exchange observables, so we will use standard binding isotherms with analytical solutions.").classes("text-xs text-gray-600")
                    self.sm.active_expt_data.is_analytical_fast_ex = True
                #return
            else:
                with self.dataModel_specFastExchange_block:
                    ui.label(f"This is a simple model ({simple_model}) but there are dependent variables ({', '.join(extra_deps)}) that are not recognized as fast-exchange observables, so a full numerical fit will be attempted. If you want to use the quicker analytical method, delete the extra observables data.").classes("text-xs text-gray-600")

        self.fast_ex_label.visible = True
        self.dataModel_specFastExchange_block.visible = True

        # reset lists and UI block
        self.specDeltaInps = []
        self.specDeltaCards = []
        self.fast_ex_chem_shift_blocks = []
        self.fast_ex_chem_shift_params = []
    # map per spec-delta index -> { species_name: {card, shift_num, fixed_cb, min_num, max_num} }
        self.fast_ex_chem_shift_map = []
        

        # keep the fast-exchange column names for later processing and bindings
        self.fast_ex_list_names = list(fast_ex_list)
        if len(extra_deps) > 0:
            with self.dataModel_specFastExchange_block:
                # species_list = [f'{x}_free' for x in self.sm.species]

                


                # default_shift_species = _default_analytical_shift_species(
                #     self.sm.active_model.eq_mat,
                #     list(self.sm.active_model.component_names),
                #     species_list,
                #     len(self.fast_ex_list_names),
                # )
                # if default_shift_species is not None:
                #     ui.label(
                #         f"Analytical model detected: defaulting fast-exchange expression to [{default_shift_species}] "
                #         "for this observable. You can edit it if needed."
                #     ).classes("text-xs text-gray-600")

                for i, shift in enumerate(self.fast_ex_list_names):
                        # card per chemical shift column
                        card = ui.card().classes('mb-2')
                        self.specDeltaCards.append(card)
                        with card:
                            ui.label(f'Fast exchange shift {i+1} ({shift})').classes('text-sm font-semibold')
                            with ui.row().classes('items-center'):
                                inp = ui.input().classes('flex-1').props('clearable')
                                self.specDeltaInps.append(inp)
                                # species chips row will be added below the input to allow quick insertion
                                with ui.row().classes('gap-1 mt-2'):
                                    for text in [f'{x}_free' for x in self.sm.species]:
                                        ui.chip(text, color='teal', on_click=lambda h=text: self._insert_species_into_fast_inp(h))
                                # placeholder checkbox to enable the input
                                en_cb = ui.checkbox('Enabled', value=True)
                                inp.bind_enabled_from(en_cb, 'value')
                                # placeholder param block element (initially empty/hidden)
                                pb = ui.element()
                                self.fast_ex_chem_shift_blocks.append(pb)
                                self.fast_ex_chem_shift_map.append({})
                                # store param dict for later
                                # self.fast_ex_chem_shift_params.append({'shift': None, 'fixed': False, 'min': None, 'max': None})

                                # bind blur handler to create/update parameter block
                                # use default args to capture current inp and index
                                # allow chips/clicks to insert into this input by remembering last focus
                                inp.on('focus', lambda e, widget=inp: self.set_focus(widget))
                                inp.on('click', lambda e, widget=inp: self.set_focus(widget))
                                # handle blur to create/update parameter sub-blocks
                                inp.on('blur', lambda e, idx=i, widget=inp: self._handle_spec_delta_blur(idx, widget))
                                # immediate change handler: reparse on every change
                                inp.on_value_change(lambda e, idx=i, widget=inp: self._handle_spec_delta_blur(idx, widget))

                                # if there is saved delta_to_spec data, populate the input
                                if hasattr(active_expt, 'delta_to_spec') and active_expt.delta_to_spec is not None and len(active_expt.delta_to_spec) > 0:
                                    delta_for_eqn = active_expt.delta_to_spec[i].copy()
                                    
                                    for ij,el in enumerate(delta_for_eqn):
                                        if np.isclose(el, 0):
                                            delta_for_eqn[ij] = 0
                                        else:
                                            if (f'{self.sm.species[ij]}_free',shift) in active_expt.limiting_shifts:
                                                s = active_expt.limiting_shifts[f'{self.sm.species[ij]}_free',shift]
                                                if s.value:
                                                    delta_for_eqn[ij] = delta_for_eqn[ij] / s.value
                                                else:
                                                    delta_for_eqn[ij] = 1

                                                #self.sm.active_expt_data.limiting_shifts[f'{self.sm.species[i]}_free',shift].value
                                    
                                    #delta_for_eqn[delta_for_eqn != 0] = 1

                                    value = self.vec_to_conc_expression(delta_for_eqn, [f'{x}_free' for x in self.sm.species])
                                    inp.value = value
                                    if value == '':
                                        en_cb.value = False
                                # elif default_shift_species is not None:
                                #     inp.value = f"[{default_shift_species}]"
                                #     # Build corresponding ChemicalShiftParam widgets immediately.
                                #     self._handle_spec_delta_blur(i, inp)


        # finished generating fast-exchange block

    def _handle_spec_delta_blur(self, fast_ex_idx, inp):
        """Called when a specDelta input loses focus. If it contains a valid concentration expression
        (non-zero vector), create or update the parameter UI block for that shift inside its card.
        """
        # defensive checks
        active_expt = self.sm.active_expt_data_or_none
        if active_expt is None:
            ui.notify("Experimental data object doesn't exist in handle_blur; stopping")
            return

        # For fast-exchange inputs, concentration expressions refer to model species, not columns
        species_list = [f'{x}_free' for x in self.sm.active_model.species]
        
        vec = self.conc_expression_to_vec(inp.value, species_list)

        # if expression is invalid or maps to no species -> remove/hide param block
        if vec is None or (isinstance(vec, (list, tuple, np.ndarray)) and np.all(np.isclose(vec, 0))):
            # clear/hide param block if present
            curr_block = self.fast_ex_chem_shift_blocks[fast_ex_idx]
            curr_block.clear()
            curr_block.visible = False
            # reset stored params
            if len(self.fast_ex_chem_shift_params)>0:
                del self.fast_ex_chem_shift_params[fast_ex_idx]
            #self.specDeltaParams[fast_ex_idx] = {'shift': None, 'fixed': False, 'min': None, 'max': None}
            return

        # ensure param block exists and is visible
        curr_block = self.fast_ex_chem_shift_blocks[fast_ex_idx]
        curr_block.visible = True

        # build per-species parameter sub-blocks but reuse widgets when possible
        nonzero_indices = [j for j, val in enumerate(vec) if not np.isclose(val, 0)]
        # map indices back to species names
        desired_species = [species_list[j] for j in nonzero_indices]

        # hide any widgets for species not present
        widget_map = self.fast_ex_chem_shift_map[fast_ex_idx]
        for existing_species in list(widget_map.keys()):
            if existing_species not in desired_species:
                widget_map[existing_species]['card'].visible = False
 

        # create or update widgets for desired species
        with curr_block:
            for spec_name in desired_species:

                # set up a ChemicalShiftParam instance keyed by (species, column)
                col_name = self.fast_ex_list_names[fast_ex_idx]
                k = (spec_name, col_name)
                cs_obj = active_expt.limiting_shifts.get(k)
                if not isinstance(cs_obj, ChemicalShiftParam):
                    # create with safe defaults
                    cs_obj = ChemicalShiftParam(species=spec_name, col=col_name, fixed=False)
                    active_expt.limiting_shifts[k] = cs_obj

                # reuse if exists
                w = widget_map.get(spec_name)
                if w is not None:
                    w['card'].visible = True
                else:
                    # create widgets and store references
                    card = ui.card().classes('q-pa-sm q-mb-sm')
                    with card:
                        ui.label(f'Species: {spec_name}').classes('text-sm font-semibold')
                        with ui.row().classes('items-center gap-2'):
                            shift_num = ui.number('Chemical shift').classes('w-40').props('clearable')
                            fixed_cb = ui.checkbox('Fixed', value=False)
                            min_num = ui.number('Minimum').classes('w-40').props('clearable')
                            max_num = ui.number('Maximum').classes('w-40').props('clearable')

                    w = {'card': card, 'shift_num': shift_num, 'fixed_cb': fixed_cb, 'min_num': min_num, 'max_num': max_num}
                    widget_map[spec_name] = w

                # two-way bind control values directly to the object
                w['shift_num'].bind_value(cs_obj, 'value')
                w['fixed_cb'].bind_value(cs_obj, 'fixed')
                w['min_num'].bind_value(cs_obj, '_min')
                w['max_num'].bind_value(cs_obj, '_max')

                # min/max enabled reflect inverted fixed
                w['min_num'].bind_enabled_from(cs_obj, 'fixed', backward=lambda v: not v)
                w['max_num'].bind_enabled_from(cs_obj, 'fixed', backward=lambda v: not v)


    def _clone_expt_data(self, old_expt: ExptData, new_name: str) -> ExptData:
        """Return a copy of old_expt with a new UUID and name, linked to the same model and raw data."""
        d = old_expt.to_dict()
        d['id'] = str(uuid.uuid4())
        d['name'] = new_name
        limiting_shifts_raw = d.pop('limiting_shifts', []) or []
        new_expt = ExptData(**d)
        new_expt.limiting_shifts = {}
        for cs in limiting_shifts_raw:
            csp = ChemicalShiftParam(**cs)
            key = (csp.species, csp.col)
            new_expt.limiting_shifts[key] = csp
        new_expt.find_and_link_model(self.sm.models)
        new_expt.find_and_link_raw_data(self.sm.raw_datas)
        return new_expt

    async def process_data_model(self):
        """Process the data model based on user input."""
        active_expt = self.sm.active_expt_data_or_none
        if active_expt is None:
            ui.notify("No active experimental data to process.", type="negative")
            return

        # If existing fits depend on this ExptData, require saving as a new one
        dependent_fits = [f for f in self.sm.fits.values() if f.expt_data_id == active_expt.id]
        new_name = self.data_model_inp.value  # default; overridden by dialog when cloning
        if dependent_fits:
            with ui.dialog() as dialog, ui.card().classes("w-96"):
                ui.label("Existing fits depend on this data model.").classes("font-semibold")
                ui.label("Save changes as a new data model to keep old fits valid:")
                name_input = ui.input("New data model name", value=f"{active_expt.name} v2").classes("w-full")
                with ui.row().classes("justify-end gap-2 mt-2"):
                    ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
                    ui.button("Save as new", on_click=lambda: dialog.submit(name_input.value)).props("color=primary")
            result = await dialog
            if result is None:
                ui.notify("Cancelled — data model unchanged.", type="info")
                return
            new_name = result
            target = self._clone_expt_data(active_expt, new_name)
        else:
            target = active_expt

        # make col_to_comp matrix
        col_to_comp = [self.conc_expression_to_vec(input.value, target.columns) for input in self.compConcInps]
        col_to_comp = np.array(col_to_comp)
        target.col_to_comp = col_to_comp
        target.name = new_name

        # generate integ_to_spec block
        # If there are no species inputs, set integ_to_spec to None

        if not hasattr(self, 'spec_integ_inps') or len(self.spec_integ_inps) == 0:
            target.integ_to_spec = None
        else:
            integ_to_spec = [self.conc_expression_to_vec(input.value, target.columns) if input.enabled else
                            np.zeros(len(target.columns)) for input in self.spec_integ_inps.values()]
            integ_to_spec = np.array(integ_to_spec)
            if integ_to_spec.size == 0 or np.all(np.isclose(integ_to_spec, 0)):
                target.integ_to_spec = None
            elif integ_to_spec.shape[0] != len(self.sm.species):
                raise ValueError("Integ_to_spec matrix shape does not match number of species.")
            else:
                target.integ_to_spec = integ_to_spec

        # If there is a fast-exchange block with enabled sections, save delta_to_spec as an object ndarray
        fast_exchange_vectors: list[np.ndarray] = []
        species_label_list: list[str] = []
        row_columns: list[str] = []
        if hasattr(self, 'specDeltaInps') and isinstance(self.specDeltaInps, list) and len(self.specDeltaInps) > 0:
            species_label_list = [f"{s}_free" for s in self.sm.species]
            for idx, input_widget in enumerate(self.specDeltaInps):
                if hasattr(input_widget, 'enabled') and input_widget.enabled and isinstance(input_widget.value, str) and input_widget.value.strip():
                    parsed_vector = self.conc_expression_to_vec(input_widget.value, species_label_list)
                    fast_exchange_vectors.append(parsed_vector)
                    if hasattr(self, 'fast_ex_list_names') and idx < len(self.fast_ex_list_names):
                        row_columns.append(self.fast_ex_list_names[idx])
        if fast_exchange_vectors:
            target.build_delta_to_spec(fast_exchange_vectors, species_label_list, row_columns=row_columns)
        else:
            target.delta_to_spec = None

        # Remove stale limiting_shifts entries
        for k in list(target.limiting_shifts.keys()):
            species, col_idx = k
            if species[:-5] not in self.sm.active_model.species or col_idx not in target.columns:
                del target.limiting_shifts[k]

        # Rebuild column mapping (reset first to avoid accumulation on re-apply)
        if hasattr(self, 'fast_ex_list_names') and len(self.fast_ex_list_names) > 0:
            target.column_mapping = []
            conc_cols = []
            delta_cols = []
            for i, col in enumerate(target.columns):
                if col in self.fast_ex_list_names:
                    delta_cols.append(i)
                else:
                    conc_cols.append(i)
            i = 0
            for col_idx in conc_cols:
                target.column_mapping.append((col_idx, i))
                i += 1
            for col_idx in delta_cols:
                target.column_mapping.append((col_idx, i))
                i += 1

        # Track simple analytical fast-exchange mode at save-time
        dep_cols = [
            name for name in target.columns
            if target.col_details.get(name, {}).get("depindep") == "dep"
        ]
        analytical_topology = _infer_simple_fast_exchange_topology(
            self.sm.active_model.eq_mat,
            len(self.sm.active_model.component_names),
        )
        target.is_analytical_fast_ex = False
        if analytical_topology is not None and dep_cols:
            all_dep_are_nmr = True
            for col in dep_cols:
                dtype_key = target.col_details.get(col, {}).get("dtype")
                dtype = self.sm._expt_dtypes.get(dtype_key) if dtype_key is not None else None
                if dtype is None or getattr(dtype, "meas", None) != "nmr_ppm":
                    all_dep_are_nmr = False
                    break
            if all_dep_are_nmr:
                target.is_analytical_fast_ex = True

        if target is not active_expt:
            self.sm.add_expt_data(target)  # sets as active, reconciles, emits expt events
            self.sm.active_fit_id = None   # deselect any auto-selected fit
            self.sm.notify_listeners("fit_changed")
            self.sm.notify_listeners("fits_loaded")
        self.sm.save_to_storage()
        self.sm.notify_listeners("data_model_processed")


    def conc_expression_to_vec(self,input_str,cols):
        """Takes a string like "+#[H]+2#[G]" or "+#[H]+2*#[G]"
         or any of the below:
          [[H]]+[[G]]
            -[[H]]+2[[G]]+3*[[F]]-0.5[[I]]
            #[H]+2#[G]
         and relates it to the column indices in the 
        cols, returning
        a vector of the concentrations of each component."""
        if input_str is None or input_str.strip() == "":
            return np.zeros(len(cols))

        cols_escaped = [re.escape(col) for col in cols]
        pattern = r'(\+|-)?(\d*\.?\d+)?\*?\[(' + '|'.join(cols_escaped) + r')\]'
        matches = re.findall(pattern, input_str)

        res = np.zeros(len(cols))
        for m in matches:
            sign = 1 if m[0] != '-' else -1
            coeff = sign*float(m[1]) if m[1] else sign*1.0
            idx = cols.index(m[2])
            res[idx] += coeff

        return res

    def vec_to_conc_expression(self, vec,cols):
        """Takes a vector of concentrations and returns a string
        representation of the concentrations in the form of
        "+[[H]]+2[[G]]" or similar."""
        terms = []
        for i, v in enumerate(vec):
            if v =='-1':
                terms.append(f"-[{cols[i]}]")
            elif v == 1:
                terms.append(f"+[{cols[i]}]")
            elif v != 0:
                terms.append(f"{v}*[{cols[i]}]")
        return ''.join(terms).lstrip('+')



    def set_focus(self, c):
        self.last_focus = c

    def insert_term(self, h: str | ClickEventArguments) -> None:
        if not isinstance(h,str):
            raise ValueError("Species name from chip is not a str")
        if hasattr(self,"last_focus") and self.last_focus is not None and self.last_focus.value is not None:
            self.last_focus.value += f"+{h}"
            # if the focused widget is a fast-exchange input, trigger its handler to regenerate param blocks

            if hasattr(self, 'specDeltaInps') and self.last_focus in self.specDeltaInps:
                idx = self.specDeltaInps.index(self.last_focus)
                # call handler (simulate a change/blur)
                self._handle_spec_delta_blur(idx, self.last_focus)


    def _insert_species_into_fast_inp(self, species_name: str | ClickEventArguments) -> None:
        """Insert a species chip term into the currently focused fast-exchange input only.

        The inserted token matches the concentration expression token format: `[Species]`.
        """
        if not isinstance(species_name,str):
            raise ValueError("Species name from chip is not a str")
        if not hasattr(self, 'last_focus') or self.last_focus is None:
            return
        # only insert into fast-exchange inputs
        if hasattr(self, 'specDeltaInps') and self.last_focus in self.specDeltaInps:
            # insert as +[Species]
            self.last_focus.value = "" if self.last_focus.value is None else self.last_focus.value
            self.last_focus.value += "+[" + species_name + "]"
            
            idx = self.specDeltaInps.index(self.last_focus)
            self._handle_spec_delta_blur(idx, self.last_focus)
           
