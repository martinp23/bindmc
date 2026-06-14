import gzip
import io
import json
import os
import sys
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Optional, Callable, Any

import numpy as np
import pandas as pd
from nicegui import app, ui
from nicegui.events import UploadEventArguments, ValueChangeEventArguments
import bindtools.binding as bd

from ..classes import BindingConstant, Component, Model, Simulation, ExptData, FitResult, RawData,ExptDataType, ChemicalShiftParam, MCMCSim, UIBindings
from ..utils import eq_mat_from_equation_str_infer_components
from lmfit import Parameter as LMFitParameter
import logging
logger = logging.getLogger(__name__)

class StateManager:

    def __init__(self,load_prior_state: bool = True):
        self.models: dict[uuid.UUID,Model] = {}  # make these uuid-keyed dicts?
        self.fits: dict[uuid.UUID,FitResult] = {}
        self.expt_datas: dict[uuid.UUID,ExptData] = {}
        self.simulations: dict[uuid.UUID,Simulation] = {}
        self.experimental_data: Optional[pd.DataFrame] = None
        self.raw_datas: dict[uuid.UUID, RawData] = {}
        self.mcmcs: dict[uuid.UUID, MCMCSim] = {}
        self._active_model_id: Optional[uuid.UUID] = None
        self._active_sim_id: Optional[uuid.UUID] = None
        self._active_fit_id: Optional[uuid.UUID] = None
        self._active_expt_data_id: Optional[uuid.UUID] = None
        self._active_raw_data_id: Optional[uuid.UUID] = None
        self._active_mcmc_id: Optional[uuid.UUID] = None
        self._listeners: dict[str, list[Callable]] = {}
        self.default_model_ids: list[uuid.UUID] = []
        self.raw_data: RawData = RawData()  # Initialize with an empty RawData instance
        self.ui_bindings: UIBindings = UIBindings()
        
        self._expt_dtypes: dict[str,ExptDataType] = {
            'conc': ExptDataType(name='Conc.', init_meas='grav_vol', units='M'),
            'nmr conc': ExptDataType(name='NMR Conc.', init_meas='nmr_integ', units='M'),
            'delta h': ExptDataType(name='H (ppm)',init_meas='nmr_ppm',units='ppm'),
            'delta f': ExptDataType(name='F (ppm)',init_meas='nmr_ppm',units='ppm'),
            'absorbance': ExptDataType(name='Absorbance', init_meas='uvvis', units='absorbance'),
            'fluorescence': ExptDataType(name='Fluorescence int.', init_meas='fluor', units='intensity'),
        }

        

        self._init_bindables()
        self.add_listener(
            "model_changed", self.save_to_storage
        )  # Save state when model is updated
        self.add_listener(
            "simulation_completed", self.save_to_storage
        )  # Save state when simulation is completed
        self.add_listener(
            "fit_completed", self.save_to_storage
        )  # Save state when simulation is completed
        self.add_listener(
            "simulation_deleted", self.save_to_storage
        )
        
        #    self._set_initial_simFig_style()

        if load_prior_state and app.storage.user.get("state-data"):
            try:
                self.load_storage_into_state()
            except Exception as e:
                logger.error(f"Error loading model data: {e}")

        # Initialize with default model
        if len(self.models) == 0:
            self._initialize_default_models(emit_events=False)


    def load_storage_into_state(self):

        orphans = []
        self.from_json(
            app.storage.user["state-data"]
        )  # Load SimData from user storage if available
        logger.info("Loaded model data from user storage.")
        # link simulations (which specify a modelID, not a full model object) to the actual models
        for sim in self.simulations.values():
            try:
                sim.find_and_link_model(
                    self.models
                )  # TODO: handle case where model is not found (seems unlikely?)
            except(ValueError):
                orphans.append(sim)
        for o in orphans:
            logger.info(f'Simulation {o.id} is orphaned; deleting.')
            self._delete_object_core(o)

        orphans = []
        for fit in self.fits.values():
            try:
                fit.find_and_link_model(
                    self.models)
                fit.find_and_link_expt_data(
                    self.expt_datas)
            except(ValueError):
                orphans.append(fit)

        for expt_data in self.expt_datas.values():
            try:
                expt_data.find_and_link_model(
                    self.models)
                expt_data.find_and_link_raw_data(
                    self.raw_datas)
                
                # Initialize selected_columns after raw data is linked
                if not expt_data.selected_columns and hasattr(expt_data, '_raw_data') and expt_data._raw_data:
                    raw_data = expt_data._raw_data.data if hasattr(expt_data._raw_data, 'data') else pd.DataFrame()
                    if not raw_data.empty:
                        expt_data.selected_columns = raw_data.columns.tolist()
            except(ValueError):
                orphans.append(expt_data)
            
        for mcmc in self.mcmcs.values():
            try:
                mcmc.find_and_link_model(self.models)
                mcmc.find_and_link_expt_data(self.expt_datas)
            except(ValueError):
                orphans.append(mcmc)

        for o in orphans:
            if isinstance(o,ExptData):
                otype='ExptData'
            elif isinstance(o,MCMCSim):
                otype = 'MCMCSim'
            elif isinstance(o,FitResult):
                otype = 'FitResult'
            else:
                otype = "Unknown object"
            logger.warning(f'{otype} {o.id} is orphaned, deleting.')
            self._delete_object_core(o)

        self._finalize_active_context(reason="load_storage_into_state", emit_events=True)
        # Emit key events so that UI components refresh 
        self.notify_listeners("active_context_changed", {})
        self.notify_listeners("model_changed")
        self.notify_listeners("data_imported")
        self.notify_listeners("fits_loaded")

    def add_listener(self, event: str, callback: Callable):
        """Add a listener for a specific event."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

        # model_changed - called from binding_model.py; listened by data_gen

    def notify_listeners(self, event: ValueChangeEventArguments|str, *args, **kwargs):
        """Notify all listeners of a specific event."""
        if event in self._listeners and isinstance(event,str):
            logger.info(f"Listener notified: {event}")
            uniq_list = list(set(self._listeners[event]))  # Ensure unique callbacks
            for callback in uniq_list:
                callback(*args, **kwargs)

    def _snapshot_object_ids(self) -> dict[str, set[uuid.UUID]]:
        return {
            "models": set(self.models.keys()),
            "fits": set(self.fits.keys()),
            "simulations": set(self.simulations.keys()),
            "expt_datas": set(self.expt_datas.keys()),
            "raw_datas": set(self.raw_datas.keys()),
            "mcmcs": set(self.mcmcs.keys()),
        }

    def _emit_collection_events(self, before: dict[str, set[uuid.UUID]], after: dict[str, set[uuid.UUID]], notify_listeners: bool) -> None:
        """Emit compatibility events for collection-level changes."""
        if not notify_listeners:
            return
        if before["models"] != after["models"]:
            self.notify_listeners("model_changed")
        if before["fits"] != after["fits"]:
            self.notify_listeners("fit_deleted")
        if before["simulations"] != after["simulations"]:
            self.notify_listeners("simulation_deleted")
        if before["expt_datas"] != after["expt_datas"] or before["raw_datas"] != after["raw_datas"]:
            self.notify_listeners("expt_data_changed")
            self.notify_listeners("data_imported")
        if before["mcmcs"] != after["mcmcs"]:
            self.notify_listeners("mcmc_changed")

    def _latest_id(self, coll: dict[uuid.UUID, Any]) -> uuid.UUID | None:
        return next(reversed(coll), None) if coll else None

    def _latest_matching_id(self, coll: dict[uuid.UUID, Any], predicate: Callable[[Any], bool]) -> uuid.UUID | None:
        for id, obj in reversed(list(coll.items())):
            if predicate(obj):
                return id
        return None

    def _normalize_uuid(self, value: uuid.UUID | str | None) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, str):
            if value in ("", "None"):
                return None
            try:
                return uuid.UUID(value)
            except Exception:
                return None
        if isinstance(value, uuid.UUID):
            return value
        return None

    def _reconcile_active_ids(self, reason: str = "") -> dict[str, tuple[uuid.UUID | None, uuid.UUID | None]]:
        """Ensure all active IDs are valid and context-consistent."""
        changes: dict[str, tuple[uuid.UUID | None, uuid.UUID | None]] = {}

        def _set_active(attr: str, new_value: uuid.UUID | None) -> None:
            old_value = getattr(self, attr)
            if old_value != new_value:
                setattr(self, attr, new_value)
                changes[attr] = (old_value, new_value)

        if not self.models:
            self._initialize_default_models(emit_events=False)
        _set_active("_active_model_id", self._normalize_uuid(self._active_model_id))
        if self._active_model_id not in self.models:
            _set_active("_active_model_id", self._latest_id(self.models))

        # Raw data: valid ID or fallback to latest.
        _set_active("_active_raw_data_id", self._normalize_uuid(self._active_raw_data_id))
        if self._active_raw_data_id not in self.raw_datas:
            fallback_raw = None
            maybe_expt_id = self._normalize_uuid(self._active_expt_data_id)
            if maybe_expt_id in self.expt_datas and maybe_expt_id is not None:
                maybe_raw = self._normalize_uuid(self.expt_datas[maybe_expt_id].raw_data_id)
                if maybe_raw in self.raw_datas:
                    fallback_raw = maybe_raw
            if fallback_raw is None:
                fallback_raw = self._latest_id(self.raw_datas)
            _set_active("_active_raw_data_id", fallback_raw)

        # Expt data: prefer active raw data, then active model, then any.
        _set_active("_active_expt_data_id", self._normalize_uuid(self._active_expt_data_id))
        expt_is_valid = self._active_expt_data_id in self.expt_datas
        if expt_is_valid and self._active_raw_data_id is not None and self._active_expt_data_id is not None:
            expt_is_valid = self.expt_datas[self._active_expt_data_id].raw_data_id == self._active_raw_data_id
        if not expt_is_valid:
            candidate = None
            if self._active_raw_data_id is not None:
                candidate = self._latest_matching_id(
                    self.expt_datas, lambda d: d.raw_data_id == self._active_raw_data_id
                )
            if candidate is None and self._active_model_id is not None:
                candidate = self._latest_matching_id(
                    self.expt_datas, lambda d: d.model_id == self._active_model_id
                )
            if candidate is None:
                candidate = self._latest_id(self.expt_datas)
            _set_active("_active_expt_data_id", candidate)

        if self._active_raw_data_id is None and self._active_expt_data_id in self.expt_datas and self._active_expt_data_id is not None:
            maybe_raw = self._normalize_uuid(self.expt_datas[self._active_expt_data_id].raw_data_id)
            if maybe_raw in self.raw_datas:
                _set_active("_active_raw_data_id", maybe_raw)

        # Fits: prefer active model + expt, then expt, then model, then any.
        _set_active("_active_fit_id", self._normalize_uuid(self._active_fit_id))
        fit_is_valid = self._active_fit_id in self.fits
        if fit_is_valid and self._active_fit_id is not None:
            afit = self.fits[self._active_fit_id]
            if self._active_model_id is not None and afit.model_id != self._active_model_id:
                fit_is_valid = False
            if self._active_expt_data_id is not None and afit.expt_data_id != self._active_expt_data_id:
                fit_is_valid = False
        if not fit_is_valid:
            candidate = None
            if self._active_model_id is not None and self._active_expt_data_id is not None:
                candidate = self._latest_matching_id(
                    self.fits,
                    lambda f: f.model_id == self._active_model_id and f.expt_data_id == self._active_expt_data_id,
                )
            if candidate is None and self._active_expt_data_id is not None:
                candidate = self._latest_matching_id(
                    self.fits, lambda f: f.expt_data_id == self._active_expt_data_id
                )
            if candidate is None and self._active_model_id is not None:
                candidate = self._latest_matching_id(
                    self.fits, lambda f: f.model_id == self._active_model_id
                )
            if candidate is None:
                candidate = self._latest_id(self.fits)
            _set_active("_active_fit_id", candidate)

        # Simulations: prefer active model then any.
        _set_active("_active_sim_id", self._normalize_uuid(self._active_sim_id))
        sim_is_valid = self._active_sim_id in self.simulations
        if sim_is_valid and self._active_model_id is not None and self._active_sim_id is not None:
            sim_is_valid = self.simulations[self._active_sim_id].model_id == self._active_model_id
        if not sim_is_valid:
            candidate = None
            if self._active_model_id is not None:
                candidate = self._latest_matching_id(
                    self.simulations, lambda s: s.model_id == self._active_model_id
                )
            if candidate is None:
                candidate = self._latest_id(self.simulations)
            _set_active("_active_sim_id", candidate)

        # MCMC: prefer active model + expt, then expt, then model, then any.
        _set_active("_active_mcmc_id", self._normalize_uuid(self._active_mcmc_id))
        mcmc_is_valid = self._active_mcmc_id in self.mcmcs
        if mcmc_is_valid and self._active_mcmc_id is not None:
            amcmc = self.mcmcs[self._active_mcmc_id]
            if self._active_model_id is not None and amcmc.model_id != self._active_model_id:
                mcmc_is_valid = False
            if self._active_expt_data_id is not None and amcmc.expt_data_id != self._active_expt_data_id:
                mcmc_is_valid = False
        if not mcmc_is_valid:
            candidate = None
            if self._active_model_id is not None and self._active_expt_data_id is not None:
                candidate = self._latest_matching_id(
                    self.mcmcs,
                    lambda m: m.model_id == self._active_model_id and m.expt_data_id == self._active_expt_data_id,
                )
            if candidate is None and self._active_expt_data_id is not None:
                candidate = self._latest_matching_id(
                    self.mcmcs, lambda m: m.expt_data_id == self._active_expt_data_id
                )
            if candidate is None and self._active_model_id is not None:
                candidate = self._latest_matching_id(
                    self.mcmcs, lambda m: m.model_id == self._active_model_id
                )
            if candidate is None:
                candidate = self._latest_id(self.mcmcs)
            _set_active("_active_mcmc_id", candidate)

        if reason and changes != {}:
            logger.info(f"Reconciled active IDs ({reason}): {changes}")
        return changes

    def _emit_active_context_events(self, changes: dict[str, tuple[uuid.UUID | None, uuid.UUID | None]]) -> None:
        if not changes:
            return
        self.notify_listeners("active_context_changed", changes)
        if "_active_model_id" in changes:
            self.update_ui_bindings(["model_name"])
            self.notify_listeners("model_changed")
        if "_active_expt_data_id" in changes or "_active_raw_data_id" in changes:
            self.notify_listeners("expt_data_changed")
            self.notify_listeners("data_imported")
        if "_active_fit_id" in changes:
            self.notify_listeners("fit_changed")
        if "_active_sim_id" in changes:
            self.notify_listeners("sim_changed")

    def _finalize_active_context(self, reason: str, emit_events: bool = True) -> dict[str, tuple[uuid.UUID | None, uuid.UUID | None]]:
        changes = self._reconcile_active_ids(reason=reason)
        if emit_events:
            self._emit_active_context_events(changes)
        return changes

    def reconcile_active_context(self, reason: str = "manual", emit_events: bool = True) -> dict[str, tuple[uuid.UUID | None, uuid.UUID | None]]:
        """Public wrapper to reconcile and optionally emit active-context events."""
        return self._finalize_active_context(reason=reason, emit_events=emit_events)

    def _delete_object_core(self, obj: Model | FitResult | Simulation | ExptData | RawData | MCMCSim) -> None:
        """Delete an object and dependent objects without emitting events."""
        if isinstance(obj, Model):
            if obj.id in self.models:
                del self.models[obj.id]
                if self._active_model_id == obj.id:
                    self._active_model_id = None
        elif isinstance(obj, FitResult):
            if obj.id in self.fits:
                del self.fits[obj.id]
                if self._active_fit_id == obj.id:
                    self._active_fit_id = None
        elif isinstance(obj, Simulation):
            if obj.id in self.simulations:
                del self.simulations[obj.id]
                if self._active_sim_id == obj.id:
                    self._active_sim_id = None
        elif isinstance(obj, ExptData):
            if obj.id in self.expt_datas:
                del self.expt_datas[obj.id]
                if self._active_expt_data_id == obj.id:
                    self._active_expt_data_id = None
        elif isinstance(obj, RawData):
            if obj.id in self.raw_datas:
                del self.raw_datas[obj.id]
                if self._active_raw_data_id == obj.id:
                    self._active_raw_data_id = None
        elif isinstance(obj, MCMCSim):
            if obj.id in self.mcmcs:
                del self.mcmcs[obj.id]
                if self._active_mcmc_id == obj.id:
                    self._active_mcmc_id = None
        else:
            raise TypeError("Expected an instance of Model, FitResult, Simulation, ExptData, RawData, or MCMCSim.")

        self.clean_up_dependencies_for_obj(obj)

    def delete_object(self, obj: Model | FitResult | Simulation | ExptData | RawData | MCMCSim) -> None:
        """Compatibility wrapper; prefer typed delete methods."""
        logger.warning("delete_object is a low-level API. Prefer typed delete methods.")
        before = self._snapshot_object_ids()
        self._delete_object_core(obj)
        after = self._snapshot_object_ids()
        self._emit_collection_events(before, after, notify_listeners=True)
        self._finalize_active_context(reason="delete_object", emit_events=True)

    def clean_up_dependencies_for_obj(self, obj: Model | FitResult | Simulation | ExptData | RawData | MCMCSim) -> None:
        """Clean up dependencies when an object is deleted."""
        objs_to_delete = []
        
        if isinstance(obj, MCMCSim):
            pass # nothing to do
        elif isinstance(obj, Simulation):
            pass # nothing to do
        elif isinstance(obj, FitResult):
            pass # nothing to do
        elif isinstance(obj, ExptData):
            for fit in list(self.fits.values()):
                if fit.expt_data_id == obj.id:
                    objs_to_delete.append(fit)
            for mcmc in list(self.mcmcs.values()):
                if mcmc.expt_data_id == obj.id:
                    objs_to_delete.append(mcmc)
        elif isinstance(obj, RawData):
            for expt_data in list(self.expt_datas.values()):
                if expt_data.raw_data_id == obj.id:
                    objs_to_delete.append(expt_data)
        elif isinstance(obj, Model):
            for sim in list(self.simulations.values()):
                if sim.model_id == obj.id:
                    objs_to_delete.append(sim)
            for fit in list(self.fits.values()):
                if fit.model_id == obj.id:
                    objs_to_delete.append(fit)
            for expt_data in list(self.expt_datas.values()):
                if expt_data.model_id == obj.id:
                    objs_to_delete.append(expt_data)
            for mcmc in list(self.mcmcs.values()):
                if mcmc.model_id == obj.id:
                    objs_to_delete.append(mcmc)
        
        for o in objs_to_delete:
            self._delete_object_core(o)

    @property
    def active_model(self) -> Model:
        """Get the currently active model."""
        if self._active_model_id is None or self._active_model_id not in self.models:
            raise IndexError("No active model set.")
        return self.models[self._active_model_id]

    @property
    def active_model_id(self) -> uuid.UUID | None:
        """Get the ID of the currently active model."""
        return self._active_model_id

    @active_model_id.setter
    def active_model_id(self, id: uuid.UUID | str | None) -> None:
        """Set the active model index and update the active model."""
        if id is not None:
            if isinstance(id,str):
                id = uuid.UUID(id)
            if not isinstance(id, uuid.UUID):
                raise TypeError("Expected a UUID for active model ID.")
            if id not in self.models:
                raise ValueError(f"Model with ID {id} does not exist.")
        self._active_model_id = id
        self.update_ui_bindings(["model_name",])
        # self.active_model = self.models[value]  # Set the active model based on the index
        # self.active_model_dict.update(self.active_model.to_dict())  # Update active_model with the new model's data


    @property
    def expt_data(self):
        """Get the experimental data."""
        logger.warning("Deprecated L109  expt_data getter sm")
        return self.active_expt_data

    @expt_data.setter
    def expt_data(self, value):
        """Set the experimental data."""
        # if isinstance(value, ExptData):
        #     self._expt_data = value
        logger.warning("Deprecated L117 expt_data setter sm")
        raise NotImplementedError("Use add_expt_data instead")
#        else:
#         raise TypeError("Expected an instance of ExptData.")

    @property
    def active_sim_id(self) -> uuid.UUID|None:
        return self._active_sim_id

    @active_sim_id.setter
    def active_sim_id(self, value: uuid.UUID | str | None ) -> None:
        if value is not None:
            if isinstance(value, str):
                value = uuid.UUID(value)
            if not isinstance(value, uuid.UUID):
                raise TypeError("Expected a UUID for active simulation ID.")
            if value not in self.simulations:
                raise IndexError("Active simulation index does not exist in state.")
        self._active_sim_id = value

    @property
    def active_simulation(self) -> Simulation|None:
        """Get the currently active simulation."""
        return self.active_sim

    @property
    def active_sim(self) -> Simulation|None:
        if self.active_sim_id is None:
            return None
        if self.active_sim_id in self.simulations:
            return self.simulations[self.active_sim_id]
        else:
            raise ValueError("Active simulation ID not present in simulation list.")

    @property
    def active_expt_data_id(self) -> Optional[uuid.UUID]:
        return self._active_expt_data_id

    @active_expt_data_id.setter
    def active_expt_data_id(self, value: uuid.UUID | str | None) -> None:
        if value is not None:
            if isinstance(value,str):
                value = uuid.UUID(value)
            if not isinstance(value,uuid.UUID):
                raise TypeError("Expected a UUID for active expt_data ID.")
            if value not in self.expt_datas:
                raise IndexError("Active expt_data index does not exist in state.")
        self._active_expt_data_id = value

    @property
    def active_expt_data(self) -> ExptData :
        """Get the currently active ExptData."""
        if self._active_expt_data_id is None:
            raise IndexError("No active ExptData set.")
            # new_obj = ExptData()
            # self.add_expt_data(new_obj)
            # self.active_expt_data_id = new_obj.id  # Set the active model to the newly created one
            # return new_obj
        else:
            return(self.expt_datas[self._active_expt_data_id])

    @property 
    def active_raw_data_id(self) -> Optional[uuid.UUID]:
        return self._active_raw_data_id
    
    @active_raw_data_id.setter
    def active_raw_data_id(self, value: uuid.UUID | str | None) -> None:
        if value is not None:
            if isinstance(value,str):
                value = uuid.UUID(value)
            if not isinstance(value,uuid.UUID):
                raise TypeError("Expected a UUID for active raw_data ID.")
            if value not in self.raw_datas:
                raise IndexError("Active raw_data index out of range")
        self._active_raw_data_id =value

    @property
    def active_raw_data(self) -> Optional[RawData]:
        if self.active_raw_data_id is None:
            return None
        if self.active_raw_data_id in self.raw_datas:
            return self.raw_datas[self.active_raw_data_id]
        else:
            raise ValueError(f"Active raw_data id {self.active_raw_data_id} does not exist.")

    @property
    def active_fit_id(self) -> Optional[uuid.UUID]:
        if self._active_fit_id is None:
            return None
        else:
            return self._active_fit_id
    
    @active_fit_id.setter
    def active_fit_id(self, value: uuid.UUID | str | None) -> None:
        if value is not None:
            if isinstance(value,str):
                value=uuid.UUID(value)
            if not isinstance(value,uuid.UUID):
                raise TypeError("Expected a UUID for active fit ID.")
            if value not in self.fits:
                raise IndexError("Active fit index out of range.")
        self._active_fit_id = value

    @property
    def active_fit(self) -> FitResult:
        """Get the currently active fit."""
        if self.active_fit_id is None:
            raise IndexError("No active fit set.")
        elif self.active_fit_id in self.fits:
            return self.fits[self.active_fit_id]
        else:
            raise(IndexError("Active fit ID not present in fit list."))

    @property
    def active_mcmc_id(self) -> Optional[uuid.UUID]:
        return self._active_mcmc_id
    
    @active_mcmc_id.setter
    def active_mcmc_id(self, value: uuid.UUID | str | None) -> None:
        if value is not None:
            if isinstance(value,str):
                value=uuid.UUID(value)
            if not isinstance(value,uuid.UUID):
                raise TypeError("Expected a UUID for active mcmc ID.")
            if value not in self.mcmcs:
                raise IndexError("Active mcmc index out of range.")
        self._active_mcmc_id = value
    
    @property
    def active_mcmc(self) -> MCMCSim:
        """Get the currently active mcmc."""
        if self.active_mcmc_id is None:
            raise IndexError("No active mcmc set.")
        elif self.active_mcmc_id in self.mcmcs:
            return self.mcmcs[self.active_mcmc_id]
        else:
            raise(IndexError("Active mcmc ID not present in mcmc list."))

    @property
    def active_sim_or_none(self) -> Simulation | None:
        if self.active_sim_id is None:
            return None
        try:
            return self.active_sim
        except Exception:
            return None

    @property
    def active_expt_data_or_none(self) -> ExptData | None:
        if self.active_expt_data_id is None:
            return None
        try:
            return self.active_expt_data
        except Exception:
            return None

    @property
    def active_raw_data_or_none(self) -> RawData | None:
        if self.active_raw_data_id is None:
            return None
        try:
            return self.active_raw_data
        except Exception:
            return None

    @property
    def active_fit_or_none(self) -> FitResult | None:
        if self.active_fit_id is None:
            return None
        try:
            return self.active_fit
        except Exception:
            return None

    @property
    def active_mcmc_or_none(self) -> MCMCSim | None:
        if self.active_mcmc_id is None:
            return None
        try:
            return self.active_mcmc
        except Exception:
            return None

    @property
    def model_name(self):
        return self.active_model.name if isinstance(self.active_model, Model) else ""

    @model_name.setter
    def model_name(self, value):
        if self.active_model is not None:
            self.active_model.name = value
            self._model_name = value
        else:
            self._model_name = value

    @property
    def eq_mat(self):
        return (
            self.active_model.eq_mat
            if isinstance(self.active_model, Model)
            else self._eq_mat
        )

    @eq_mat.setter
    def eq_mat(self, value):
        if self.active_model is not None:
            self.active_model.eq_mat = value
            self._eq_mat = value
        else:
            self._eq_mat = value

    @property
    def nComp(self):
        return (
            self.active_model.nComp
            if isinstance(self.active_model, Model)
            else self._nComp
        )

    @nComp.setter
    def nComp(self, value):
        if self.active_model is not None:
            self.active_model.nComp = value
            self._nComp = value
        else:
            self._nComp = value

    @property
    def nStep(self):
        return (
            self.active_model.nStep
            if isinstance(self.active_model, Model)
            else self._nStep
        )

    @nStep.setter
    def nStep(self, value):
        if self.active_model is not None:
            self.active_model.nStep = value
            self._nStep = value
        else:
            self._nStep = value

    @property
    def eq_str(self):
        return (
            self.active_model.eq_str
            if isinstance(self.active_model, Model)
            else self._eq_str
        )

    @eq_str.setter
    def eq_str(self, value):
        if self.active_model is not None:
            self.active_model.eq_str = value
            self._eq_str = value
        else:
            self._eq_str = value

    @property
    def eq_mat_str(self):
        return (
            self.active_model.eq_mat_str
            if isinstance(self.active_model, Model)
            else self._eq_mat_str
        )

    @eq_mat_str.setter
    def eq_mat_str(self, value):
        if self.active_model is not None:
            self.active_model.eq_mat_str = value
            self._eq_mat_str = value
        else:
            self._eq_mat_str = value

    @property
    def components(self):
        return (
            self.active_model.components
            if isinstance(self.active_model, Model)
            else self._components
        )

    @components.setter
    def components(self, value):
        if self.active_model is not None:
            self.active_model.components = value
            self._components = value
        else:
            self._components = value

    @property
    def species(self):
        return (
            self.active_model.species
            if isinstance(self.active_model, Model)
            else self._species
        )

    @species.setter
    def species(self, value):
        if self.active_model is not None:
            self.active_model.species = value
            self._species = value
        else:
            self._species = value

    @property
    def comp_concs(self):
        return (
            self.active_model.component_concs
            if isinstance(self.active_model, Model)
            else self._comp_concs
        )

    @comp_concs.setter
    def comp_concs(self, value):
        if self.active_model is not None:
            self.active_model.component_concs = value
            self._comp_concs = value
        else:
            self._comp_concs = value

    @property
    def binding_constants(self):
        return (
            self.active_model.binding_constants
            if isinstance(self.active_model, Model)
            else self._binding_constants
        )

    @binding_constants.setter
    def binding_constants(self, value):
        if self.active_model is not None:
            self.active_model.binding_constants = value
            self._binding_constants = value
        else:
            self._binding_constants = value

    @property
    def component_names(self):
        return (
            self.active_model.component_names
            if isinstance(self.active_model, Model)
            else self._component_names
        )

    @component_names.setter
    def component_names(self, value):
        if self.active_model is not None:
            self.active_model.component_names = value
            self._component_names = value
        else:
            self._component_names = value


    def add_model(self, model: Model, emit_events: bool = True) -> None:
        """Add a model to the state manager."""
        if not isinstance(model, Model):
            raise TypeError("Expected a Model instance.")
        self.models[model.id] = model  # Use UUID as key
        self.active_model_id = model.id
        self._finalize_active_context(reason="add_model", emit_events=emit_events)

    def add_fit(self, fit: FitResult, emit_events: bool = True) -> None:
        """Add a fit result to the state manager."""
        if not isinstance(fit, FitResult):
            raise TypeError("Expected a FitResult instance.")
        self.fits[fit.id] = fit
        self.active_fit_id = fit.id  # Set the newly added fit as active
        self._finalize_active_context(reason="add_fit", emit_events=emit_events)
    
    def add_sim(self, sim: Simulation, emit_events: bool = True) -> None:
        """Add a simulation to the state manager."""
        if not isinstance(sim, Simulation):
            raise TypeError("Expected a Simulation instance.")
        self.simulations[sim.id]=sim
        self.active_sim_id = sim.id
        self._finalize_active_context(reason="add_sim", emit_events=emit_events)

    def add_expt_data(self, expt_data: ExptData, emit_events: bool = True) -> None:
        """Add experimental data to the state manager."""
        if not isinstance(expt_data, ExptData):
            raise TypeError("Expected an ExptData instance.")
        self.expt_datas[expt_data.id]=expt_data
        self.active_expt_data_id = expt_data.id
        self.active_expt_data.col_details = {k: self.active_expt_data.col_details[k] if k in self.active_expt_data.col_details else {'depindep': None} for k in self.active_expt_data.data.columns}
        self._finalize_active_context(reason="add_expt_data", emit_events=emit_events)


    def add_raw_data(self, raw_data: RawData, emit_events: bool = True) -> None: 
        """Add raw data to the state manager."""
        if not isinstance(raw_data, RawData):
            raise TypeError("Expected a RawData instance.")
        if raw_data.id in self.raw_datas:
            raise ValueError(f"RawData with id {raw_data.id} already exists.")
        self.raw_datas[raw_data.id] = raw_data
        self.active_raw_data_id = raw_data.id
        self._finalize_active_context(reason="add_raw_data", emit_events=emit_events)

    def add_mcmc(self, mcmc: MCMCSim, emit_events: bool = True) -> None:
        """Add a MCMC result to the state manager."""
        if not isinstance(mcmc, MCMCSim):
            raise TypeError("Expected an MCMCSim instance.")
        self.mcmcs[mcmc.id] = mcmc
        self.active_mcmc_id = mcmc.id
        self._finalize_active_context(reason="add_mcmc", emit_events=emit_events)

    def add_expt_data_type(self, expt_data_type: ExptDataType) -> None:
        """Add an experimental data type to the state manager."""
        if not isinstance(expt_data_type, ExptDataType):
            raise TypeError("Expected an ExptDataType instance.")
        if expt_data_type.name.lower() in self._expt_dtypes:
            raise ValueError(f"ExptDataType with name {expt_data_type.name} already exists.")
        self._expt_dtypes[expt_data_type.name] = expt_data_type

    def _init_bindables(self):
        # """Initialize bindable attributes."""

        self._nComp: int = 2
        self._nComp: int = 2  # Number of components
        self._nStep: int = 20
        self._eq_str = ""
        self._eq_consts = None  # Optional attribute for equilibrium constants
        self._model_name = ""
        self._comp_concs = pd.DataFrame({})
        self._components = []
        self._eq_mat = np.array([])  # Initialize eqMat as an empty array
        self._binding_constants = []
        self._species = []
        self._component_names = []
        self._eq_mat_str = ""

    def new_model(self, name="New model") -> uuid.UUID:
        """Create a new model and set it as the active model."""
        existing_names = [model.name for model in self.models.values()]
        if name in existing_names:
            n_models_with_name = len([
                model for model in self.models.values() if model.name.startswith(name)])
            name = f"{name} ({n_models_with_name})"  # Append a number to the name if it already exists

        new_model = Model(name=name,
                          nComp=self.nComp,
                          nStep=self.nStep,
                          component_concs=self.comp_concs.copy(),
                          component_names=self.component_names.copy(),
                          components=self.components.copy(),
        )

        self.add_model(new_model)
        
        return new_model.id

    def _default_models_path(self) -> str:
        if getattr(sys, 'frozen', False):
            # PyInstaller onefile: data files are extracted to sys._MEIPASS
            return os.path.join(getattr(sys, '_MEIPASS'), 'webgui', 'default_models.json')
        return os.path.join(os.path.dirname(__file__), '..', 'default_models.json')

    def _load_default_models_data(self) -> dict[str, Any]:
        with open(self._default_models_path(), 'r') as f:
            return json.load(f)

    def _default_model_ids_from_bundle(self) -> set[uuid.UUID]:
        ids: set[uuid.UUID] = set()
        try:
            default_models_data = self._load_default_models_data()
        except Exception as e:
            logger.warning(f"Could not load bundled default model IDs: {e}")
            return ids
        for model_data in default_models_data.get("models", []):
            mid = self._normalize_uuid(model_data.get("id"))
            if mid is not None:
                ids.add(mid)
        return ids

    def _initialize_default_models(self, emit_events: bool = True):
        """Initialize with default models."""
        self.default_model_ids = []
        try:
            default_models_data = self._load_default_models_data()
        except Exception as e:
            logger.error(f"Error loading default models: {e}")
            raise RuntimeError("Unable to initialize built-in models.") from e

        # Create models from the loaded data
        for model_data in default_models_data.get('models', []):
            model = Model(**model_data)
            # Reconstruct complex objects
            model.components = [Component(**comp) for comp in model_data.get("components", [])]
            model.binding_constants = [BindingConstant(**k) for k in model_data.get("binding_constants", [])]
            model.eq_mat = np.array(model_data.get("eq_mat", []))
            model.component_concs = pd.DataFrame(model_data.get("component_concs", {}))
            self.add_model(model, emit_events=emit_events)
            self.default_model_ids.append(model.id)

        if len(self.models) == 0:
            raise RuntimeError("No built-in models were loaded.")

        logger.info(f"Loaded {len(self.default_model_ids)} default models")

    # def _set_initial_simFig_style(self):
    #     """Set the initial style for the simulation figure."""
    #     self.simFig_data = {
    #         'data': [],
    #         'layout': {
    #             'margin': {'l':50, 'r':0, 'b':20, 't':0},
    #             'plot_bgcolor': '#E5ECF6',
    #             'legend': {'y': .95},
    #             'xaxis': {'title': 'x-axis'},
    #             'yaxis': {'title': 'y-axis'},
    #             },
    #         }

    async def new_project(self):
        """Create a new project."""
        try:
            with ui.dialog() as dialog, ui.card():
                ui.label("Create new project? Unsaved changes will be lost.")
                with ui.row():
                    ui.button("Yes", on_click=lambda: dialog.submit(True))
                    ui.button("No", on_click=lambda: dialog.submit(False))

            result = await dialog
            if result:
                # Reset the UIState and reload the page
                # self.sd = UIState()  # Reset the SimData instance
                app.storage.user["state-data_old"] = app.storage.user.get("state-data", "")
                self.__init__(load_prior_state=False) # Reinitialize the StateManager

              #  self.simFig_data["data"] = []  # Clear the simulation figure data
              #  self.simFig.update()
                app.storage.user["state-data"] = self.to_json()
                ui.navigate.reload()
            else:
                ui.notify("New project creation cancelled", type="info")
        except Exception as e:
            logger.error(f"Error creating new project: {str(e)}")
            ui.notify("Failed to create new project", type="negative")

    async def open_project(self):
        """Open an existing project."""
        try:

            with ui.dialog() as dialog, ui.card():
                ui.label("Open Project File")
                upload_box = ui.upload(label="Choose file", auto_upload=True).props(
                    'accept=".json, .json.gz"'
                )
                ui.button("Cancel", on_click=lambda: dialog.submit("cancel"))

                def on_upload_complete(e: UploadEventArguments) -> None:
                    dialog.submit(e)  # Store result for later

                upload_box.on_upload(on_upload_complete)

            result: UploadEventArguments|str= await dialog

            if isinstance(result, str) and result == "cancel":
                ui.notify("Project loading cancelled", type="info")
                return
            elif isinstance(result, UploadEventArguments):
                filename = result.file.name

                if filename.endswith(".gz"):
                    file_content = await result.file.read()
                    with gzip.GzipFile(fileobj=io.BytesIO(file_content), mode="rb") as gz:
                        file_content = gz.read().decode("utf-8")
                else:
                    file_content = await result.file.text("utf-8")

                app.storage.user["state-data"] = file_content
                try:
                    self.load_storage_into_state()
                except Exception as e:
                    logger.error(f"Error loading model data: {e}")
                #ui.navigate.reload()
                ui.notify("Project loaded successfully", type="info")
            else:
                raise RuntimeError("Unexpected result type from dialog submission.")

        except Exception as e:
            logger.error(f"Error opening project: {str(e)}")
            ui.notify("Failed to open project", type="negative")

    def save_to_storage(self, e=None):
        """Save the current state to user storage."""
        app.storage.user["state-data"] = self.to_json()

    async def save_project(self):
        """Save the current project."""
        logger.info("saving...")
        self.save_to_storage()  # Save the current state to user storage

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        buffer = io.BytesIO()

        with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
            gz.write(app.storage.user["state-data"].encode("utf-8"))

        # Ensure data is flushed and gzip stream is closed before reading
        buffer.seek(0)
        filename = f"bindtools_project_{timestamp}.json.gz"
        ui.download.content(buffer.read(), filename=filename)
        ui.notify(f"Project saved as {filename}", type="info")

    def to_json(self):
        return json.dumps(self.to_dict())

    def to_dict(self):
        """Convert the state to a dictionary."""
        return {
            #"simFig_data": self.simFig_data if hasattr(self, "simFig_data") else {},
            #"simFig": self.simFig.to_dict() if hasattr(self, "simFig") else {},
            "nComp": int(self.nComp),
            "nStep": int(self.nStep),
            "eq_str": self.eq_str,
            "eq_mat": (
                self.eq_mat.tolist() if isinstance(self.eq_mat, np.ndarray) else []
            ),  # Convert numpy arrays to lists
            "eq_mat_str": (
                self.eq_mat_str if hasattr(self, "eq_mat_str") else ""
            ),  # Optional attribute
            "components": (
                [asdict(comp) for comp in self.components]
                if hasattr(self, "components")
                else []
            ),  # Convert Component objects to dicts
            "species": (
                self.species if hasattr(self, "species") else []
            ),  # Optional attribute
            # "eq_consts": (
            #     self.eq_consts if hasattr(self, "eq_consts") else None
            # ),  # Optional attribute
            "model_name": self.model_name,
            "comp_concs": self.comp_concs.to_dict(orient="list"),
            "binding_constants": (
                [asdict(k) for k in self.binding_constants]
                if hasattr(self, "binding_constants")
                else []
            ),
            "component_names": (
                self.component_names if hasattr(self, "component_names") else []
            ),  # Optional attribute
            "models": (
                [model.to_dict() for model in self.models.values()]
                if hasattr(self, "models")
                else []
            ),  # Optional attribute
            "simulations": (
                [sim.to_dict() for sim in self.simulations.values()]
                if hasattr(self, "simulations")
                else []
            ),  # List of simulations
            "raw_datas": (
                [raw_data.to_dict() for raw_data in self.raw_datas.values()]
                if hasattr(self, "raw_datas")
                else []
            ),  # List of raw data
            "expt_datas": (
                [expt_data.to_dict() for expt_data in self.expt_datas.values()]
                if hasattr(self, "expt_datas")
                else []
            ),  # List of experimental data
            "_expt_dtypes": (
                {name: asdict(dtype) for name, dtype in self._expt_dtypes.items()}
                if hasattr(self, "_expt_dtypes")
                else {}
            ),  # Dictionary of experimental data types
            "fits": (
                [fit.to_dict() for fit in self.fits.values()]
                if hasattr(self, "fits")
                else []
            ),  # List of fits
            "mcmcs": (
                [
                    {
                        "id": str(m.id),
                        "nwalkers": m.nwalkers,
                        "nsteps_target": m.nsteps_target,
                        "burn": m.burn,
                        "thin": m.thin,
                        "seed": m.seed,
                        "chains": m.chains.tolist() if isinstance(m.chains, np.ndarray) else [],
                        "priors": m.priors,
                        "model_id": str(m.model_id) if m.model_id else None,
                        "expt_data_id": str(m.expt_data_id) if m.expt_data_id else None,
                        "nsteps_done": m.nsteps_done,
                    }
                    for m in self.mcmcs.values()
                ]
                if hasattr(self, "mcmcs")
                else []
            ),
            "active_model_id": (
                str(self.active_model_id) if hasattr(self, "_active_model_id") else None
            ),  # Index of the active model
            "active_sim_id": (
                str(self.active_sim_id) if hasattr(self, "_active_sim_id") else None
            ),  # Index of the active simulation
            "active_expt_data_id": (
                str(self.active_expt_data_id) if hasattr(self, "_active_expt_data_id") else None
            ),  # Index of the active experimental data
            "active_fit_id": (
                str(self.active_fit_id) if hasattr(self, "_active_fit_id") else None
            ),  # Index of the active fit
            "active_raw_data_id": (
                str(self.active_raw_data_id) if hasattr(self, "_active_raw_data_id") else None
            ),
            "active_mcmc_id": (
                str(self.active_mcmc_id) if hasattr(self, "_active_mcmc_id") else None
            ),
            "default_model_ids": (
                [str(m) for m in self.default_model_ids]
                if hasattr(self,"default_model_ids")
                else
                []
            )
        }

    def from_json(self, json_str: str) -> None:
        """Load the state from a JSON string."""
        data = json.loads(json_str)
        mtemp = data.get("models", [])
        self.models = {}
        if mtemp:
            for model in mtemp:
                self.add_model(Model(**model), emit_events=False)
                m_id = uuid.UUID(model['id'])
                self.models[m_id].components = [
                    Component(**comp) for comp in model.get("components", [])
                ]
                self.models[m_id].binding_constants = [
                    BindingConstant(**k) for k in model.get("binding_constants", [])
                ]
                self.models[m_id].eq_mat = np.array(
                    model.get("eq_mat", [])
                )  # Convert numpy arrays to lists
                self.models[m_id].component_concs = pd.DataFrame(
                    model.get("component_concs", {})
                )


        self.simulations = {}
        simtemp = data.get("simulations", [])
        if simtemp:
            for sim in simtemp:
                simulation = Simulation(**sim)
                simulation.model_id = uuid.UUID(sim.get("model_id"))
                simulation.comp_concs = pd.DataFrame(sim.get("comp_concs", {}))
                # simulation.model = Model(**sim.get("model", {}))
                # simulation.params = [BindingConstant(**k) for k in sim.get('params', [])]
                simulation.results = pd.DataFrame(sim.get("results", {}))
                self.simulations[simulation.id]=simulation

        self.fits = {}
        fittemp = data.get("fits", [])  # List of fits  
        if fittemp:
            for fit in fittemp:
                fit_result = FitResult(**fit)
                fit_result.fit_speciation = pd.DataFrame(
                    fit.get("fit_speciation", {}))
                fit_result.calc_obs = pd.DataFrame(
                    fit.get("calc_obs", {}))
                self.fits[fit_result.id]=fit_result

        self.mcmcs = {}
        mcmc_temp = data.get("mcmcs", [])
        if mcmc_temp:
            for mcmc in mcmc_temp:
                try:
                    mcmc_obj = MCMCSim(**mcmc)
                    if not isinstance(mcmc_obj.chains, np.ndarray):
                        mcmc_obj.chains = np.array(mcmc_obj.chains)
                    mcmc_obj.model_id = self._normalize_uuid(mcmc_obj.model_id)
                    mcmc_obj.expt_data_id = self._normalize_uuid(mcmc_obj.expt_data_id)
                    self.mcmcs[mcmc_obj.id] = mcmc_obj
                except Exception as e:
                    logger.warning(f"Skipping invalid serialized MCMC entry: {e}")

        rawtemp = data.get("raw_datas", [])  # List of raw data
        self.raw_datas = {}
        if rawtemp:
            for raw in rawtemp:
                raw_data = RawData(**raw)
                raw_data.data = pd.DataFrame(
                    raw.get("data", {})
                )
                self.raw_datas[raw_data.id] = raw_data  # Store by UUID

        expttemp = data.get("expt_datas", [])  # List of experimental data
        self.expt_datas = {}
        if expttemp:
            for expt in expttemp:
                # Ensure backward compatibility - add selected_columns if missing
                if 'selected_columns' not in expt:
                    expt['selected_columns'] = []
                    
                expt_data = ExptData(**expt)
                # limiting_shifts now serialized as list of ChemicalShiftParam dicts
                expt_data.limiting_shifts = {}
                for cs in expt.get("limiting_shifts", []) or []:
                    csp = ChemicalShiftParam(**cs)
                    key = (csp.species, csp.col)
                    expt_data.limiting_shifts[key] = csp

                # Reconstruct delta_to_spec (object ndarray with floats or lmfit Parameters)
                serialized_delta = expt.get("delta_to_spec", [])
                if serialized_delta == []:
                    expt_data.delta_to_spec = None
                elif isinstance(serialized_delta, list) and serialized_delta:
                    # Expect a list of rows
                    new_rows: list[list[LMFitParameter|float]] = []
                    for row in serialized_delta:
                        reconstructed_row: list[LMFitParameter|float] = []
                        for cell in row:
                            if isinstance(cell, dict) and cell.get("type") == "lmfit_param":
                                # Construct lmfit Parameter
                                parameter = LMFitParameter(
                                    name=cell.get("name", ""),
                                    value=float(cell.get("value", 0.0)),
                                )
                                if cell.get("min") is not None:
                                    parameter.min = float(cell["min"])  # type: ignore[index]
                                if cell.get("max") is not None:
                                    parameter.max = float(cell["max"])  # type: ignore[index]
                                parameter.vary = bool(cell.get("vary", True))
                                reconstructed_row.append(parameter)
                            elif cell is None:
                                reconstructed_row.append(0.0)
                            elif isinstance(cell,(str, int, float)):
                                try:
                                    reconstructed_row.append(float(cell))
                                except Exception:
                                    logger.warning(f"Failed to convert cell {cell} to float, appending 0.0")
                                    reconstructed_row.append(0.0)
                        new_rows.append(reconstructed_row)
                    try:
                        nr = len(new_rows)
                        nc = len(new_rows[0]) if nr > 0 else 0
                        # Attempt to create a 2D numpy array with dtype=object
                        # need to do this long-winded approach to stop numpy from
                        # trying (and failing) to coerce the object array to a float array
                        # which calls Parameter.__array__ and fails.
                        if nc > 0:
                            expt_data.delta_to_spec = np.empty((nr, nc), dtype=object)
                            for i in range(nr):
                                for j in range(nc):
                                    expt_data.delta_to_spec[i, j] = new_rows[i][j]
                        #expt_data.delta_to_spec = np.array(new_rows, dtype=object)
                    except Exception:
                        # If object array fails, still set as object array coercing to objects
                        expt_data.delta_to_spec = np.array([[x for x in row] for row in new_rows], dtype=object)
                self.expt_datas[expt_data.id]=expt_data

        self._nComp = int(data.get("nComp", 2))
        self._nStep = int(data.get("nStep", 20))
        self._eq_str = data.get("eq_str", "")
        self._eq_mat_str = data.get("eq_mat_str", "[]")
        self._eq_mat = np.array(data.get("eq_mat", []))
        comp_temp = data.get("components", [])
        self._components = (
            [Component(**comp) for comp in comp_temp] if comp_temp else []
        )
        ktemp = data.get("binding_constants", [])
        self._binding_constants = [BindingConstant(**k) for k in ktemp] if ktemp else []
        self._species = data.get("species", [])
        self._eq_consts = data.get("eq_consts", None)
        self._model_name = data.get("model_name", "")
        self._component_names = data.get("component_names", [])
        self._comp_concs = pd.DataFrame(data.get("comp_concs", {}))
        self._expt_data = ExptData(**data.get("expt_data", {}))
        self._active_model_id = self._normalize_uuid(data.get("active_model_id", None))
        self._active_sim_id = self._normalize_uuid(data.get("active_sim_id", None))
        self._active_fit_id = self._normalize_uuid(data.get("active_fit_id", None))
        self._active_raw_data_id = self._normalize_uuid(data.get("active_raw_data_id", None))
        self._active_expt_data_id = self._normalize_uuid(data.get("active_expt_data_id", None))
        self._active_mcmc_id = self._normalize_uuid(data.get("active_mcmc_id", None))

        mids = data.get("default_model_ids", None)
        if mids:
            self.default_model_ids = [uuid.UUID(m) for m in mids]
        else:
            # Backward compatibility for older saved states without default_model_ids.
            # Any model ID that matches the bundled defaults is treated as built-in.
            bundled_default_ids = self._default_model_ids_from_bundle()
            self.default_model_ids = [mid for mid in self.models.keys() if mid in bundled_default_ids]

        #self._active_raw_data_id = data.get("active_raw_data_id", None)
        for name, dtype in data.get("_expt_dtypes", {}).items():
            self._expt_dtypes[name] = ExptDataType(**dtype)

        self._finalize_active_context(reason="from_json", emit_events=False)
 
    def resolve_str_None(self, id: uuid.UUID | str | None):
        if id == "None":
            id = None
        return id

    # def parse_equations(self, e=None):
    #     """Parse the equilibrium equations and update the model data output."""
    #     # This method is now async to allow for UI interactions
    #     return self._parse_equations(e)

    async def parse_equations(self, e):
        """Parse the equilibrium equations and update the model data output."""

        # if current model_name is already a model, ask the user if they want to overwrite
        if self.model_name in [m.name for m in self.models.values()]:
            #model = [m for m in self.models if m.name == self.model_name][0]
            model = self.active_model
            if model.eq_mat_str == "" or model.eq_mat is np.array([]):
                # then this is a new model and we don't need to ask about overwriting
                pass
            # otherwise, we need to ask the user if they want to overwrite the model
            else:
                with ui.dialog() as dialog, ui.card():
                    ui.label(
                        f"Are you sure you want to overwrite model \"{self.model_name}\"? \nDoing so will delete all simulations and fits which rely on this model."
                    )
                    with ui.row():
                        ui.button("Yes", on_click=lambda: dialog.submit(True))
                        ui.button("No", on_click=lambda: dialog.submit(False))

                async def show():
                    result = await dialog
                    return result

                res = await show()
                if res is False:  # i.e. user does not want to save
                    ui.notify(
                        "Please give a unique model name and re-try.", type="info"
                    )
                    return
                else:
                    ui.notify(f"Overwriting model {self.model_name}", type="warning")

        eq_input = self.active_model.eq_str.strip() if self.active_model.eq_str else ""

        if not eq_input:
            ui.notify("Please enter equilibrium equations.", type="negative")
            return
        try:
            eq_matrix, component_names, species = eq_mat_from_equation_str_infer_components(
                eq_input
            )
            model = self.active_model
            nmodel = len(self.models)
            self.delete_model(self.active_model, notify_user=False, notify_listeners=True)
            if nmodel==1:
                # if  we had only one model, then deletion would have initialized a default model
                # since we cannot have zero models. 
                self.active_model.name = model.name  # Set the name of the default model
            else:
                self.new_model(name=model.name)  # Create a new model with the same name
            self.active_model.eq_str = model.eq_str  # Copy the equilibrium string from the old model
            self.active_model.nComp = model.nComp  # Copy the number of components from the old model
            self.active_model.nStep = model.nStep  # Copy the number of steps from the
            self.active_model.component_concs = model.component_concs  # Copy the component concentrations from the old model
            self.active_model.component_names = model.component_names  # Copy the component names from the old model
            self.active_model.components = model.components  # Copy the components from the old model
            #self.notify_listeners('model_changed')  # Notify listeners that the model has been updated
            #self.active_model_idx = self.models.index(model)



            self.active_model.eq_mat = eq_matrix
            # TODO replace next line with a property
            self.active_model.eq_mat_str = str(eq_matrix.tolist()).replace(
                "],", "]\n"
            )  # Convert to list for display
            self.species = species
            self.component_names = component_names

            self.active_model.nComp = len(component_names)  # Update number of components in SimData
            #    self.modelData.set_visibility(True)  # Show the model data output area

            for comp in component_names:
                if comp not in [comp.name for comp in self.components]:
                    # Add new component to SimData
                    self.components.append(Component(name=comp))

            self.components = [
                comp for comp in self.components if comp.name in component_names
            ]  # Keep only components that are in the list

            # reorder sd.components to match components list, based on the name attribute of sd.components elements
            self.components = sorted(
                self.components,
                key=lambda x: (
                    component_names.index(x.name) if x.name in component_names else float("inf")
                ),
            )

            self.generate_binding_constants()  # Generate binding constants based on the current model


            self.notify_listeners(
                "model_changed", self.active_model
            )  # Notify listeners that the model has been updated

            # Disable save button when equations are parsed
            # TODO restore #self.save_sim_details_button.set_enabled(False)
            # default to model name + values of Ks

        except Exception as e:
            logger.error(e)
            ui.notify("Error: " + str(e), type="negative")


    def generate_binding_constants(self):
        """Generate binding constants based on the current model."""
        if not self.active_model:
            ui.notify("No active model to generate binding constants.", type="negative")
            return
        
        species = self.active_model.species
        components = self.active_model.component_names

        # number of bound species:
        boundspecies = [s for s in species if s not in components]
        # num_bound_species = len(species) - len(components)


        for s in species:

            if s not in [
                k.species
                for k in self.active_model.binding_constants
                if k.species not in species
            ]:
                logK = None
                isComp = False
                vary = True
                if s not in boundspecies:
                    # this is a component so logK = 0
                    logK = 0
                    isComp = True
                    vary = False
                self.active_model.binding_constants.append(
                    BindingConstant(species=s, logK=logK, vary=vary, isComp=isComp)
                )

        # remove stale binding constants
        # self.sd.binding_constants = [k for k in self.sd.binding_constants if k.species in species]

        # ensure isComp is set correctly for existing binding constants, and remove stale ones
        for k in self.active_model.binding_constants:
            if k.species not in species:
                self.active_model.binding_constants.remove(k)
            else:
                if k.species in components:
                    k.isComp = True
                else:
                    k.isComp = False

        # reorder self.sd.binding_constants to match species list
        ro = []
        for s in species:
            # as a quick check, ensure components have logK=0
            for k in self.active_model.binding_constants:
                if k.species in components:
                    k.logK = 0
                # reorder self.sd.binding_constants to match species list
            ro.append([k for k in self.active_model.binding_constants if k.species == s][0])

        self.active_model.binding_constants = ro

    def remove_model_dependent_objs(self, model: Model, notify_user: bool = True, notify_listeners: bool = True):
        """Backward-compatible helper for model cascade deletion."""
        if model.id not in self.models:
            ui.notify("Model not found.", type="negative")
            return
        self.delete_model(model, notify_user=notify_user, notify_listeners=notify_listeners)

    def delete_model(self, model: Model, notify_user: bool = True, notify_listeners: bool = True, reconcile: bool = True):
        """Delete a model from the state manager."""
        if model.id in self.default_model_ids:
            if notify_user:
                ui.notify("Built-in models cannot be deleted.", type="warning")
            return

        if model.id in self.models:
            before = self._snapshot_object_ids()
            self._delete_object_core(model)
            if len(self.models) == 0:
                self._initialize_default_models(emit_events=False)
                if notify_user:
                    ui.notify("No models left. Default models have been created.", type="info")
            after = self._snapshot_object_ids()
            self._emit_collection_events(before, after, notify_listeners=notify_listeners)
            if reconcile:
                self._finalize_active_context(reason="delete_model", emit_events=notify_listeners)
        else:
            ui.notify("Model not found.", type="negative")

    def delete_fit(self, fit: FitResult, notify_user: bool = True, notify_listeners: bool = True, reconcile: bool = True):
        """Delete a fit from the state manager."""
        if fit.id in self.fits:
            before = self._snapshot_object_ids()
            self._delete_object_core(fit)
            after = self._snapshot_object_ids()
            self._emit_collection_events(before, after, notify_listeners=notify_listeners)
            if reconcile:
                self._finalize_active_context(reason="delete_fit", emit_events=notify_listeners)
        else:
            ui.notify("Fit not found.", type="negative")

    def delete_simulation(self, simulation: Simulation, notify_user: bool = True, notify_listeners: bool = True, reconcile: bool = True):
        """Delete a simulation from the state manager."""
        if simulation.id in self.simulations:
            before = self._snapshot_object_ids()
            self._delete_object_core(simulation)
            after = self._snapshot_object_ids()
            self._emit_collection_events(before, after, notify_listeners=notify_listeners)
            if reconcile:
                self._finalize_active_context(reason="delete_simulation", emit_events=notify_listeners)
        else:
            ui.notify("Simulation not found.", type="negative")

    def delete_expt_data(self, expt_data: ExptData, notify_user: bool = True, notify_listeners: bool = True, reconcile: bool = True):
        """Delete experimental data from the state manager."""
        if expt_data.id in self.expt_datas:
            before = self._snapshot_object_ids()
            self._delete_object_core(expt_data)
            after = self._snapshot_object_ids()
            self._emit_collection_events(before, after, notify_listeners=notify_listeners)
            if reconcile:
                self._finalize_active_context(reason="delete_expt_data", emit_events=notify_listeners)
        else:
            ui.notify("Experimental data not found.", type="negative")

    def delete_raw_data(self, raw_data: RawData, notify_user: bool = True, notify_listeners: bool = True, reconcile: bool = True):
        """Delete raw data from the state manager."""
        if raw_data.id in self.raw_datas:
            before = self._snapshot_object_ids()
            self._delete_object_core(raw_data)
            after = self._snapshot_object_ids()
            self._emit_collection_events(before, after, notify_listeners=notify_listeners)
            if reconcile:
                self._finalize_active_context(reason="delete_raw_data", emit_events=notify_listeners)
        else:
            ui.notify("Raw data not found.", type="negative")

    def delete_mcmc(self, mcmc: MCMCSim, notify_user: bool = True, notify_listeners: bool = True, reconcile: bool = True):
        """Delete MCMC results from the state manager."""
        if mcmc.id in self.mcmcs:
            before = self._snapshot_object_ids()
            self._delete_object_core(mcmc)
            after = self._snapshot_object_ids()
            self._emit_collection_events(before, after, notify_listeners=notify_listeners)
            if reconcile:
                self._finalize_active_context(reason="delete_mcmc", emit_events=notify_listeners)
        else:
            ui.notify("MCMC result not found.", type="negative")
    
    def update_ui_bindings(self, bindables: str|list|None=None):
        if bindables is None:
            bindables = list(self.ui_bindings.__dict__.keys())
        
        def set_bindable(dest,src,parent=None):
            if parent is not None:
                if not hasattr(self,parent) or  getattr(self,parent) is  None:
                    val = ""
                else:
                    val = getattr(getattr(self,parent),src)
            else:
                val = getattr(self,src)
            if hasattr(self.ui_bindings, dest):
                setattr(self.ui_bindings, dest, val)


        for b in bindables:
            if hasattr(self.ui_bindings, b):
                if b == 'model_name':
                    set_bindable(b, 'name', parent='active_model')


    def dump_setup_and_model_def(self,model:Model) ->str:
        outstr = f"""
import bindtools as bd
import numpy as np
import matplotlib.pyplot as plt

#model = Model(name={model.name}, eq_mat={repr(model.eq_mat.tolist())})) 

eq_mat = {model.eq_mat.tolist()}
model_name = {model.name}

comp_names = {model.component_names}
species_names = {model.species}
nstep = {model.nStep}

        """
        return outstr

    def dump_simulation_to_python(self, model: Model) -> str:
        # dump initial imports and model setup
        outstr = self.dump_setup_and_model_def(model)
        # generate component blocks
        for c in model.components:
            if c.spacing == 'lin':
                outstr += f"\n{c.name}_concs = np.linspace({c.start_conc if c.start_conc is not None else 0},{c.end_conc if c.end_conc is not None else 0},nstep)"
            else:
                raise(NotImplementedError)

        outstr += f"""
comp_concs = np.vstack(({','.join([c+'_concs' for c in model.component_names])}))

logKs = dict()
for i,s in enumerate(species_names):
    logKs[s] = model.binding_constants[i].logK



# model parameters are all defined
# now let's generate the model and simulate it

model = bd.bindingModel(eq_mat, comp_names, species_names,compConcs=comp_concs)
model.prepModel()
model.params.pretty_print()

for s in species_names:
    model.params[s].set(value=logKs[s])

spec=model.calcSpeciation()

"""
        
        
        return outstr

    def dump_fit_to_python(self, fit: FitResult) -> str:
        outstr = self.dump_setup_and_model_def(fit.model)
        
        bm = self.generate_binding_model_for_fit(fit)

        # add some imports
        outstr = """
import pandas as pd
import lmfit
""" + outstr

        # load datafile
        outstr += f"""
#load datafile
data = pd.read_csv({fit.expt_data.raw_data.filename})

# sort datafile
column_mapping = {repr(fit.expt_data.column_mapping)}
if column_mapping is not None:
    old_cols = self.data.columns
    new_cols  = [None] * len(old_cols)
    for raw_proc in self.column_mapping:
        new_cols[proc] = old_cols[raw]
    data = data[new_cols]"""

        # specify compconc etc matrices
        outstr += f"""
# various matrices
obs_list = 
component_names = {repr(bm.compNames)}
integ_to_spec = {repr(bm.colToSpec)}
delta_to_spec = {repr(bm.specToDd)}
species = {repr(bm.plist)}
col_to_comp = {repr(bm.colToComp)}"""

        # set up fit
        outstr += """
# fitting and plotting routines
fit = bd.bindingModel(eqMat=eqMat,
    compNames=component_names,
    speciesList=species,
    colToComp=col_to_comp,
    specToInteg=integ_to_spec,
    specToDd=delta_to_spec,
    obsList=obs_list,
    rawData=data)
#sigma = [0.0005, 0.0005,0.0005,0.0005,0.0005]
fit.prepModel()
"""
        outstr += "# Define parameters"
        for k in fit.model.binding_constants:
            outstr += f"\nfit.params['log{k.species}'].set(value={k.logK if k.logK is not None else 0.0}, vary={k.vary}, min={k.min}, max={k.max})"


        outstr += f"""
fit.runModel(sigma=sigma,skip_col=2,method={fit.fit_method})
bd.makeFitResidPlot(fit,plotMask=(0,1),ylabel='Chemical shift (ppm)')"""



        return outstr
        # model_str = self.dump_model_to_python(fit._model) if fit._model is not None else "# Model not linked."
        # return model_str

    def generate_binding_model_for_fit(self, fit: Optional[FitResult]=None, analytical_cfg: Optional[dict[str, object]]=None) -> bd.bindingModel:
        """Generate a bindtools.bindingModel from the current active model."""
        old_fit = None
        if fit is not None and fit.id != self.active_fit_id:
            old_fit = str(self.active_fit_id)
            self.active_fit_id = fit.id
            self.active_expt_data_id = fit.expt_data_id
            self.active_model_id = fit.model_id
        
        if not self.active_model:
            raise ValueError("No active model to generate binding model.")

        obs_list = [x for x in self.active_expt_data.sorted_data.columns if self.active_expt_data.col_details[x]['depindep'] == 'dep']
        integ_to_spec = self.active_expt_data.integ_to_spec
        if not (isinstance(integ_to_spec, np.ndarray) and integ_to_spec.ndim == 2 and integ_to_spec.size > 0):
            integ_to_spec = None
        delta_to_spec = self.active_expt_data.delta_to_spec
        if not (isinstance(delta_to_spec, np.ndarray) and delta_to_spec.ndim == 2 and delta_to_spec.size > 0):
            delta_to_spec = None

        model = bd.bindingModel(
            eqMat=self.active_model.eq_mat,
            compNames=self.active_model.component_names,
            speciesList=self.active_model.species,
            colToComp=self.active_expt_data.col_to_comp,
            specToInteg=integ_to_spec,
            specToDd = delta_to_spec.T if delta_to_spec is not None else None,
            obsList=obs_list,
            rawData=np.array(self.active_expt_data.sorted_data)
        )

        cfg = analytical_cfg
        if cfg is None and fit is not None and getattr(fit, "analytical_fast_exchange", False):
            cfg = {
                "topology": fit.analytical_topology,
                "complex_indices": list(getattr(fit, "analytical_complex_indices", [])),
                "obs_columns": list(getattr(fit, "analytical_obs_columns", [])),
                "obs_components": list(getattr(fit, "analytical_obs_components", [])),
            }

        if cfg is not None:
            model.analytical_fast_exchange = True
            model.analytical_topology = str(cfg["topology"])
            model.analytical_complex_indices = [int(x) for x in cfg["complex_indices"]]  # type: ignore[index]
            model.analytical_obs_columns = [str(x) for x in cfg["obs_columns"]]  # type: ignore[index]
            model.analytical_obs_components = [int(x) for x in cfg["obs_components"]]  # type: ignore[index]
            logger.info(
                "Using analytical fast-exchange backend (%s model) for fitting.",
                model.analytical_topology,
            )

        # Handle UV-vis / fluorescence linear observables (numerical and analytical paths).
        if self.active_expt_data.has_linear_obs(self._expt_dtypes):
            self.active_expt_data.build_abs_to_spec(self._expt_dtypes)
            abs_to_spec = self.active_expt_data.abs_to_spec
            if abs_to_spec is not None and isinstance(abs_to_spec, np.ndarray) and abs_to_spec.ndim == 2 and abs_to_spec.size > 0:
                model.specToLinear = abs_to_spec.T  # (n_species, n_obs)

                # Build per-observable param name map for the analytical path.
                linear_obs_param_map: list[list] = []
                for obs_idx in range(abs_to_spec.shape[0]):
                    pnames: list = []
                    for species_idx in range(abs_to_spec.shape[1]):
                        cell = abs_to_spec[obs_idx, species_idx]
                        pnames.append(cell.name if isinstance(cell, LMFitParameter) else None)
                    linear_obs_param_map.append(pnames)

                lin_cols = [col for col in obs_list
                            if self.active_expt_data.col_details.get(col, {}).get("depindep") == "dep"
                            # already filtered above — just iterate obs_list directly
                            ]
                model.analytical_linear_obs_columns = lin_cols
                model.analytical_linear_obs_param_map = linear_obs_param_map

        model.prepModel()

        for k in self.active_model.binding_constants:
            model.params[f'log{k.species}'].set(value=k.logK if k.logK is not None else 0.0, vary=k.vary, min=k.min, max=k.max)


        # cleanup by restoring previous fit if needed
        if old_fit is not None:
            self.active_fit_id = uuid.UUID(old_fit)
            self.active_expt_data_id = self.active_fit.expt_data_id
            self.active_model_id = self.active_fit.model_id

        return model

    # ------------------------------------------------------------------
    # Jupyter notebook export
    # ------------------------------------------------------------------

    def dump_simulation_notebook(self, sim: Simulation) -> dict:
        """Export *sim* as an nbformat-4 notebook dict.

        The notebook embeds component concentrations from ``sim.comp_concs``
        and uses the binding constants from the linked model.  It is entirely
        self-contained (no nicegui / webgui imports).
        """
        from webgui.export.notebook_exporter import export_simulation_notebook

        model = self.models.get(sim.model_id)
        if model is None:
            raise ValueError(f"Model {sim.model_id} not found for simulation.")
        return export_simulation_notebook(sim, model)

    def dump_fit_notebook(self, fit: FitResult) -> tuple[dict, "pd.DataFrame"]:
        """Export *fit* as an nbformat-4 notebook dict plus a CSV DataFrame.

        The notebook is set up to re-run the fit; original fitted values
        appear as inline comments.  The companion CSV DataFrame contains the
        raw experimental data and should be saved as ``data.csv`` alongside
        the exported notebook.

        Returns
        -------
        notebook : dict
            nbformat-4 compatible dict (serialise with ``json.dumps``).
        csv_df : pd.DataFrame
            Raw data to be saved as CSV.
        """
        import pandas as pd  # noqa: F401 — type annotation only
        from webgui.export.notebook_exporter import export_fit_notebook

        # Ensure all objects are linked
        if not hasattr(fit, "_model") or fit._model is None:
            fit.find_and_link_model(self.models)
        if not hasattr(fit, "_expt_data") or fit._expt_data is None:
            fit.find_and_link_expt_data(self.expt_datas)
        expt_data = fit._expt_data
        if expt_data is not None:
            obs_type_names: list[str] = [
               ot.name for ot in expt_data.get_obs_list(self._expt_dtypes)
            ]
            if not hasattr(expt_data, "_raw_data") or expt_data._raw_data is None:
                expt_data.find_and_link_raw_data(self.raw_datas)
            if not hasattr(expt_data, "_model") or expt_data._model is None:
                expt_data.find_and_link_model(self.models)
        else:
            obs_type_names = []

        # Extract linear observable (UV-vis / fluorescence) structure for the notebook.
        lin_obs_col_names: list[str] | None = None
        lin_obs_param_map: list[list] | None = None
        if expt_data is not None and expt_data.has_linear_obs(self._expt_dtypes):
            expt_data.build_abs_to_spec(self._expt_dtypes)
            abs_to_spec = expt_data.abs_to_spec
            if abs_to_spec is not None and abs_to_spec.ndim == 2 and abs_to_spec.size > 0:
                lin_obs_col_names = [col for col, _ in expt_data.linear_obs_cols(self._expt_dtypes)]
                lin_obs_param_map = []
                for obs_idx in range(abs_to_spec.shape[0]):
                    row: list = []
                    for spec_idx in range(abs_to_spec.shape[1]):
                        cell = abs_to_spec[obs_idx, spec_idx]
                        if isinstance(cell, LMFitParameter):
                            row.append({"name": cell.name, "min": float(cell.min), "max": float(cell.max)})
                        else:
                            row.append(None)
                    lin_obs_param_map.append(row)
        
        


        return export_fit_notebook(
            fit, fit._model, expt_data, expt_data._raw_data,
            obs_type_names=obs_type_names,
            lin_obs_col_names=lin_obs_col_names,
            lin_obs_param_map=lin_obs_param_map,
        )

    def dump_mcmc_notebook(
        self,
        mcmc: "MCMCSim | None",
        include_chains: bool,
    ) -> "tuple[dict, pd.DataFrame, bytes | None]":
        """Export an MCMC run as a notebook zip bundle.

        The notebook contains the full fit setup (identical to
        :meth:`dump_fit_notebook`) followed by a live MCMC section.

        Parameters
        ----------
        mcmc : MCMCSim or None
            The MCMC run to export.  When *None* (no run yet), a code-only
            notebook is generated using the active fit's context.
        include_chains : bool
            When True, the companion HDF5 chain file is also produced.
            Requires ``mcmc.mc.sampler`` to be non-None.

        Returns
        -------
        notebook : dict
        csv_df : pd.DataFrame
        h5_bytes : bytes or None
        """
        import pandas as pd  # noqa: F401
        from webgui.export.notebook_exporter import export_mcmc_notebook

        # Always use active_fit so that the fit name embedded in the notebook's
        # read_csv call matches the ZIP entry name produced by the caller.
        # The MCMCSim is used only for its MCMC parameters and chains.
        fit = self.active_fit  # raises if not set

        # Link model onto fit
        if not hasattr(fit, "_model") or fit._model is None:
            fit.find_and_link_model(self.models)

        # Link expt_data onto fit
        if not hasattr(fit, "_expt_data") or fit._expt_data is None:
            fit.find_and_link_expt_data(self.expt_datas)
        expt_data = fit._expt_data

        if expt_data is not None:
            if not hasattr(expt_data, "_raw_data") or expt_data._raw_data is None:
                expt_data.find_and_link_raw_data(self.raw_datas)
            if not hasattr(expt_data, "_model") or expt_data._model is None:
                expt_data.find_and_link_model(self.models)

        if expt_data is None:
            raise ValueError("No experimental data found for MCMC notebook export.")
        if fit._model is None:
            raise ValueError("No model found for MCMC notebook export.")
        if expt_data._raw_data is None:
            raise ValueError("No raw data found for MCMC notebook export.")

        obs_type_names: list[str] = [
            ot.name for ot in expt_data.get_obs_list(self._expt_dtypes)
        ]

        # Extract linear observable (UV-vis / fluorescence) structure for the notebook.
        lin_obs_col_names: list[str] | None = None
        lin_obs_param_map: list[list] | None = None
        if expt_data.has_linear_obs(self._expt_dtypes):
            expt_data.build_abs_to_spec(self._expt_dtypes)
            abs_to_spec = expt_data.abs_to_spec
            if abs_to_spec is not None and abs_to_spec.ndim == 2 and abs_to_spec.size > 0:
                lin_obs_col_names = [col for col, _ in expt_data.linear_obs_cols(self._expt_dtypes)]
                lin_obs_param_map = []
                for obs_idx in range(abs_to_spec.shape[0]):
                    row: list = []
                    for spec_idx in range(abs_to_spec.shape[1]):
                        cell = abs_to_spec[obs_idx, spec_idx]
                        if isinstance(cell, LMFitParameter):
                            row.append({"name": cell.name, "min": float(cell.min), "max": float(cell.max)})
                        else:
                            row.append(None)
                    lin_obs_param_map.append(row)

        return export_mcmc_notebook(
            mcmc, fit, fit._model, expt_data, expt_data._raw_data,
            obs_type_names, include_chains,
            lin_obs_col_names=lin_obs_col_names,
            lin_obs_param_map=lin_obs_param_map,
        )
