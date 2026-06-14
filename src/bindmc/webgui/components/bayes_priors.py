from __future__ import annotations

from functools import partial
from typing import Any
from typing import TYPE_CHECKING

from nicegui import run, ui

if TYPE_CHECKING:
    from .bayes import BayesPanel


def _classify_param_type(label: str) -> str:
    """Classify a prior parameter by type based on its label string."""
    if label.startswith('log'):
        return 'bindingConstant'
    if label.startswith('delta0_'):
        return 'delta'
    if label.startswith('deltac') and '_' in label[6:]:
        return 'deltadelta'
    if label.startswith('shift_'):
        return 'delta'
    if label.startswith('eps_'):
        return 'extinction'
    if label.startswith('fluor_'):
        return 'fluorAmp'
    return 'sigma'


_PARAM_TYPE_CLASSES: dict[str, str] = {
    'bindingConstant': 'bg-blue-100 text-blue-700',
    'delta': 'bg-green-100 text-green-700',
    'deltadelta': 'bg-teal-100 text-teal-700',
    'sigma': 'bg-orange-100 text-orange-700',
    'extinction': 'bg-purple-100 text-purple-700',
    'fluorAmp': 'bg-amber-100 text-amber-700',
}


class BayesPriorEditor:
    """Manage editable Bayesian priors for the Bayes panel."""

    def __init__(self, panel: 'BayesPanel') -> None:
        self.panel = panel
        self.priors: list[dict[str, Any]] = []

    def setup_bindings(self) -> None:
        active_mcmc = self.panel.sm.active_mcmc_or_none
        if active_mcmc is not None and getattr(active_mcmc, "priors", None):
            self.priors = list(active_mcmc.priors)

    async def _ensure_active_fit_model(self) -> bool:
        """Ensure an active fit has a bindtools model available for prior editing."""
        active_fit = self.panel.sm.active_fit_or_none
        active_expt_data = self.panel.sm.active_expt_data_or_none
        if active_fit is None or active_expt_data is None:
            return False
        if active_fit.bd_model is not None:
            return True

        ui.notify('Preparing fit model for prior editor. This may take a second...', type='info')
        try:
            model = self.panel.sm.generate_binding_model_for_fit(active_fit)
            skip_col = int(active_expt_data.col_to_comp.shape[0])
            model = await run.cpu_bound(
                partial(
                    model.runModel,
                    ret=True,
                    skip_col=skip_col,
                    method=active_fit.fit_method,
                )
            )
            active_fit.bd_model = model
            self.panel.sm.save_to_storage()
            ui.notify('Fit model is ready. You can now edit priors.', type='positive')
            return True
        except Exception as e:
            ui.notify(f'Unable to prepare fit model for priors: {e}', type='negative')
            return False

    def _current_prior_specs(self) -> list[dict[str, Any]]:
        active_fit = self.panel.sm.active_fit_or_none
        active_expt_data = self.panel.sm.active_expt_data_or_none
        if active_fit is None or active_fit.bd_model is None or active_expt_data is None:
            return []

        model = active_fit.bd_model
        mini_result_params = getattr(model.miniResult, "params", None)
        if mini_result_params is None:
            return []

        specs: list[dict[str, Any]] = []
        for param_name in mini_result_params.keys():
            if not mini_result_params[param_name].vary:
                continue
            param = model.params[param_name]
            label_str = str(getattr(param, 'name', param_name))
            specs.append({
                'label': label_str,
                'lower': float(param.min),
                'upper': float(param.max),
                'fit_value': float(mini_result_params[param_name].value),
                'param_type': _classify_param_type(label_str),
            })

        seen_sigma_names: set[str] = set()
        for obs in active_expt_data.get_obs_list(self.panel.sm._expt_dtypes):
            if obs.name in seen_sigma_names:
                continue
            seen_sigma_names.add(obs.name)
            sigma_param = obs.param
            sigma_fit_value = None
            try:
                sigma_fit_value = None if sigma_param.value is None else float(sigma_param.value)
            except (TypeError, ValueError):
                sigma_fit_value = None
            specs.append({
                'label': str(getattr(sigma_param, 'name', obs.name)),
                'lower': float(sigma_param.min),
                'upper': float(sigma_param.max),
                'fit_value': sigma_fit_value,
                'param_type': 'sigma',
            })

        return specs

    def _default_prior_rows(self) -> list[dict[str, Any]]:
        return [
            {
                'label': spec['label'],
                'type': 'uniform',
                'params': {'lower': spec['lower'], 'upper': spec['upper']},
            }
            for spec in self._current_prior_specs()
        ]

    def _sync_prior_row_controls(self, row_state: dict[str, Any]) -> None:
        is_uniform = row_state['type_select'].value == 'Uniform'
        row_state['lower_input'].set_enabled(is_uniform)
        row_state['upper_input'].set_enabled(is_uniform)

    async def open(self) -> None:
        if not await self._ensure_active_fit_model():
            ui.notify('No active fit is available to edit priors.', type='warning')
            return

        specs = self._current_prior_specs()
        if not specs:
            ui.notify('No active fit is available to edit priors.', type='warning')
            return

        default_rows = self._default_prior_rows()
        if self.priors:
            prior_by_label = {
                str(prior.get('label', '')): prior
                for prior in self.priors
                if isinstance(prior, dict)
            }
            rows = [prior_by_label.get(spec['label'], default_row) for spec, default_row in zip(specs, default_rows)]
        else:
            rows = default_rows
        row_states: list[dict[str, Any]] = []

        with ui.dialog() as dialog, ui.card().classes('w-[min(980px,96vw)] max-h-[88vh] overflow-hidden bayes-priors-card'):
            ui.label('Edit MCMC Priors').classes('text-lg font-bold')
            ui.label('Uniform priors use lower/upper bounds. None keeps the current model bounds.').classes('text-sm text-gray-600 mb-2')
            status_label = ui.label('').classes('text-negative mb-2')
            with ui.scroll_area().classes('w-full').style('max-height: 65vh;'):
                for index, spec in enumerate(specs):
                    prior = rows[index] if index < len(rows) else None
                    prior_params = prior.get('params', {}) if isinstance(prior, dict) else {}
                    if not isinstance(prior_params, dict):
                        prior_params = {}
                    with ui.card().classes('w-full mb-2'):
                        with ui.row().classes('w-full items-center gap-3 flex-wrap'):
                            ui.label(spec['label']).classes('font-semibold w-60')
                            param_type = spec['param_type']
                            ui.label(param_type).classes(
                                'text-xs font-medium px-2 py-0.5 rounded '
                                + _PARAM_TYPE_CLASSES.get(param_type, 'bg-gray-100 text-gray-700')
                            )
                            type_select = ui.select(
                                options=['Uniform', 'None'],
                                value='Uniform' if prior is None else ('None' if str(prior.get('type', 'uniform')).lower() == 'none' else 'Uniform'),
                                label='Prior type',
                            ).classes('w-40')
                            lower_input = ui.number(
                                label='Lower',
                                value=spec['lower'] if prior is None else prior_params.get('lower', spec['lower']),
                            ).classes('w-32')
                            upper_input = ui.number(
                                label='Upper',
                                value=spec['upper'] if prior is None else prior_params.get('upper', spec['upper']),
                            ).classes('w-32')
                            fit_val = spec.get('fit_value')
                            fit_text = 'N/A' if fit_val is None else f'{float(fit_val):.6g}'
                            ui.label(f'Current fitted: {fit_text}').classes('text-xs text-gray-600')
                            row_state = {
                                'label': spec['label'],
                                'type_select': type_select,
                                'lower_input': lower_input,
                                'upper_input': upper_input,
                                'fit_value': fit_val,
                                'param_type': param_type,
                            }
                            row_states.append(row_state)

                            def _on_type_change(_=None, row_state=row_state):
                                self._sync_prior_row_controls(row_state)

                            type_select.on_value_change(_on_type_change)
                            self._sync_prior_row_controls(row_state)

                            async def _open_apply_modal(source_row=row_state) -> None:
                                pt = source_row['param_type']
                                same_type_others = [r for r in row_states if r is not source_row and r['param_type'] == pt]
                                if not same_type_others:
                                    ui.notify(f'No other {pt} parameters to apply to.', type='info')
                                    return

                                with ui.dialog() as apply_dialog, ui.card().classes('w-[min(520px,92vw)]'):
                                    ui.label(f'Apply to all {pt} parameters').classes('text-lg font-bold mb-1')
                                    ui.label(
                                        'Choose how to apply the current bounds to the other '
                                        f'{len(same_type_others)} {pt} parameter(s):'
                                    ).classes('text-sm text-gray-600 mb-3')
                                    with ui.column().classes('w-full gap-2'):
                                        ui.button(
                                            'Copy these bounds exactly',
                                            on_click=lambda: apply_dialog.submit('copy'),
                                        ).classes('w-full')
                                        ui.button(
                                            "Shift to each parameter's fitted value (keep same margins)",
                                            on_click=lambda: apply_dialog.submit('shift'),
                                        ).classes('w-full')
                                        ui.button(
                                            'Cancel',
                                            on_click=lambda: apply_dialog.submit('cancel'),
                                        ).classes('w-full')

                                mode = await apply_dialog
                                if mode == 'cancel' or mode is None:
                                    return

                                src_lower = source_row['lower_input'].value
                                src_upper = source_row['upper_input'].value
                                src_type = source_row['type_select'].value
                                src_fit = source_row.get('fit_value')

                                for other in same_type_others:
                                    if (
                                        mode == 'shift'
                                        and src_type == 'Uniform'
                                        and src_lower is not None
                                        and src_upper is not None
                                        and src_fit is not None
                                    ):
                                        tgt_fit = other.get('fit_value')
                                        if tgt_fit is not None:
                                            margin_below = float(src_fit) - float(src_lower)
                                            margin_above = float(src_upper) - float(src_fit)
                                            other['lower_input'].value = float(tgt_fit) - margin_below
                                            other['upper_input'].value = float(tgt_fit) + margin_above
                                        else:
                                            other['lower_input'].value = src_lower
                                            other['upper_input'].value = src_upper
                                    else:
                                        other['lower_input'].value = src_lower
                                        other['upper_input'].value = src_upper
                                    other['type_select'].value = src_type
                                    self._sync_prior_row_controls(other)

                            ui.button(
                                f'Apply to all ({param_type})',
                                on_click=_open_apply_modal,
                            ).classes('text-xs')

            async def _save_priors() -> None:
                saved_rows: list[dict[str, Any]] = []
                out_of_range_rows: list[str] = []
                for row_state in row_states:
                    prior_type = row_state['type_select'].value
                    if prior_type == 'None':
                        saved_rows.append({
                            'label': row_state['label'],
                            'type': 'none',
                            'params': {},
                        })
                        continue

                    lower_value = row_state['lower_input'].value
                    upper_value = row_state['upper_input'].value
                    if lower_value is None or upper_value is None:
                        status_label.text = f"{row_state['label']}: lower and upper bounds are required for a uniform prior."
                        return
                    try:
                        lower_float = float(lower_value)
                        upper_float = float(upper_value)
                    except (TypeError, ValueError):
                        status_label.text = f"{row_state['label']}: bounds must be numeric."
                        return
                    if lower_float > upper_float:
                        status_label.text = f"{row_state['label']}: lower bound must be less than or equal to upper bound."
                        return

                    saved_rows.append({
                        'label': row_state['label'],
                        'type': 'uniform',
                        'params': {'lower': lower_float, 'upper': upper_float},
                    })
                    fit_value = row_state.get('fit_value')
                    if fit_value is not None and not (lower_float <= float(fit_value) <= upper_float):
                        out_of_range_rows.append(
                            f"{row_state['label']} (fit={float(fit_value):.6g}, bounds=[{lower_float:.6g}, {upper_float:.6g}])"
                        )

                if out_of_range_rows:
                    with ui.dialog() as confirm_dialog, ui.card().classes('w-[min(760px,92vw)]'):
                        ui.label('Bounds exclude fitted value').classes('text-lg font-bold')
                        ui.label('The current fitted value is outside the bounds for:').classes('mb-1')
                        ui.markdown('\n'.join([f'- {item}' for item in out_of_range_rows]))
                        ui.label('Are you sure you want to save these priors?').classes('mt-1')
                        with ui.row().classes('w-full justify-end gap-2 mt-2'):
                            ui.button('Cancel', on_click=lambda: confirm_dialog.submit(False))
                            ui.button('Save anyway', on_click=lambda: confirm_dialog.submit(True))
                    should_continue = await confirm_dialog
                    confirm_dialog.delete()
                    if not should_continue:
                        return

                self.priors = saved_rows
                if hasattr(self.panel, 'mcmc'):
                    self.panel.mcmc.priors = list(saved_rows)
                    self.panel.sm.save_to_storage()
                dialog.submit(True)

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=lambda: dialog.submit(False))
                ui.button('Save priors', on_click=_save_priors)

        dialog.open()
        await ui.run_javascript(
            '(function attempt(n) {'
            '  var els = document.querySelectorAll(".bayes-priors-card input[type=number]");'
            '  els.forEach(function(el) {'
            '    el.addEventListener("wheel", function(e) { e.preventDefault(); }, {passive: false});'
            '  });'
            '  if (els.length === 0 && n > 0) { setTimeout(function() { attempt(n - 1); }, 50); }'
            '})(10);'
        )
        await dialog