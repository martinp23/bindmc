import numpy as np
import pandas as pd
from lmfit import Parameter as LMFitParameter
from lmfit import Parameters

from bindmc.webgui.classes import ChemicalShiftParam, ExptData, Model, RawData


def _new_expt(columns: list[str]) -> ExptData:
    raw = RawData(filename="raw.csv", data=pd.DataFrame({c: [1.0, 2.0] for c in columns}))
    model = Model(name="test-model")
    return ExptData(name="test-expt", init_model=model, init_raw_data=raw)


def test_sanitizes_special_characters_and_lmfit_accepts_names():
    expt = _new_expt(["H shift (ppm)"])
    expt.limiting_shifts[("HG_free", "H shift (ppm)")] = ChemicalShiftParam(
        species="HG_free",
        col="H shift (ppm)",
        value=7.2,
        fixed=False,
    )

    matrix = expt.build_delta_to_spec(
        spec_vectors=[np.array([1.0])],
        species_names=["HG_free"],
        row_columns=["H shift (ppm)"],
    )
    cell = matrix[0, 0]
    assert isinstance(cell, LMFitParameter)

    # Regression check: sanitized name must be a valid lmfit Parameters key.
    pars = Parameters()
    pars.add(cell.name, value=1.0)
    assert cell.name in pars
    assert " " not in cell.name
    assert "(" not in cell.name
    assert ")" not in cell.name


def test_collision_gets_deterministic_numeric_suffix():
    expt = _new_expt(["A-B", "A B"])
    expt.limiting_shifts[("S_free", "A-B")] = ChemicalShiftParam(
        species="S_free",
        col="A-B",
        value=1.0,
        fixed=False,
    )
    expt.limiting_shifts[("S_free", "A B")] = ChemicalShiftParam(
        species="S_free",
        col="A B",
        value=2.0,
        fixed=False,
    )

    matrix = expt.build_delta_to_spec(
        spec_vectors=[np.array([1.0]), np.array([1.0])],
        species_names=["S_free"],
        row_columns=["A-B", "A B"],
    )
    p1 = matrix[0, 0]
    p2 = matrix[1, 0]
    assert isinstance(p1, LMFitParameter)
    assert isinstance(p2, LMFitParameter)
    assert p1.name == "delta_S_free_A_B"
    assert p2.name == "delta_S_free_A_B_2"
    assert p1.name != p2.name


def test_cache_reuses_same_parameter_object_for_same_species_and_column():
    expt = _new_expt(["H shift (ppm)"])
    expt.limiting_shifts[("HG_free", "H shift (ppm)")] = ChemicalShiftParam(
        species="HG_free",
        col="H shift (ppm)",
        value=5.5,
        fixed=False,
    )

    matrix = expt.build_delta_to_spec(
        spec_vectors=[np.array([1.0]), np.array([1.0])],
        species_names=["HG_free"],
        row_columns=["H shift (ppm)", "H shift (ppm)"],
    )
    assert matrix[0, 0] is matrix[1, 0]


def test_fixed_shift_entries_remain_float():
    expt = _new_expt(["H shift (ppm)"])
    expt.limiting_shifts[("HG_free", "H shift (ppm)")] = ChemicalShiftParam(
        species="HG_free",
        col="H shift (ppm)",
        value=3.14,
        fixed=True,
    )

    matrix = expt.build_delta_to_spec(
        spec_vectors=[np.array([1.0])],
        species_names=["HG_free"],
        row_columns=["H shift (ppm)"],
    )
    cell = matrix[0, 0]
    assert isinstance(cell, float)
    assert cell == 3.14

