from .base import BaseComponent
from nicegui import ui, run
import io
import json
import zipfile
import numpy as np
import pandas as pd
from ..classes import MCMCSim
from ..utils import safe_filename
from functools import partial
import asyncio
import re
import emcee
from matplotlib import pyplot as plt
import logging
from .bayes_priors import BayesPriorEditor

logger = logging.getLogger(__name__)


_CORNER_BASE_WIDTH_PCT = 56
_CORNER_MAX_WIDTH_PCT = 80
_CHAIN_BASE_HEIGHT_PX = 320
_CHAIN_PER_ROW_HEIGHT_PX = 120
_CHAIN_MIN_HEIGHT_PX = 500
_CHAIN_MAX_HEIGHT_PX = 2400
_CORNER_MIN_HEIGHT_PX = 420
_CORNER_MAX_HEIGHT_PX = 1400
_DISPLAY_DPI = 100
_EXPORT_DPI = 180


def _corner_width_pct(ndim: int) -> int:
    """Corner width policy: 3x3 baseline, 4x4 midpoint, 5x5+ capped at 80vw."""
    if ndim <= 3:
        return _CORNER_BASE_WIDTH_PCT
    if ndim == 4:
        return int(round(_CORNER_BASE_WIDTH_PCT + (_CORNER_MAX_WIDTH_PCT - _CORNER_BASE_WIDTH_PCT) * 0.5))
    return _CORNER_MAX_WIDTH_PCT


def _chain_height_px(ndim: int) -> int:
    rows = max(1, int(ndim) + 1)
    height = _CHAIN_BASE_HEIGHT_PX + rows * _CHAIN_PER_ROW_HEIGHT_PX
    return max(_CHAIN_MIN_HEIGHT_PX, min(_CHAIN_MAX_HEIGHT_PX, int(height)))


def _corner_height_px(ndim: int) -> int:
    # Keep corner close to square while allowing vertical growth with n.
    height = 280 + int(max(1, ndim) * 170)
    return max(_CORNER_MIN_HEIGHT_PX, min(_CORNER_MAX_HEIGHT_PX, height))


_TRIAL_STEPS = 1000


def _run_mcmc_trial(mc, trial_steps: int) -> float:
    """Run *trial_steps* of MCMC in a worker process and return elapsed wall-clock seconds."""
    import time
    from multiprocessing import Pool

    b = io.StringIO()
    with Pool() as pool:
        t0 = time.monotonic()
        mc.run(samples=trial_steps, pool=pool, tqdm_kwargs={"file": b})
    return time.monotonic() - t0


def _format_duration(seconds: float) -> str:
    """Return a human-readable string for a duration in seconds."""
    s = int(round(seconds))
    if s < 60:
        return f"{s} second{'s' if s != 1 else ''}"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min {s} s" if s else f"{m} minute{'s' if m != 1 else ''}"
    h, m = divmod(m, 60)
    return f"{h} h {m} min" if m else f"{h} hour{'s' if h != 1 else ''}"


class BayesPanel(BaseComponent):
    def setup_bindings(self) -> None:
        self.prior_editor.setup_bindings()
        self.sm.add_listener("fit_changed", self._refresh_for_active_fit)
        self.sm.add_listener("active_context_changed", self._rebuild_dark_species_card)
        self.sm.add_listener("data_model_processed", self._rebuild_dark_species_card)

    def setup_nicegui(self) -> None:
        self.prior_editor = BayesPriorEditor(self)
        self._dark_species_visible = False  # must be set before bind_visibility_from
        self.container = ui.column().classes("w-full")

        with self.container:
            # Dark / silent species card (shown only for UV-vis / fluorescence datasets)
            with ui.card().classes("w-full mb-4").bind_visibility_from(self, "_dark_species_visible"):
                ui.label("Dark / Silent Species").classes("text-base font-semibold mb-1")
                ui.label("Tick species whose ε / fluorescence amplitude is zero for each observable column.").classes(
                    "text-xs text-gray-500 mb-2"
                )
                self.dark_species_rows = ui.column().classes("w-full gap-1")

            # MCMC Configuration
            with ui.card().classes("w-full mb-4"):
                ui.label("MCMC Configuration").classes("text-lg font-bold mb-2")
                # with ui.grid(columns='auto 80px').classes('w-full'):
                with ui.grid(columns=2):
                    with ui.column().classes():
                        with ui.row():
                            ui.label("Number of Walkers:").classes("self-center mr-2")
                            self.nwalkers_input = ui.number(value=20, min=10, max=1000).classes("self-center mr-2")
                        with ui.row():
                            ui.label("Number of Steps:").classes("self-center mr-2")
                            self.nsteps_input = ui.number(value=10000, min=500, max=1000000).classes("self-center mr-2")
                        with ui.row():
                            ui.label("Steps per Chunk:").classes("self-center mr-2")
                            self.chunk_size_input = ui.number(value=500, min=10, max=1000000).classes(
                                "self-center mr-2"
                            )
                    with ui.column().classes("ml-5"):
                        self.edit_priors_button = ui.button("Edit priors (bounds)", on_click=self.prior_editor.open)
                        self.export_notebook_button = ui.button(
                            "Export to Notebook",
                            on_click=self._open_export_dialog,
                        ).classes("mt-2")

            # Control buttons
            with ui.row().classes("mt-4"):
                self.run_button = ui.button("Run Bayesian Analysis", on_click=self.run_analysis)
                self.stop_button = ui.button("Stop Analysis", on_click=self.stop_analysis)
                self.stop_button.set_enabled(False)

                with ui.tabs().classes("w-full") as tabs:
                    run = ui.tab("Run", icon="go")
                    results = ui.tab("Results", icon="box")
                with ui.tab_panels(tabs, value=run).classes("w-full h-full"):
                    with ui.tab_panel(run):
                        # Progress Display
                        # --- NiceGUI elements ---
                        self.progress_bar = ui.linear_progress(value=0, show_value=False)
                        self.progress_label = ui.label("Progress: 0%").classes("mt-2")
                        self.status_log = ui.textarea(label="Status Log").classes("w-full h-32 mt-2")
                        # Timers are created only while a run is active and canceled afterwards.
                        ui.markdown("#### Chains")
                        with ui.row().classes("w-full justify-center"):
                            self.chain_chart = ui.matplotlib().classes("w-full")

                    with ui.tab_panel(results):
                        # Results area
                        self.result_area = ui.markdown("### MCMC results ").classes("mt-4")

                        ui.markdown("#### Chains figure")
                        with ui.row().classes("w-full justify-center"):
                            self.result_chains = ui.matplotlib().classes("w-full")
                        ui.markdown("#### Corner plot")
                        with ui.row().classes("w-full justify-center"):
                            self.result_corner = ui.matplotlib().classes("w-full")
                        with ui.row().classes("w-full justify-center gap-2 mt-2 mb-2"):
                            ui.button("Download Chains Figure", on_click=self.download_chain_figure)
                            ui.button("Download Corner Figure", on_click=self.download_corner_figure)

        # Control variables
        self.is_running = False
        self.should_stop = False
        self.completed_steps = 0
        self.progress_timer = None
        self.status_timer = None
        self.graph_timer = None
        # Maps fit UUID → MCMCSim run for that fit (session-only; sampler state is not persisted)
        self._fit_to_mcmc: dict = {}
        self._apply_chain_container_style(self.chain_chart, ndim=2)
        self._rebuild_dark_species_card()
        self._apply_chain_container_style(self.result_chains, ndim=2)
        self._apply_corner_container_style(ndim=3)

    def _set_figure_size(self, fig, width_in: float, height_in: float) -> None:
        fig.set_dpi(_DISPLAY_DPI)
        fig.set_size_inches(width_in, height_in, forward=True)

    def _apply_chain_container_style(self, chart, ndim: int) -> None:
        height_px = _chain_height_px(ndim)
        chart.style(f"width: min(96vw, 1320px); height: {height_px}px; margin: 0 auto;")

    def _apply_corner_container_style(self, ndim: int) -> None:
        width_pct = _corner_width_pct(ndim)
        height_px = _corner_height_px(ndim)
        self.result_corner.style(
            f"width: {width_pct}vw; max-width: 80vw; min-width: 420px; height: {height_px}px; margin: 0 auto;"
        )

    def _chain_figsize(self, ndim: int) -> tuple[float, float]:
        rows = max(1, int(ndim) + 1)
        return (12.5, max(6.0, rows * 1.7))

    def _corner_figsize(self, ndim: int) -> tuple[float, float]:
        side = max(7.0, min(22.0, float(ndim) * 2.6))
        return (side, side)

    def _get_burnin(self, notify: bool = True) -> int:
        if not hasattr(self, "mcmc") or self.mcmc.mc is None or self.mcmc.mc.sampler is None:
            return 0
        tau = None
        try:
            tau = self.mcmc.mc.sampler.get_autocorr_time()
        except emcee.autocorr.AutocorrError as e:
            tau = e.tau
            if notify:
                s = (
                    f"Autocorrelation time is likely too short. Max tau is {int(np.max(tau))}; "
                    f"nsteps is {self.completed_steps}. Re-run for at least {int(50 * np.max(tau))} steps."
                )
                ui.notify(s, type="warning")
                self.result_area.content += f"""

            WARNING: {s}"""
        return int(5 * np.max(tau)) if tau is not None else 0

    def _start_run_timers(self) -> None:
        """Create live-update timers for an active run."""
        self._stop_run_timers()
        with self.container:
            self.progress_timer = ui.timer(0.1, callback=self._update_progress_bar, once=False, active=True)
            self.status_timer = ui.timer(0.1, callback=self._update_status_log, once=False, active=True)
            self.graph_timer = ui.timer(1.0, callback=self._update_graphs, once=False, active=True)

    def _stop_run_timers(self) -> None:
        """Cancel and clear any active run timers."""
        for timer_attr in ("progress_timer", "status_timer", "graph_timer"):
            timer = getattr(self, timer_attr, None)
            if timer is None:
                continue
            try:
                timer.cancel(with_current_invocation=True)
            except Exception:
                pass
            setattr(self, timer_attr, None)

    async def run_analysis(self):
        if self.is_running:
            ui.notify("Analysis already running!", type="warning")
            return

        active_fit = self.sm.active_fit_or_none
        if active_fit is None:
            ui.notify("No active fit result.", type="warning")
            return

        if active_fit.bd_model is None:
            print("No bindtools model selected for fitting, generating one.")
            ui.notify("Running an initial fit using least_sq")
            m1 = self.sm.generate_binding_model_for_fit(active_fit)
            m1 = await run.cpu_bound(
                partial(
                    m1.runModel,
                    ret=True,
                    skip_col=np.shape(self.sm.active_expt_data.col_to_comp)[0],
                    method=active_fit.fit_method,
                )
            )
            active_fit.bd_model = m1

        nsteps_target = int(self.nsteps_input.value)
        nwalkers = int(self.nwalkers_input.value)
        obslist = self.sm.active_expt_data.get_obs_list(self.sm._expt_dtypes)

        # Create MCMC simulation (not yet registered in state)
        self.mcmc = MCMCSim(
            model=self.sm.active_model,
            expt_data=self.sm.active_expt_data,
            bd_model=active_fit.bd_model,
            nwalkers=nwalkers,
            nsteps_target=nsteps_target,
            priors=list(self.prior_editor.priors) if self.prior_editor.priors else [],
        )
        self.mcmc.setup(obslist)

        # --- Timing trial (skipped for short runs) ---
        if nsteps_target > _TRIAL_STEPS:
            self.run_button.set_enabled(False)
            ui.notify(
                f"Running a {_TRIAL_STEPS:,}-step timing trial ({nwalkers} walkers) — please wait…",
                type="info",
                timeout=60000,
            )
            try:
                trial_elapsed = await run.cpu_bound(partial(_run_mcmc_trial, self.mcmc.mc, _TRIAL_STEPS))
                it_s = _TRIAL_STEPS / trial_elapsed
                full_seconds = nsteps_target * trial_elapsed / _TRIAL_STEPS
                full_time_str = _format_duration(full_seconds)

                with ui.dialog() as timing_dialog, ui.card().classes("w-[min(560px,92vw)]"):
                    ui.label("Runtime estimate").classes("text-lg font-bold")
                    ui.label(f"{_TRIAL_STEPS:,} steps took {trial_elapsed:.1f} s ({it_s:.2f} it/s).").classes(
                        "text-sm text-gray-600 mt-1"
                    )
                    ui.label(
                        f"The full run ({nsteps_target:,} steps, {nwalkers} walkers) "
                        f"will take approximately {full_time_str}."
                    ).classes("mt-2")
                    ui.label("Do you want to continue?").classes("mt-1 font-medium")
                    with ui.row().classes("w-full justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=lambda: timing_dialog.submit(False))
                        ui.button("Continue", on_click=lambda: timing_dialog.submit(True))

                should_continue = await timing_dialog
                timing_dialog.delete()
                if not should_continue:
                    self.run_button.set_enabled(True)
                    return
            except Exception as e:
                ui.notify(f"Timing trial failed ({e}); proceeding without estimate.", type="warning")

        # Register in state now that the user has confirmed (or the trial was skipped)
        self.sm.add_mcmc(self.mcmc, emit_events=False)
        self._fit_to_mcmc[active_fit.id] = self.mcmc
        self.sm.save_to_storage()
        self._clear_results()
        # Setup UI for running state
        self.is_running = True
        self.should_stop = False
        self.run_button.set_enabled(False)
        self.stop_button.set_enabled(True)
        self.progress_bar.value = 0
        self.progress_label.text = "Starting MCMC analysis..."
        self._log_status("Starting MCMC analysis...")
        self._start_run_timers()

        total_steps = self.mcmc.nsteps_target
        nwalkers = self.mcmc.nwalkers
        self.completed_steps = 0

        try:
            # Run MCMC in chunks
            self.mcmc.cancel_event.clear()
            # this function is part of the bindgui mcmc object, not the parent
            # it runs the mcmc in cpu-bound chunks
            await self.mcmc.run(int(self.chunk_size_input.value))
            await asyncio.sleep(0.1)

            if self.should_stop:
                self.progress_label.text = (
                    f"Analysis stopped at {self.completed_steps}/{total_steps} steps with {nwalkers} walkers"
                )
                self._log_status("Analysis stopped by user")
                ui.notify("MCMC analysis stopped by user", type="warning")
            else:
                self.progress_label.text = f"MCMC Complete! ({total_steps} steps with {nwalkers} walkers)"
                self._log_status("MCMC analysis completed successfully")
                ui.notify("MCMC analysis completed successfully!", type="positive")

                # Update results
                self._update_results(self.mcmc)

        except Exception as e:
            self.progress_label.text = "Analysis failed"
            self._log_status(f"Error: {str(e)}")
            ui.notify(f"MCMC analysis failed: {str(e)}", type="negative")

        finally:
            self._stop_run_timers()
            # Reset UI state
            self.is_running = False
            self.should_stop = False
            self.run_button.set_enabled(True)
            self.stop_button.set_enabled(False)

    def stop_analysis(self):
        """Stop the running analysis."""
        if self.is_running:
            self.should_stop = True
            self.mcmc.cancel_event.set()
            ui.notify("Stopping analysis after current chunk...", type="info")
        else:
            ui.notify("No analysis is currently running", type="warning")

    def _log_status(self, message):
        """Add a timestamped message to the status log."""
        import datetime

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        current_log = self.status_log.value or ""
        new_message = f"[{timestamp}] {message}\n"
        self.status_log.value = current_log + new_message
        logger.info(message)

        # Auto-scroll to bottom (approximate)
        lines = (current_log + new_message).count("\n")
        if lines > 8:  # Keep only recent messages visible
            lines_to_keep = "\n".join((current_log + new_message).split("\n")[-8:])
            self.status_log.value = lines_to_keep

    def _update_results(self, mcmc):
        """Update the results area with MCMC summary."""
        # Calculate acceptance fraction if available
        acceptance_frac = "N/A"
        if mcmc.mc and mcmc.mc.sampler and hasattr(mcmc.mc.sampler, "acceptance_fraction"):
            acceptance_frac = f"{mcmc.mc.sampler.acceptance_fraction.mean():.3f}"

        self.result_area.content = f"""
        ## MCMC Analysis Complete
        
        **Configuration:**
        - Walkers: {mcmc.nwalkers}
        - Steps target: {mcmc.nsteps_target}
        - Chunk Size: {self.chunk_size_input.value}
        
        **Results:**
        - Chains shape: {mcmc.mc.sampler.chain.shape if mcmc.mc and mcmc.mc.sampler else "N/A"}
        - Acceptance fraction: {acceptance_frac}
        
        Analysis completed at {pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        self._make_result_graphs()

    def _update_graphs(self):
        if hasattr(self, "mcmc"):
            while not self.mcmc.q3_samples.empty():
                samples = self.mcmc.q3_samples.get()
                chains = samples["chains"]  # shape: (nwalkers, nsteps, ndim)
                acceptance_frac = samples["acceptance_fraction"]  # shape: (nwalkers,)

                nsteps, nwalkers, ndim = chains.shape
                self._apply_chain_container_style(self.chain_chart, ndim)

                f = self.chain_chart.figure
                f.clear()
                w, h = self._chain_figsize(ndim)
                self._set_figure_size(f, w, h)
                axs = []
                for ii in range(ndim):
                    axs.append(f.add_subplot(ndim + 1, 1, ii + 1))
                axs.append(f.add_subplot(ndim + 1, 1, ndim + 1))

                # Plot chains for first 5 walkers per dimension
                walkers_to_plot = range(min(5, nwalkers))
                for d in range(ndim):
                    for w in walkers_to_plot:
                        axs[d].plot(chains[:, w, d], label=f"Dim {d} Walker {w}")
                        axs[d].set_title(f"Parameter {d}")
                        axs[d].set_xlabel("Steps")

                # Plot acceptance fraction
                axs[-1].bar(range(nwalkers), acceptance_frac)
                axs[-1].set_title("Acceptance Fraction per Walker")
                axs[-1].set_xlabel("Walker")
                axs[-1].set_ylabel("Acceptance Fraction")

                f.tight_layout()
                self.chain_chart.update()

    def _update_progress_bar(self):
        if hasattr(self, "mcmc"):
            self.progress_bar.set_value(
                self.mcmc.q_percent_done.get() if not self.mcmc.q_percent_done.empty() else self.progress_bar.value
            )

    def _update_status_log(self):
        if hasattr(self, "mcmc"):
            while not self.mcmc.q2_tqdm_out.empty():
                logstr = self.mcmc.q2_tqdm_out.get()
                pattern = r"\b(\d+)\b/.*?\[(\d{2}:\d{2}).*?,\s*([\d.]+)it/s\]"

                match = re.search(pattern, logstr)
                if match:
                    iters, time, it_s = match.groups()
                    self._log_status(f"{iters} iterations completed in {time}, {it_s} it/s")
                    self.completed_steps += int(iters)
                    it_s_val = float(it_s)
                    current_chunk = float(self.chunk_size_input.value)
                    if it_s_val > current_chunk / 2:
                        new_chunk = int(round(3 * it_s_val))
                        self.chunk_size_input.value = new_chunk
                        self.mcmc.chunk_size_val.value = new_chunk
                        self._log_status(
                            f">> **Chunk size adjusted:** sampling rate ({it_s_val:.1f} it/s) "
                            f"  exceeded chunk size / 2 ({current_chunk / 2:.1f}). "
                            f"  Chunk size set to **{new_chunk}** for the next chunk."
                        )

    def _clear_results(self):
        self.result_chains.figure.clear()
        self.result_corner.figure.clear()
        self.result_area.content = ""

        self.result_chains.update()
        self.result_corner.update()

    def _clear_run_state(self) -> None:
        """Reset the Run tab's live-progress UI without touching the Results tab."""
        self.chain_chart.figure.clear()
        self.chain_chart.update()
        self.status_log.set_value("")
        self.progress_bar.set_value(0)
        self.progress_label.set_text("")
        self.completed_steps = 0

    def _rebuild_dark_species_card(self, *args) -> None:
        """Rebuild dark-species toggle rows for the active dataset."""
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

    def _refresh_for_active_fit(self, e=None) -> None:
        """Called on fit_changed: clear MCMC state and restore results for the newly active fit."""
        if self.is_running:
            return
        self._clear_run_state()
        self._clear_results()
        active_fit = self.sm.active_fit_or_none
        if active_fit is None:
            return
        found_mcmc = self._fit_to_mcmc.get(active_fit.id)
        if (
            found_mcmc is not None
            and getattr(found_mcmc, "mc", None) is not None
            and getattr(found_mcmc.mc, "sampler", None) is not None
        ):
            self.mcmc = found_mcmc
            self._update_results(self.mcmc)

    def _make_result_graphs(self):
        if self.mcmc.mc.sampler is None:
            ui.notify("No chain available; re-run MCMC", type="negative")
            return
        ndim = int(self.mcmc.mc.sampler.ndim)
        self._apply_chain_container_style(self.result_chains, ndim)
        self._apply_corner_container_style(ndim)

        f = self.result_chains.figure
        f.clear()
        w, h = self._chain_figsize(ndim)
        self._set_figure_size(f, w, h)
        self.mcmc.mc.plot_chain(fig=f)
        f.tight_layout()
        self.result_chains.update()

        f = self.result_corner.figure
        f.clear()
        cw, ch = self._corner_figsize(ndim)
        self._set_figure_size(f, cw, ch)
        burnin = self._get_burnin(notify=True)
        self.mcmc.mc.make_corner_fig(burnin=burnin, fig=f)
        f.tight_layout()
        self.result_corner.update()

    def _download_figure(self, fig, filename: str) -> None:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=_EXPORT_DPI, bbox_inches="tight")
        buf.seek(0)
        ui.download.content(buf.getvalue(), filename=filename)

    def download_chain_figure(self) -> None:
        if not hasattr(self, "mcmc") or self.mcmc.mc is None or self.mcmc.mc.sampler is None:
            ui.notify("No chain figure available for download.", type="warning")
            return
        ndim = int(self.mcmc.mc.sampler.ndim)
        fig = plt.figure()
        w, h = self._chain_figsize(ndim)
        fig.set_dpi(_EXPORT_DPI)
        fig.set_size_inches(w * 1.2, h * 1.2, forward=True)
        self.mcmc.mc.plot_chain(fig=fig)
        fig.tight_layout()
        active_fit = self.sm.active_fit_or_none
        stem = active_fit.name if active_fit is not None else "mcmc"
        filename = f"{safe_filename(stem, fallback='mcmc')}_chains.png"
        self._download_figure(fig, filename)
        plt.close(fig)

    def download_corner_figure(self) -> None:
        if not hasattr(self, "mcmc") or self.mcmc.mc is None or self.mcmc.mc.sampler is None:
            ui.notify("No corner figure available for download.", type="warning")
            return
        ndim = int(self.mcmc.mc.sampler.ndim)
        fig = plt.figure()
        w, h = self._corner_figsize(ndim)
        fig.set_dpi(_EXPORT_DPI)
        fig.set_size_inches(w * 1.2, h * 1.2, forward=True)
        burnin = self._get_burnin(notify=False)
        self.mcmc.mc.make_corner_fig(burnin=burnin, fig=fig)
        fig.tight_layout()
        active_fit = self.sm.active_fit_or_none
        stem = active_fit.name if active_fit is not None else "mcmc"
        filename = f"{safe_filename(stem, fallback='mcmc')}_corner.png"
        self._download_figure(fig, filename)
        plt.close(fig)

    # ------------------------------------------------------------------
    # Notebook export
    # ------------------------------------------------------------------

    def _open_export_dialog(self) -> None:
        active_fit = self.sm.active_fit_or_none
        if active_fit is None:
            ui.notify("No active fit to export.", type="warning")
            return

        has_sampler = (
            hasattr(self, "mcmc")
            and getattr(self.mcmc, "mc", None) is not None
            and getattr(self.mcmc.mc, "sampler", None) is not None
        )

        include_chains: dict = {"value": False}

        with ui.dialog() as dialog, ui.card().classes("min-w-[24rem]"):
            ui.label("Export MCMC Notebook").classes("text-lg font-bold mb-2")

            if has_sampler:
                chain_mb = (
                    self.mcmc.mc.sampler.backend.chain.nbytes + self.mcmc.mc.sampler.backend.log_prob.nbytes
                ) / (1024 * 1024)
                options = {
                    "code": "Run MCMC (code only)",
                    "chains": f"Export and load saved chains (.hdf, ~{chain_mb:.1f} MB uncompressed)",
                }
                radio = ui.radio(options=options, value="code").classes("mt-2")
                radio.on_value_change(lambda e: include_chains.update({"value": e.value == "chains"}))
            else:
                ui.label("Run MCMC (code only)").classes("font-medium mt-2")
                ui.label("MCMC has not yet run in this session; chains cannot be exported.").classes(
                    "text-sm text-orange-600 mt-1"
                )

            with ui.row().classes("mt-4 gap-2 justify-end w-full"):
                ui.button("Cancel", on_click=dialog.close)
                ui.button(
                    "Export",
                    on_click=lambda: (
                        dialog.close(),
                        self._do_export_notebook(include_chains["value"]),
                    ),
                ).props("color=primary")

        dialog.open()

    def _do_export_notebook(self, include_chains: bool) -> None:
        active_fit = self.sm.active_fit_or_none
        if active_fit is None:
            ui.notify("No active fit to export.", type="negative")
            return

        mcmc_arg = self.mcmc if hasattr(self, "mcmc") else None
        try:
            notebook, csv_df, h5_bytes = self.sm.dump_mcmc_notebook(mcmc_arg, include_chains)
        except Exception as exc:
            ui.notify(f"Notebook export failed: {exc}", type="negative")
            return

        stem = safe_filename(active_fit.name, fallback="mcmc")
        nb_bytes = json.dumps(notebook, indent=1).encode()
        csv_bytes = csv_df.to_csv(index=False, float_format="{:.5e}".format).encode()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{stem}.ipynb", nb_bytes)
            zf.writestr(f"{stem}_data.csv", csv_bytes)
            if h5_bytes is not None:
                zf.writestr(f"{stem}_chains.hdf", h5_bytes)
        buf.seek(0)

        zip_filename = f"{stem}_mcmc_notebook.zip"
        ui.download.content(buf.read(), filename=zip_filename)
        ui.notify(f"Notebook exported as {zip_filename}.", type="positive")
