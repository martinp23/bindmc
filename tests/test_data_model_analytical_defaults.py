import numpy as np

from bindmc.webgui.utils import _infer_simple_fast_exchange_topology


def test_infer_simple_fast_exchange_topology_variants():
    eq_11 = np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 1.0]])
    eq_12 = np.array([[1.0, 0.0, 1.0, 1.0], [0.0, 1.0, 1.0, 2.0]])
    eq_21 = np.array([[1.0, 0.0, 1.0, 2.0], [0.0, 1.0, 1.0, 1.0]])

    assert _infer_simple_fast_exchange_topology(eq_11, 2) == ("1:1", [2])
    assert _infer_simple_fast_exchange_topology(eq_12, 2) == ("1:2", [2, 3])
    assert _infer_simple_fast_exchange_topology(eq_21, 2) == ("2:1", [2, 3])


def test_infer_simple_fast_exchange_topology_returns_none_for_non_simple():
    eq_non_simple = np.array([[1.0, 0.0, 1.0, 2.0], [0.0, 1.0, 1.0, 2.0]])
    assert _infer_simple_fast_exchange_topology(eq_non_simple, 2) is None
