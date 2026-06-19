import io
import logging
import uuid
from dataclasses import dataclass, field, InitVar
from typing import Any, Optional

from nicegui import run
import numpy as np
import bindtools.binding as bd
from functools import partial
from multiprocessing import Manager, Pool

from .ExptData import ExptData
from .Model import Model

logger = logging.getLogger(__name__)


@dataclass
class MCMCSim:
    """Data class to represent a MCMC simulation."""

    nwalkers: int = 100
    nsteps_target: int = 1000

    burn: int = 100
    thin: int = 1
    max_retained_points: int = 1000
    seed: Optional[int] = None
    chains: np.ndarray = field(default_factory=lambda: np.array([]))  # Array to hold the MCMC chains
    priors: list[dict[str, Any]] = field(default_factory=list)
    model_id: Optional[uuid.UUID] = None
    expt_data_id: Optional[uuid.UUID] = None
    nsteps_done: int = 0
    bd_model: Optional[bd.bindingModel] = None

    model: InitVar[Optional[Model]] = None
    expt_data: InitVar[Optional[ExptData]] = None

    id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())  # unique ID for the instance

    def __post_init__(self, model, expt_data) -> None:
        """Ensure data are appropriate types."""
        if not isinstance(self.id, uuid.UUID):
            if isinstance(self.id, str):
                self.id = uuid.UUID(self.id)

        prior_specs: list[dict[str, Any]] = []
        for prior in self.priors or []:
            if not isinstance(prior, dict):
                continue
            prior_type = str(prior.get("type", "uniform")).lower()
            params = prior.get("params")
            if not isinstance(params, dict):
                params = {
                    key: prior.get(key) for key in ("lower", "upper", "mu", "sigma") if prior.get(key) is not None
                }
            prior_specs.append(
                {
                    "label": str(prior.get("label", "")),
                    "type": prior_type,
                    "params": dict(params),
                }
            )
        self.priors = prior_specs

        if model is not None:
            self.model_id = model.id
            self._model = model
        else:
            self._model = None
        if expt_data is not None:
            self.expt_data_id = expt_data.id
            self._expt_data = expt_data
        else:
            self._expt_data = None

        manager = Manager()
        self.cancel_event = manager.Event()
        self.q_percent_done = manager.Queue()
        self.q2_tqdm_out = manager.Queue()
        self.q3_samples = manager.Queue()
        self.chunk_size_val = manager.Value("i", 100)

    def find_and_link_expt_data(self, expt_datas: dict[uuid.UUID, ExptData]) -> None:
        """Link the experimental data to this fit result."""
        if expt_datas is not None:
            if self.expt_data_id in expt_datas and self.expt_data_id is not None:
                self._expt_data = expt_datas[self.expt_data_id]
                return
        else:
            raise ValueError(f"Corresponding experimental data {self.expt_data_id} not found for FitResult.")

    def find_and_link_model(self, models: dict[uuid.UUID, Model]) -> None:
        """Link the experimental data to this fit result."""
        if models is not None:
            if self.model_id in models and self.model_id is not None:
                self._model = models[self.model_id]
                return
        else:
            raise ValueError(f"Corresponding model {self.model_id} not found for FitResult.")

    def setup(self, obslist: list[bd.ObsType]) -> None:
        if self.bd_model is None:
            raise ValueError("bd_model must be set before running MCMC simulation.")
        if self._expt_data is None:
            raise ValueError("Experimental data must be linked before running MCMC simulation.")

        self.mc = bd.MCMC(self.bd_model, obslist, walkers=self.nwalkers, samples=self.nsteps_target)
        self._apply_prior_bounds(obslist)

    def _parameter_specs(self, obslist: list[bd.ObsType]) -> list[dict[str, Any]]:
        if self.bd_model is None or self.bd_model.miniResult is None:
            return []

        specs: list[dict[str, Any]] = []
        mini_result_params = getattr(self.bd_model.miniResult, "params", None)
        if mini_result_params is None:
            return []

        for param_name in mini_result_params.keys():
            if not mini_result_params[param_name].vary:
                continue
            param = self.bd_model.params[param_name]
            specs.append(
                {
                    "label": str(getattr(param, "name", param_name)),
                    "lower": float(param.min),
                    "upper": float(param.max),
                }
            )

        seen_sigma_names: set[str] = set()
        for obs in obslist:
            if obs.name in seen_sigma_names:
                continue
            seen_sigma_names.add(obs.name)
            sigma_param = obs.param
            specs.append(
                {
                    "label": str(getattr(sigma_param, "name", obs.name)),
                    "lower": float(sigma_param.min),
                    "upper": float(sigma_param.max),
                }
            )

        return specs

    def _apply_prior_bounds(self, obslist: list[bd.ObsType]) -> None:
        if self.bd_model is None:
            return

        specs = self._parameter_specs(obslist)
        resolved_bounds: list[list[float]] = []
        for index, spec in enumerate(specs):
            prior = self.priors[index] if index < len(self.priors) else {}
            prior_type = str(prior.get("type", "uniform")).lower()
            params = prior.get("params", {}) if isinstance(prior.get("params", {}), dict) else {}
            lower = params.get("lower", spec["lower"])
            upper = params.get("upper", spec["upper"])
            if prior_type != "uniform":
                if prior_type not in ("none", ""):
                    logger.warning(
                        "Unsupported prior type '%s' for '%s'; falling back to model bounds.",
                        prior_type,
                        spec.get("label", f"param_{index}"),
                    )
                lower = spec["lower"]
                upper = spec["upper"]

            try:
                lower_value = float(spec["lower"] if lower is None else lower)
            except (TypeError, ValueError):
                lower_value = float(spec["lower"])
            try:
                upper_value = float(spec["upper"] if upper is None else upper)
            except (TypeError, ValueError):
                upper_value = float(spec["upper"])

            resolved_bounds.append([lower_value, upper_value])

        if not hasattr(self.bd_model, "fcn_opts") or self.bd_model.fcn_opts is None:
            self.bd_model.fcn_opts = {}
        self.bd_model.fcn_opts["mcmc_bounds"] = np.array(resolved_bounds, dtype=float)

    async def run(self, chunk_size: Optional[int] = None) -> None:
        if chunk_size is not None:
            self.chunk_size_val.value = int(chunk_size)
        self.mc = await run.cpu_bound(partial(self._run_mcmc))

    def _run_mcmc(self) -> bd.MCMC:
        """Run the MCMC simulation with multiprocessing in blocks of chunk_size steps."""
        if self.mc is None:
            raise ValueError("MCMC not set up. Call setup() before running the simulation.")

        with Pool() as pool:
            while self.nsteps_done < self.nsteps_target:
                if self.cancel_event.is_set():
                    logger.info("MCMC run cancelled.")
                    return self.mc
                chunk_size = self.chunk_size_val.value
                remaining_raw = self.nsteps_target - self.nsteps_done
                raw_chunk = min(chunk_size, remaining_raw)

                # Convert raw chunk size to stored samples chunk size based on thin factor
                samples_stored = max(1, raw_chunk // self.thin)
                actual_raw = samples_stored * self.thin

                b = io.StringIO()
                self.mc.run(samples=samples_stored, thin=self.thin, pool=pool, tqdm_kwargs={"file": b})

                self.nsteps_done += actual_raw
                self.q_percent_done.put(self.nsteps_done / self.nsteps_target)
                self.q2_tqdm_out.put(b.getvalue().splitlines()[-1])
                if self.mc.sampler is not None:
                    a = {}
                    # a['percent_done'] = self.nsteps_done / self.nsteps_target
                    # a['tqdm'] = b.getvalue().splitlines()[-1]
                    a["chains"] = self.mc.sampler.get_chain()  # discard=self.burn, thin=self.thin, flat=True)
                    a["acceptance_fraction"] = self.mc.sampler.acceptance_fraction
                    self.q3_samples.put(a)
                logger.info("Completed steps: %s", self.nsteps_done)

        return self.mc
