"""Tests for UV-vis / fluorescence observable types.

Covers:
- concToLinearObs() math
- concToObservable() with specToLinear
- calc_analytical_linear_observables()
- fitfun_analytical_fast_exchange() with UV-vis
- ExptDataType normalisation of uv_abs and new keys
- ExptData.has_linear_obs / linear_obs_cols
- ExptData.build_abs_to_spec (parameter naming, dark species)
- ExptData.dark_species serialisation round-trip
- StateManager analytical config with UV-vis dataset
- Numerical-path fit with synthetic UV-vis data
"""

from __future__ import annotations

import uuid
import pytest
import numpy as np
import lmfit

import bindtools.binding as bd
from webgui.classes.ExptDataType import ExptDataType
from webgui.classes.ExptData import ExptData
from webgui.classes.RawData import RawData
from webgui.classes.Component import Component
from webgui.classes.Model import Model
from lmfit import Parameter as LMFitParameter


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_simple_model(name: str = "1:1") -> Model:
    """Minimal 1:1 binding model (H + G ⇌ HG)."""
    m = Model(
        name=name,
        component_names=["H", "G"],
        species=["H", "G", "HG"],
        eq_mat=np.array([[1, 1]]),  # 1 complex, 1 equilibrium
        binding_constants_logK=[6.0],
    )
    return m


def _simple_1to1_eq_mat() -> np.ndarray:
    return np.array([[1, 1]], dtype=float)


# ---------------------------------------------------------------------------
# 1. concToLinearObs
# ---------------------------------------------------------------------------

class TestConcToLinearObs:
    def test_basic_identity(self):
        """When specToLinear is identity matrix, obs = concs."""
        concs = np.array([[1.0, 2.0, 3.0],
                          [4.0, 5.0, 6.0]])
        specToLinear = np.eye(3, dtype=object)
        params = np.array([], dtype=float)
        names: list[str] = []
        result = bd.concToLinearObs(concs, specToLinear, params, names)
        np.testing.assert_allclose(result, concs)

    def test_scalar_eps(self):
        """Epsilon values are applied correctly."""
        # 3 species, 1 observable; eps = [2, 0, 3]
        concs = np.array([[1.0, 1.0, 1.0],
                          [2.0, 3.0, 4.0]])  # (n_pts=2, n_sp=3)
        specToLinear = np.array([[2.0], [0.0], [3.0]], dtype=object)  # (3, 1)
        result = bd.concToLinearObs(concs, specToLinear, np.array([]), [])
        # expected: [2*1+0*1+3*1, 2*2+0*3+3*4] = [5, 16]
        np.testing.assert_allclose(result.flatten(), [5.0, 16.0])

    def test_lmfit_parameter_values_resolved(self):
        """lmfit Parameter objects in the matrix are replaced with their values."""
        eps_param = LMFitParameter("eps_HG_test", value=5.0, min=0, max=1000)
        # 2 species, 1 observable — build object array without using np.array([...param...])
        specToLinear = np.empty((2, 1), dtype=object)
        specToLinear[0, 0] = 0.0
        specToLinear[1, 0] = eps_param
        concs = np.array([[1.0, 2.0],
                          [3.0, 4.0]])  # (2, 2)
        # shiftParams = [5.0], paramNames = ["eps_HG_test"]
        result = bd.concToLinearObs(concs, specToLinear, np.array([5.0]), ["eps_HG_test"])
        # obs = 0*concs[:,0] + 5*concs[:,1] = [10, 20]
        np.testing.assert_allclose(result.flatten(), [10.0, 20.0])

    def test_output_shape(self):
        """Returns (n_pts, n_obs) shape."""
        concs = np.ones((7, 4))
        specToLinear = np.ones((4, 3), dtype=object)
        result = bd.concToLinearObs(concs, specToLinear, np.array([]), [])
        assert result.shape == (7, 3)


# ---------------------------------------------------------------------------
# 2. concToObservable with specToLinear
# ---------------------------------------------------------------------------

class TestConcToObservableLinear:
    def test_linear_only(self):
        """concToObservable returns linear obs when only specToLinear is given."""
        concs = np.array([[2.0, 3.0]])
        specToLinear = np.array([[1.0], [2.0]], dtype=object)  # (2 sp, 1 obs)
        result = bd.concToObservable(
            concs, None, None, np.array([]), [],
            specToLinear=specToLinear,
        )
        # 1*2 + 2*3 = 8
        np.testing.assert_allclose(result.flatten(), [8.0])

    def test_integ_and_linear_concatenated(self):
        """concToObservable concatenates integ then linear columns."""
        concs = np.array([[1.0, 2.0]])
        specToInteg = np.array([[1.0], [0.0]])   # (2, 1) — only first species
        specToLinear = np.array([[0.0], [3.0]], dtype=object)  # (2, 1) — only second species
        result = bd.concToObservable(
            concs, specToInteg, None, np.array([]), [],
            specToLinear=specToLinear,
        )
        assert result.shape == (1, 2)
        np.testing.assert_allclose(result[0, 0], 1.0)   # integ: 1*1+0*2
        np.testing.assert_allclose(result[0, 1], 6.0)   # linear: 0*1+3*2


# ---------------------------------------------------------------------------
# 3. calc_analytical_linear_observables
# ---------------------------------------------------------------------------

class TestCalcAnalyticalLinearObservables:
    def test_single_observable_no_dark(self):
        """A = eps_H * [H] + eps_HG * [HG]."""
        # 2 species, 3 points
        spec_calc = np.array([[0.5, 0.5],
                              [0.3, 0.7],
                              [0.1, 0.9]])
        linear_obs_param_map = [["eps_H_abs", "eps_HG_abs"]]
        linear_param_values = np.array([1000.0, 5000.0])   # eps_H=1000, eps_HG=5000
        linear_param_names = ["eps_H_abs", "eps_HG_abs"]

        out = bd.calc_analytical_linear_observables(
            spec_calc, linear_param_values, linear_param_names, linear_obs_param_map
        )
        expected = np.array([
            [1000 * 0.5 + 5000 * 0.5],
            [1000 * 0.3 + 5000 * 0.7],
            [1000 * 0.1 + 5000 * 0.9],
        ])
        np.testing.assert_allclose(out, expected)

    def test_dark_species_contributes_zero(self):
        """Species with None param name is treated as dark (zero contribution)."""
        spec_calc = np.array([[1.0, 0.5]])
        # first species is dark
        linear_obs_param_map = [[None, "eps_G_abs"]]
        linear_param_values = np.array([200.0])
        linear_param_names = ["eps_G_abs"]

        out = bd.calc_analytical_linear_observables(
            spec_calc, linear_param_values, linear_param_names, linear_obs_param_map
        )
        np.testing.assert_allclose(out, [[100.0]])   # only 200 * 0.5

    def test_output_shape(self):
        spec_calc = np.ones((5, 3))
        linear_obs_param_map = [["a", "b", "c"], ["d", "e", "f"]]
        params = np.ones(6)
        names = ["a", "b", "c", "d", "e", "f"]
        out = bd.calc_analytical_linear_observables(spec_calc, params, names, linear_obs_param_map)
        assert out.shape == (5, 2)


# ---------------------------------------------------------------------------
# 4. ExptDataType normalisation
# ---------------------------------------------------------------------------

class TestExptDataType:
    def test_uvvis_sets_absorbance_units(self):
        edt = ExptDataType(name="Abs", init_meas="uvvis")
        assert edt.meas == "uvvis"
        assert edt.units == "absorbance"
        assert edt.lnsigma is not None

    def test_uv_abs_alias_resolves_to_uvvis(self):
        """Legacy uv_abs key is normalised to uvvis."""
        edt = ExptDataType(name="Legacy", init_meas="uv_abs")
        assert edt.meas == "uvvis"
        assert edt.units == "absorbance"

    def test_uv_abs_stored_measurement_aliased_by_property(self):
        """Already-stored uv_abs in _measurement_method is normalised by .meas."""
        edt = ExptDataType(name="UV", init_meas="")
        edt._measurement_method = "uv_abs"
        assert edt.meas == "uvvis"

    def test_fluorescence_sets_intensity_units(self):
        edt = ExptDataType(name="Fluor", init_meas="fluorescence")
        assert edt.meas == "fluorescence"
        assert edt.units == "intensity"

    def test_fluorescence_lnsigma_range(self):
        edt = ExptDataType(name="Fluor", init_meas="fluorescence")
        assert edt.lnsigma_min == -8
        assert edt.lnsigma_max == 0


# ---------------------------------------------------------------------------
# 5. ExptData.has_linear_obs / linear_obs_cols
# ---------------------------------------------------------------------------

class TestExptDataLinearObs:
    def _make_expt_data_with_col(self, meas: str) -> tuple[ExptData, dict]:
        expt_data = ExptData(name="test")
        expt_data.col_details = {
            "H_conc": {"depindep": "indep", "dtype": "conc"},
            "abs_col": {"depindep": "dep", "dtype": "my_abs"},
        }
        edt = ExptDataType(name="my_abs", init_meas=meas)
        expt_dtypes = {"conc": ExptDataType(name="Conc", init_meas="grav_vol"), "my_abs": edt}
        return expt_data, expt_dtypes

    def test_has_linear_obs_uvvis(self):
        ed, dtypes = self._make_expt_data_with_col("uvvis")
        assert ed.has_linear_obs(dtypes) is True

    def test_has_linear_obs_fluorescence(self):
        ed, dtypes = self._make_expt_data_with_col("fluorescence")
        assert ed.has_linear_obs(dtypes) is True

    def test_has_linear_obs_uv_abs_legacy(self):
        """Legacy uv_abs meas maps to uvvis via ExptDataType.meas property."""
        ed, dtypes = self._make_expt_data_with_col("uv_abs")
        assert ed.has_linear_obs(dtypes) is True

    def test_has_linear_obs_nmr_returns_false(self):
        ed, dtypes = self._make_expt_data_with_col("nmr_ppm")
        assert ed.has_linear_obs(dtypes) is False

    def test_linear_obs_cols_returns_col_and_meas(self):
        ed, dtypes = self._make_expt_data_with_col("uvvis")
        cols = ed.linear_obs_cols(dtypes)
        assert len(cols) == 1
        col_name, meas = cols[0]
        assert col_name == "abs_col"
        assert meas == "uvvis"


# ---------------------------------------------------------------------------
# 6. ExptData.build_abs_to_spec
# ---------------------------------------------------------------------------

class TestBuildAbsToSpec:
    def _make_linked_expt_data(self, meas: str = "uvvis", dark_species: list[str] | None = None):
        """Create an ExptData with a mock model linked."""
        import pandas as pd

        model = Model(
            name="1to1",
            component_names=["H", "G"],
            species=["H_free", "G_free", "HG"],
            eq_mat=np.array([[1, 1]]),
        )
        raw_data = RawData(
            filename="test",
            data=pd.DataFrame({
                "H_conc": [1e-4, 2e-4, 3e-4],
                "G_conc": [1e-5, 1e-5, 1e-5],
                "abs_col": [0.1, 0.2, 0.3],
            }),
        )
        edt_conc = ExptDataType(name="Conc", init_meas="grav_vol", units="M")
        edt_abs = ExptDataType(name="my_abs", init_meas=meas)
        expt_dtypes = {"conc": edt_conc, "my_abs": edt_abs}

        expt_data = ExptData(
            name="test",
            init_model=model,
            init_raw_data=raw_data,
        )
        expt_data.col_details = {
            "H_conc": {"depindep": "indep", "dtype": "conc"},
            "G_conc": {"depindep": "indep", "dtype": "conc"},
            "abs_col": {"depindep": "dep", "dtype": "my_abs"},
        }
        col_to_comp = np.array([[1, 0], [0, 1]], dtype=float)
        expt_data.col_to_comp = col_to_comp

        if dark_species:
            expt_data.dark_species = {"abs_col": dark_species}

        return expt_data, expt_dtypes

    def test_build_creates_matrix(self):
        ed, dtypes = self._make_linked_expt_data()
        ed.build_abs_to_spec(dtypes)
        assert ed.abs_to_spec is not None
        assert ed.abs_to_spec.shape == (1, 3)  # 1 obs col, 3 species

    def test_dark_species_has_float_zero(self):
        ed, dtypes = self._make_linked_expt_data(dark_species=["HG"])
        ed.build_abs_to_spec(dtypes)
        mat = ed.abs_to_spec
        assert mat is not None
        # species: H_free, G_free, HG → HG is at index 2
        assert mat[0, 2] == 0.0
        assert not isinstance(mat[0, 2], LMFitParameter)

    def test_active_species_are_parameters(self):
        ed, dtypes = self._make_linked_expt_data(dark_species=["HG"])
        ed.build_abs_to_spec(dtypes)
        mat = ed.abs_to_spec
        assert mat is not None
        assert isinstance(mat[0, 0], LMFitParameter)  # H_free
        assert isinstance(mat[0, 1], LMFitParameter)  # G_free

    def test_eps_param_names_prefixed_correctly_uvvis(self):
        ed, dtypes = self._make_linked_expt_data(meas="uvvis")
        ed.build_abs_to_spec(dtypes)
        mat = ed.abs_to_spec
        assert mat is not None
        for sp_idx in range(3):
            cell = mat[0, sp_idx]
            if isinstance(cell, LMFitParameter):
                assert cell.name.startswith("eps_"), cell.name

    def test_fluor_param_names_prefixed_correctly(self):
        ed, dtypes = self._make_linked_expt_data(meas="fluorescence")
        ed.build_abs_to_spec(dtypes)
        mat = ed.abs_to_spec
        assert mat is not None
        for sp_idx in range(3):
            cell = mat[0, sp_idx]
            if isinstance(cell, LMFitParameter):
                assert cell.name.startswith("fluor_"), cell.name

    def test_no_linear_obs_sets_abs_to_spec_none(self):
        """build_abs_to_spec with no UV-vis columns sets abs_to_spec to None."""
        import pandas as pd
        edt_conc = ExptDataType(name="Conc", init_meas="grav_vol", units="M")
        edt_nmr = ExptDataType(name="NMR shift", init_meas="nmr_ppm", units="ppm")
        dtypes = {"conc": edt_conc, "delta_H": edt_nmr}
        ed = ExptData(name="test")
        ed.col_details = {
            "H_conc": {"depindep": "indep", "dtype": "conc"},
            "delta_H": {"depindep": "dep", "dtype": "delta_H"},
        }
        ed.build_abs_to_spec(dtypes)
        assert ed.abs_to_spec is None


# ---------------------------------------------------------------------------
# 7. ExptData dark_species serialisation round-trip
# ---------------------------------------------------------------------------

class TestDarkSpeciesSerialisation:
    def test_to_dict_includes_dark_species(self):
        ed = ExptData(name="test")
        ed.dark_species = {"abs_col": ["HG", "H_free"]}
        d = ed.to_dict()
        assert "dark_species" in d
        assert d["dark_species"] == {"abs_col": ["HG", "H_free"]}

    def test_empty_dark_species_serialised(self):
        ed = ExptData(name="test")
        d = ed.to_dict()
        assert "dark_species" in d
        assert d["dark_species"] == {}


# ---------------------------------------------------------------------------
# 8. End-to-end: numerical-path fit with synthetic UV-vis data
# ---------------------------------------------------------------------------

class TestNumericalUVvisFit:
    """Verify the numerical NR path fits absorbance data end-to-end."""

    def _generate_synthetic_1to1_uvvis_data(
        self,
        log_beta: float = 6.0,
        eps_H: float = 1000.0,
        eps_HG: float = 5000.0,
        H_total: float = 1e-4,
        n_pts: int = 20,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return (comp_concs [n_pts,2], absorbance [n_pts,1]) for 1:1 binding."""
        G_total = np.linspace(0, 2e-4, n_pts)
        beta = 10 ** log_beta
        # Closed-form 1:1: quadratic for [HG]
        a_coef = 1.0
        b_coef = -(H_total + G_total + 1.0 / beta)
        c_coef = H_total * G_total
        HG = (-b_coef - np.sqrt(b_coef ** 2 - 4 * a_coef * c_coef)) / (2 * a_coef)
        H_free = H_total - HG
        absorbance = eps_H * H_free + eps_HG * HG  # (no G contribution)
        comp_concs = np.column_stack([np.full(n_pts, H_total), G_total])
        return comp_concs, absorbance.reshape(-1, 1)

    def test_uvvis_fit_recovers_binding_constant(self):
        """bindingModel with specToLinear recovers known log_beta within 0.2 log units."""
        log_beta_true = 6.0
        eps_H_true = 1000.0
        eps_HG_true = 5000.0
        H_total = 1e-4
        n_pts = 25

        comp_concs, absorbance = self._generate_synthetic_1to1_uvvis_data(
            log_beta=log_beta_true, eps_H=eps_H_true, eps_HG=eps_HG_true,
            H_total=H_total, n_pts=n_pts,
        )

        eq_mat = np.array([[1, 0, 1], [0, 1, 1]], dtype=float)  # (2 comps, 3 species)
        # species: H_free(0), G_free(1), HG(2)
        # specToLinear shape: (n_species=3, n_obs=1)
        # eps params
        eps_H_p = LMFitParameter("eps_H_free_abs", value=800.0, min=0.1, max=1e5)
        eps_G_p = LMFitParameter("eps_G_free_abs", value=0.0, min=-1e-10, max=1e-10, vary=False)
        eps_HG_p = LMFitParameter("eps_HG_abs", value=3000.0, min=0.1, max=1e5)

        specToLinear = np.empty((3, 1), dtype=object)
        specToLinear[0, 0] = eps_H_p
        specToLinear[1, 0] = eps_G_p
        specToLinear[2, 0] = eps_HG_p

        # Build raw data: [comp_concs | absorbance]
        raw_data = np.hstack([comp_concs, absorbance])

        model = bd.bindingModel(
            eqMat=eq_mat,
            compNames=["H", "G"],
            speciesList=["H", "G", "HG"],
            colToComp=np.eye(2),  # columns 0,1 → comp H, G
            rawData=raw_data,
        )
        model.specToLinear = specToLinear
        model.prepModel()

        # Fix G to 0 (dark) — for the numerical path, just set it to fixed 0 float
        # by replacing the matrix entry. The parameter was registered with value=0.0
        # and vary=False, but lmfit disallows min==max==0, so we use a small nonzero bound.
        model.params["eps_G_free_abs"].set(value=0.0, vary=False, min=-1e-10, max=1e-10)

        model.runModel(skip_col=2, method="least_squares")

        assert model.miniResult is not None
        assert model.miniResult.success or model.miniResult.redchi < 1e-3

        recovered_log_beta = model.miniResult.params["logHG"].value
        assert abs(recovered_log_beta - log_beta_true) < 0.2, (
            f"Expected logβ ≈ {log_beta_true}, got {recovered_log_beta:.3f}"
        )


# ---------------------------------------------------------------------------
# 9. End-to-end: analytical path with synthetic UV-vis data
# ---------------------------------------------------------------------------

class TestAnalyticalUVvisFit:
    """Verify the analytical fast-exchange path works for UV-vis observables."""

    def test_analytical_uvvis_fit_recovers_log_beta(self):
        """fitfun_analytical_fast_exchange with UV-vis observables recovers log_beta."""
        log_beta_true = 6.0
        H_total = 1e-4
        n_pts = 20
        eps_H = 1000.0
        eps_HG = 5000.0

        G_total = np.linspace(0, 2e-4, n_pts)
        beta = 10 ** log_beta_true
        b_coef = -(H_total + G_total + 1.0 / beta)
        c_coef = H_total * G_total
        HG = (-b_coef - np.sqrt(b_coef ** 2 - 4 * c_coef)) / 2.0
        H_free = H_total - HG
        G_free = G_total - HG
        absorbance = eps_H * H_free + eps_HG * HG

        comp_concs = np.column_stack([np.full(n_pts, H_total), G_total])
        eq_mat = np.array([[1, 0, 1], [0, 1, 1]], dtype=float)  # (2 comps, 3 species)
        raw_data = np.hstack([comp_concs, absorbance.reshape(-1, 1)])

        eps_H_p = LMFitParameter("eps_H_free_abs", value=800.0, min=0.1, max=1e5)
        eps_G_p = LMFitParameter("eps_G_free_abs", value=0.0, min=-1e-10, max=1e-10, vary=False)
        eps_HG_p = LMFitParameter("eps_HG_abs", value=3000.0, min=0.1, max=1e5)

        specToLinear = np.empty((3, 1), dtype=object)
        specToLinear[0, 0] = eps_H_p
        specToLinear[1, 0] = eps_G_p
        specToLinear[2, 0] = eps_HG_p

        model = bd.bindingModel(
            eqMat=eq_mat,
            compNames=["H", "G"],
            speciesList=["H", "G", "HG"],
            colToComp=np.eye(2),
            rawData=raw_data,
        )
        model.specToLinear = specToLinear
        model.analytical_fast_exchange = True
        model.analytical_topology = "1:1"
        model.analytical_complex_indices = [2]  # HG is species index 2
        model.analytical_obs_columns = []       # no NMR shift columns
        model.analytical_obs_components = []
        # analytical_linear_obs_param_map: per obs-col, per species
        model.analytical_linear_obs_param_map = [
            ["eps_H_free_abs", None, "eps_HG_abs"]  # species: H_free, G_free, HG
        ]

        model.prepModel()
        model.params["eps_G_free_abs"].set(value=0.0, vary=False, min=-1e-10, max=1e-10)

        model.runModel(skip_col=2, method="least_squares")

        assert model.miniResult is not None
        recovered = model.miniResult.params["logHG"].value
        assert abs(recovered - log_beta_true) < 0.2, (
            f"Expected logβ ≈ {log_beta_true}, got {recovered:.3f}"
        )
