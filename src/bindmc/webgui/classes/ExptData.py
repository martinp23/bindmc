import uuid
from dataclasses import asdict, dataclass, field, InitVar
from typing import  Optional,Any
import unicodedata
import re
from nicegui import binding
import numpy as np
import pandas as pd
from lmfit import Parameter as LMFitParameter
from asteval import valid_symbol_name
import bindtools.binding as bd
from .Model import Model
from .RawData import RawData
from .ChemicalShiftParam import ChemicalShiftParam
from .ExptDataType import ExptDataType

@dataclass
class ExptData():
    """Data class to represent experimental data."""

    name: str = ""
    #filename: str = ""
    #data: pd.DataFrame = field(default_factory=pd.DataFrame, compare=False)
    col_to_comp: np.ndarray = field(default_factory=lambda: np.array([]))  # Matrix to convert columns to components
    component_names: list[str] = field(default_factory=list)  # Names of components
    integ_to_spec: np.ndarray | None = field(default_factory=lambda: np.array([]))
    delta_to_spec: np.ndarray | None = field(default_factory=lambda: np.array([]))  
    # Keyed by (species_name, col_name) to support multiple shifts per species; col_name can be None for generic/default
    limiting_shifts: dict[tuple[str, str|None], ChemicalShiftParam] = field(default_factory=dict)
    # UV-vis / fluorescence: (n_obs_cols, n_species) object array — lmfit.Parameter or 0.0.
    # Not serialised (rebuilt on demand via build_abs_to_spec).
    abs_to_spec: np.ndarray | None = field(default=None, compare=False)
    # Maps observable col name → list of species names that are dark (ε/k fixed at 0).
    dark_species: dict[str, list[str]] = field(default_factory=dict)
    col_details: dict = field(default_factory=dict)
    id: uuid.UUID = field(
        default_factory=lambda: (uuid.uuid4()))
    model_id: Optional[uuid.UUID] = None
    raw_data_id: Optional[uuid.UUID] = None
    column_mapping: list[tuple[int, int]] = field(default_factory=list)  # List of tuples (col_idx, comp_idx) for reordering raw data before fitting
    is_analytical_fast_ex: bool = False  # Flag to indicate if this is a simple fast-exchange case that can use analytical solutions
    selected_columns: list[str] = field(default_factory=list)  # List of column names to include in data operations

    init_model: InitVar[Optional[Model]] = None  # Model associated with this experimental data
    init_raw_data: InitVar[Optional[RawData]] = None
    _comp_concs: pd.DataFrame = field(default_factory=pd.DataFrame, compare=False)
    _model: Optional[Model] = None  # The model used for the experimental data, if any
    _raw_data: Optional[RawData] = None

    def __post_init__(self,init_model, init_raw_data) -> None:
        # Load initvars
        if isinstance(init_model,Model):  
            self._model=init_model
            self.model_id = init_model.id

        if isinstance(init_raw_data,RawData):
            self._raw_data = init_raw_data
            self.raw_data_id = init_raw_data.id

        """Ensure data are appropriate types."""
        # if not isinstance(self.data, pd.DataFrame):
        #     self.data = pd.DataFrame(self.data)
        if not isinstance(self.col_to_comp, np.ndarray):
            self.col_to_comp = np.array(self.col_to_comp, dtype=float)
        if not isinstance(self.integ_to_spec, np.ndarray):
            self.integ_to_spec = np.array(self.integ_to_spec, dtype=float)

        # if len(self.col_details) != len(self.data.columns):
        #     # Initialize col_details if it doesn't match the number of columns
        #     self.col_details = {
        #         col: {"depindep": None} for col in self.data.columns
        #     } 

        if not isinstance(self.id, uuid.UUID):
            if isinstance(self.id, str):
                self.id = uuid.UUID(self.id)

        if not isinstance(self.model_id, uuid.UUID):
            if isinstance(self.model_id, str) and self.model_id != 'None':
                self.model_id = uuid.UUID(self.model_id)

        if isinstance(self._model, Model) and not self.model_id:
            self.model_id = self._model.id
            
        # Initialize selected_columns to include all columns if not set
        if not self.selected_columns:
            # Get data without triggering property access that might cause recursion
            raw_data = self._raw_data.data if isinstance(self._raw_data, RawData) else pd.DataFrame([])
            if not raw_data.empty:
                self.selected_columns = raw_data.columns.tolist()


    def find_and_link_model(self, models: Optional[dict[uuid.UUID,Model]] = None) -> None:
        """Set the model for this experimental data."""
        if models is not None:
            if self.model_id in models  and self.model_id is not None:
                self._model = models[self.model_id]
            else:
                raise ValueError(f"Corresponding model {self.model_id} not found for ExptData.")


        else:
            raise ValueError(f"Corresponding model {self.model_id} not found for ExptData.")

    def find_and_link_raw_data(self, raw_datas: dict[uuid.UUID, RawData]) -> None:
        """Set the raw data for this experimental data."""
        if raw_datas is not None and isinstance(self.raw_data_id,(str,uuid.UUID)):
            self.raw_data_id = uuid.UUID(self.raw_data_id) if isinstance(self.raw_data_id, str) else self.raw_data_id
            self._raw_data = raw_datas.get(self.raw_data_id)
            return
        
        raise ValueError(f"Corresponding raw data {self.raw_data_id} not found for ExptData.")

    @property
    def sorted_data(self) -> pd.DataFrame:
        """Return the selected data sorted by the column mapping."""
        base_data = self.selected_data  # Use selected data instead of full data
        if self.column_mapping and base_data is not None and not base_data.empty:
            old_cols = base_data.columns
            new_cols: list[None|str] = [None] * len(old_cols)
            for raw,proc in self.column_mapping:
                if raw < len(old_cols):  # Ensure mapping is valid for selected columns
                    new_cols[proc] = old_cols[raw]
            # Filter out None values in case column mapping refers to unselected columns
            valid_cols = [col for col in new_cols if col is not None]
            return base_data[valid_cols] if valid_cols else pd.DataFrame()
        else:
            return base_data

    @property
    def data(self) -> pd.DataFrame:
        return self._raw_data.data if isinstance(self._raw_data, RawData) else pd.DataFrame([])
    
    @property
    def selected_data(self) -> pd.DataFrame:
        """Return a view of the data with only selected columns."""
        full_data = self.data
        if full_data.empty or not self.selected_columns:
            return full_data
        # Filter to only selected columns that actually exist in the data
        available_selected = [col for col in self.selected_columns if col in full_data.columns]
        return full_data[available_selected] if available_selected else pd.DataFrame()

    @property 
    def obsdata(self) -> pd.DataFrame:
        """Get the observed data which are to be included in the fit (i.e. not disabled)."""
        data_to_use = self.selected_data  # Use selected data instead of full data
        if data_to_use is not None and not data_to_use.empty:
            return data_to_use[[x for x in data_to_use.columns if x in self.col_details and self.col_details[x]['depindep'] == 'dep']]
        else:
            return pd.DataFrame([])


    @property
    def columns(self) -> list[str]:
        """Get the column names of the selected experimental data."""
        return self.selected_data.columns.tolist() if not self.selected_data.empty else []

    @property
    def comp_concs(self) -> pd.DataFrame:
        """Get the component concentrations for this fit."""
        if isinstance(self._comp_concs,pd.DataFrame) and not self._comp_concs.empty:
            return self._comp_concs
        elif  (self.selected_data is not None) and (self.col_to_comp is not None):
            nconcs = np.shape(self.col_to_comp)[1]
            cc = np.dot(self.selected_data.iloc[:,:nconcs],self.col_to_comp.T)  # [Htot, Gtot]
            
            if self.model is not None:
                self._comp_concs = pd.DataFrame(
                    cc, columns=self.model.component_names
                )
                return self._comp_concs
            else:
                raise ValueError("Model is not set for ExptData, cannot get component_names.")
        else:
            raise ValueError("Model is not set or does not have component concentrations.")


    def get_obs_list(self,expt_dtyes: dict[str,ExptDataType]) -> list[bd.ObsType]:
        """Get the list of ExptDataType for each observed column."""
        obs_list = []
        for col in self.col_details:
            if self.col_details[col]['depindep'] == 'dep' and self.col_details[col]['dtype'] is not None:
                edt = expt_dtyes.get(self.col_details[col]['dtype'])
                if edt is None:
                    raise ValueError(f"ExptDataType {self.col_details[col]['dtype']} not found for column {col}.")
                obs_list.append(bd.ObsType(name=edt.meas, units=edt.units, value=edt.lnsigma, minlim=edt.lnsigma_min, maxlim=edt.lnsigma_max))
        return obs_list

    def has_linear_obs(self, expt_dtypes: dict) -> bool:
        """Return True if any dependent column has a UV-vis or fluorescence measurement type."""
        for col, details in self.col_details.items():
            if details.get('depindep') == 'dep':
                dtype_key = details.get('dtype')
                if dtype_key is not None:
                    edt = expt_dtypes.get(dtype_key)
                    if edt is not None and edt.meas in ('uvvis', 'fluorescence'):
                        return True
        return False

    def linear_obs_cols(self, expt_dtypes: dict) -> list[tuple[str, str]]:
        """Return list of (col_name, measurement_method) for UV-vis/fluorescence dep columns."""
        result = []
        for col in self.col_details:  # preserves insertion order
            details = self.col_details[col]
            if details.get('depindep') == 'dep':
                dtype_key = details.get('dtype')
                if dtype_key is not None:
                    edt = expt_dtypes.get(dtype_key)
                    if edt is not None and edt.meas in ('uvvis', 'fluorescence'):
                        result.append((col, edt.meas))
        return result

    def build_abs_to_spec(self, expt_dtypes: dict) -> None:
        """Build the abs_to_spec object array for UV-vis / fluorescence observables.

        Shape: (n_linear_obs_cols, n_species), dtype=object.
        Active species → lmfit.Parameter with auto-estimated initial value.
        Dark species → 0.0 (fixed).

        Initial value heuristic: eps_init ≈ max(|obs_col|) / sum(max([comp]) for active comps),
        with bounds spanning ±3 orders of magnitude.  Falls back to 1.0 when concentrations
        are zero or the model is not linked.
        """
        lin_cols = self.linear_obs_cols(expt_dtypes)
        if not lin_cols:
            self.abs_to_spec = None
            return

        model = self.model
        species_names = model.species if model is not None else []
        n_species = len(species_names)
        n_obs = len(lin_cols)

        matrix = np.zeros((n_obs, n_species), dtype=object)

        # Pre-compute max component concentrations for auto-estimation.
        try:
            comp_concs_vals = self.comp_concs.values if not self.comp_concs.empty else None
        except Exception:
            comp_concs_vals = None

        used_param_names: set[str] = set()

        for obs_idx, (col, meas) in enumerate(lin_cols):
            dark = set(self.dark_species.get(col, []))
            prefix = 'eps' if meas == 'uvvis' else 'fluor'

            # Auto-estimate a scale for epsilon from the observable column.
            try:
                obs_vals = self.selected_data[col].dropna().abs().values
                max_obs = float(obs_vals.max()) if obs_vals.size > 0 else 1.0
            except Exception:
                max_obs = 1.0

            # Sum of max concentrations of non-dark species for scale estimate.
            active_species = [s for s in species_names if s not in dark]
            denom = 1.0
            if comp_concs_vals is not None and len(active_species) > 0 and comp_concs_vals.shape[1] > 0:
                # Use total component concentrations as a proxy for species concentrations.
                n_comps = comp_concs_vals.shape[1]
                denom = max(float(comp_concs_vals.max()), 1e-30)
            eps_init = max_obs / denom if denom > 0 else 1.0
            if eps_init == 0.0 or not np.isfinite(eps_init):
                eps_init = 1.0

            token = self._sanitize_shift_param_name(col)

            for species_idx, species in enumerate(species_names):
                if species in dark:
                    matrix[obs_idx, species_idx] = 0.0
                else:
                    base_name = f"{prefix}_{self._sanitize_shift_param_name(species)}_{token}"
                    # Ensure uniqueness across all observables.
                    candidate = base_name
                    suffix = 2
                    while candidate in used_param_names:
                        candidate = f"{base_name}_{suffix}"
                        suffix += 1
                    used_param_names.add(candidate)

                    param = LMFitParameter(
                        name=candidate,
                        value=eps_init,
                        min=eps_init * 1e-3,
                        max=eps_init * 1e3,
                        vary=True,
                    )
                    matrix[obs_idx, species_idx] = param

        self.abs_to_spec = matrix




    @property
    def model(self) -> Optional[Model]:
        """Get the model associated with this experimental data."""
        return self._model if isinstance(self._model, Model) else None


    @model.setter
    def model(self, model: Model) -> None:
        """Set the model for this experimental data."""
        if model is not None:
            self.model_id = model.id
            self._model = model


    @property
    def raw_data(self) -> RawData:
        """Get the rawdata associated with this experimental data."""
        return self._raw_data if isinstance(self._raw_data, RawData) else RawData()



    @raw_data.setter
    def raw_data(self, raw_data:RawData) -> None:
        if raw_data is not None:
            self.raw_data_id = raw_data.id
            self._raw_data = raw_data

    def to_dict(self):
        """Convert ExptData to a dictionary."""
        return {
            "name": self.name,
            # "filename": self.raw_data.filename,
            # "data": (
            #     self.data.to_dict(orient="list")
            #     if isinstance(self.data, pd.DataFrame) else {}
            # ),
            "col_to_comp": self.col_to_comp.tolist() if isinstance(self.col_to_comp, np.ndarray) else [],
            "integ_to_spec": self.integ_to_spec.tolist() if isinstance(self.integ_to_spec, np.ndarray) else [],
            "col_details": self.col_details if isinstance(self.col_details, dict) else {},
            "id": str(self.id) if self.id else "",
            "model_id": str(self.model_id) if hasattr(self, "model_id") else "",
            "raw_data_id": str(self.raw_data_id) if hasattr(self, "raw_data_id") else "",
            # Serialize delta_to_spec safely even when it contains objects (e.g., lmfit Parameters)
            "delta_to_spec": self._delta_to_spec_jsonable(),
            # limiting_shifts as a list for JSON safety (tuple keys not JSON-serializable)
            "limiting_shifts": [asdict(v) for v in self.limiting_shifts.values()],
            "is_analytical_fast_ex": self.is_analytical_fast_ex,
            "selected_columns": self.selected_columns,
            "dark_species": {col: list(species) for col, species in self.dark_species.items()},
        }

    # --- Fast-exchange helpers ---
    def _sanitize_shift_param_name(self, raw_suffix: str) -> str:
        """Convert species/column suffix into a readable symbol-like token."""
        safe = re.sub(r"[^\w]+", "_", raw_suffix)
        safe = re.sub(r"_+", "_", safe).strip("_")
        return safe or "param"

    def _unique_shift_param_name(self, base_name: str, used_names: set[str]) -> str:
        """Ensure a deterministic unique parameter name within one build call."""
        candidate = base_name
        idx = 2
        while candidate in used_names:
            candidate = f"{base_name}_{idx}"
            idx += 1
        used_names.add(candidate)
        return candidate

    def build_delta_to_spec(self, spec_vectors: list[np.ndarray], species_names: list[str], row_columns: list[str]) -> np.ndarray:
        """Build an object ndarray mapping species to chemical-shift parameters for fast exchange.

        Each nonzero entry becomes either a float (fixed) or an lmfit Parameter (variable).
        The same species across multiple rows will reuse the same Parameter object.

        Args:
            spec_vectors: list of length n_rows, each a 1D array over species_names with coefficients.
            species_names: ordered list of species corresponding to columns (e.g., ["H_free", "G_free"]).

        Returns:
            np.ndarray of shape (n_rows, n_species) with dtype=object.
        """
        num_rows = len(spec_vectors)
        num_species = len(species_names)
        parameter_matrix = np.zeros((num_rows, num_species), dtype=object)

        # cache to reuse the same Parameter per species
        parameter_cache: dict[tuple[str,str], LMFitParameter|float] = {}
        used_param_names: set[str] = set()

        def _get_parameter_for_species(species_key: str, column_name: str):
            # species_key should match keys used in limiting_shifts (e.g., "H_free")
            cache_key = (species_key, column_name)
            if cache_key in parameter_cache:
                return parameter_cache[cache_key]

            # Look up by (species, column) first; then fallback to generic (species, None);
            # and finally support legacy dict[str] keys by scanning values with species match.
            shift_param = self.limiting_shifts.get((species_key, column_name))
            if shift_param is None:
                raise ValueError(f"No shift parameter found for species '{species_key}' and column '{column_name}'.")
            
            # Extract value/bounds/fixed
            param_value = 0.0
            not_fixed = False
            min_value = None
            max_value = None
            if isinstance(shift_param, ChemicalShiftParam):
                param_value = float(shift_param.value) if shift_param.value is not None else 0.0
                not_fixed = not bool(shift_param.fixed)
                min_value = getattr(shift_param, "_min", None)
                max_value = getattr(shift_param, "_max", None)
            else:
                raise ValueError(f"Expected ChemicalShiftParam, got {type(shift_param)} for species '{species_key}' and column '{column_name}'.")

            if not_fixed:
                raw_suffix = f"{species_key}_{column_name or ''}"
                name_suffix = self._sanitize_shift_param_name(raw_suffix)
                base_name = f"delta_{name_suffix}"
                if not valid_symbol_name(base_name):
                    base_name = "delta_param"
                final_name = self._unique_shift_param_name(base_name, used_param_names)
                parameter = LMFitParameter(name=final_name, value=param_value)
            
                if min_value is not None:
                    parameter.min = float(min_value)
                if max_value is not None:
                    parameter.max = float(max_value)
                parameter.vary = True
            else:
                parameter = float(param_value)  # Fixed parameters are just floats
            parameter_cache[cache_key] = parameter
            return parameter
            

        for i, spec_vector in enumerate(spec_vectors):
            if spec_vector is None:
                continue
            delta_col = row_columns[i]

            for j, coeff in enumerate(list(spec_vector)):
                try:
                    is_nonzero = not np.isclose(coeff, 0)
                except Exception:
                    is_nonzero = bool(coeff)
                if is_nonzero:
                    species_key = species_names[j]
                    parameter_matrix[i, j] = _get_parameter_for_species(species_key, delta_col)
                else:
                    parameter_matrix[i, j] = 0.0

        self.delta_to_spec = parameter_matrix
        return parameter_matrix

    def _delta_to_spec_jsonable(self) -> list:
        """Return a JSON-serializable representation of delta_to_spec.

        - Numeric arrays: return .tolist()
        - Object arrays: floats stay as floats; lmfit Parameters become dicts
        - Anything else falls back to None
        """
        if not isinstance(self.delta_to_spec, np.ndarray):
            return []
        if self.delta_to_spec.dtype != object:
            return self.delta_to_spec.tolist()
        serialized_rows: list[list[object]] = []
        for row_values in self.delta_to_spec:
            serialized_row: list[object] = []
            for cell_value in row_values:
                if isinstance(cell_value, (int, float, np.floating)):
                    serialized_row.append(float(cell_value))
                elif isinstance(cell_value, LMFitParameter):
                    # Note: min/max may be +/-inf; replace with None for JSON friendliness
                    min_bound = getattr(cell_value, "min", None)
                    max_bound = getattr(cell_value, "max", None)
                    serialized_row.append({
                        "type": "lmfit_param",
                        "name": getattr(cell_value, "name", ""),
                        "value": float(getattr(cell_value, "value", 0.0)),
                        "min": (float(min_bound) if (min_bound is not None and np.isfinite(min_bound)) else None),
                        "max": (float(max_bound) if (max_bound is not None and np.isfinite(max_bound)) else None),
                        "vary": bool(getattr(cell_value, "vary", True)),
                    })
                else:
                    # Try best-effort float conversion, else None
                    try:
                        serialized_row.append(float(cell_value))
                    except Exception:
                        serialized_row.append(None)
            serialized_rows.append(serialized_row)
        return serialized_rows
