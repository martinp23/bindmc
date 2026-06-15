from bindmc.webgui.utils import eqMatFromEqnStr, eqMatFromStr, eq_mat_from_equation_str_infer_components
import numpy as np
import pytest

pytest_plugins = ["nicegui.testing.user_plugin"]


async def test_eqMatFromStr() -> None:
    # Set up test data
    eq_strs = []

    eq_strs.append("[[1, 0, 1], [0, 1, 1]]")
    eq_strs.append("[1, 0, 1]\n[0, 1, 1]")
    eq_strs.append("1, 0, 1\n0, 1,1")
    eq_strs.append("1 0 1\n0 1 1")

    expected_result = np.array([[1, 0, 1], [0, 1, 1]], dtype=float)

    for eq_str in eq_strs:
        result = eqMatFromStr(eq_str)

        # Assert the result matches the expected output
        assert np.array_equal(result, expected_result)
    # result = eqMatFromStr2(eq_str)

    # # Expected result
    # expected_result = np.array([[1, 0, 1], [0, 1, 1]], dtype=float)

    # # Assert the result matches the expected output
    # assert np.array_equal(result, expected_result)


async def test_eqMatFromEqnStrInfer1to2() -> None:
    # Set up test data
    eq_str = "H + G <=> HG;H + 2G <=> HG2"
    expected_result = np.array([[1, 0, 1, 1], [0, 1, 1, 2]], dtype=float)

    # Call the function to test
    result = eq_mat_from_equation_str_infer_components(eq_str)[0]

    # Assert the result matches the expected output
    assert np.array_equal(result, expected_result)


async def test_eqMatFromEqnStr1to1() -> None:
    # Set up test data
    eq_str = "H + G <=> HG"
    expected_result = np.array([[1, 0, 1], [0, 1, 1]], dtype=float)

    components = ["H", "G"]

    # Call the function to test
    result = eqMatFromEqnStr(eq_str, components)[0]

    # Assert the result matches the expected output
    assert np.array_equal(result, expected_result)


async def test_eqMatFromEqnStr1to2() -> None:
    # Set up test data
    eq_str = "H + G <=> HG;H + 2G <=> HG2"
    expected_result = np.array([[1, 0, 1, 1], [0, 1, 1, 2]], dtype=float)

    components = ["H", "G"]
    # Call the function to test
    result = eqMatFromEqnStr(eq_str, components)[0]

    # Assert the result matches the expected output
    assert np.array_equal(result, expected_result)


# unbalanced equation should raise ValueError
async def test_eqMatFromEqnStrUnbalanced() -> None:
    # Set up test data
    eq_str = "H + G <=> HG2"

    components = ["H", "G"]
    # Call the function to test
    with pytest.raises(ValueError):
        eqMatFromEqnStr(eq_str, components)


async def test_eqMatFromEqnStr1to2_equalsign() -> None:
    # Set up test data
    eq_str = "H + G = HG;H + 2G = HG2"
    expected_result = np.array([[1, 0, 1, 1], [0, 1, 1, 2]], dtype=float)

    components = ["H", "G"]
    # Call the function to test
    result = eqMatFromEqnStr(eq_str, components)[0]

    # Assert the result matches the expected output
    assert np.array_equal(result, expected_result)


async def test_eqMatFromEqnStr1to2_both_equalsign() -> None:
    # Set up test data
    eq_str = "H + G <=> HG;H + 2G = HG2"
    expected_result = np.array([[1, 0, 1, 1], [0, 1, 1, 2]], dtype=float)

    components = ["H", "G"]
    # Call the function to test
    result = eqMatFromEqnStr(eq_str, components)[0]

    # Assert the result matches the expected output
    assert np.array_equal(result, expected_result)


# unbalanced equation should raise ValueError
async def test_eqMatFromEqnStrUnbalanced_equalsign() -> None:
    # Set up test data
    eq_str = "H + G = HG2"

    components = ["H", "G"]
    # Call the function to test
    with pytest.raises(ValueError):
        eqMatFromEqnStr(eq_str, components)


# unbalanced equation should raise ValueError
async def test_eqMatFromEqnStrMissingComp() -> None:
    # Set up test data
    eq_str = "H + G <=> HF2"

    components = ["H", "G"]
    # Call the function to test
    with pytest.raises(ValueError):
        eqMatFromEqnStr(eq_str, components)


# A species on the LHS should raise NotImplementedError
async def test_eqMatFromEqnStrSpeciesOnLHS() -> None:
    # Set up test data
    eq_str = "HG + G <=> HG2"

    components = ["H", "G"]
    # Call the function to test
    with pytest.raises(NotImplementedError):
        eqMatFromEqnStr(eq_str, components)


# in this case, the equation is balanced, but the stoichiometry is weird: everything is multiplied by 2
async def test_eqMatFromEqnStrDuplicatedStoich() -> None:
    # Set up test data
    eq_str = "2H + 2G <=> 2HG"
    expected_result = np.array([[1, 0, 1], [0, 1, 1]], dtype=float)

    components = ["H", "G"]

    # Call the function to test
    result = eqMatFromEqnStr(eq_str, components)[0]

    # Assert the result matches the expected output
    assert np.array_equal(result, expected_result)


# in this case, we have complex stoichiometry, but should still just return the basic eq matrix
# as derived from the species names
async def test_eqMatFromEqnStrWeirdStoich() -> None:
    # Set up test data
    eq_str = "5H + 7G <=> 3HG + 2HG2"
    expected_result = np.array([[1, 0, 1, 1], [0, 1, 1, 2]], dtype=float)

    components = ["H", "G"]

    # Call the function to test
    result = eqMatFromEqnStr(eq_str, components)[0]

    # Assert the result matches the expected output
    assert np.array_equal(result, expected_result)
