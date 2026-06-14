from webgui.components.bayes import _chain_height_px, _corner_height_px, _corner_width_pct


def test_corner_width_policy_breakpoints():
    assert _corner_width_pct(1) == 56
    assert _corner_width_pct(3) == 56
    assert _corner_width_pct(4) == 68
    assert _corner_width_pct(5) == 80
    assert _corner_width_pct(12) == 80


def test_chain_height_scales_with_dimension_and_clamps():
    h2 = _chain_height_px(2)
    h5 = _chain_height_px(5)
    h20 = _chain_height_px(20)

    assert h5 > h2
    assert h20 >= h5
    assert h2 >= 500
    assert h20 <= 2400


def test_corner_height_scales_with_dimension_and_clamps():
    h2 = _corner_height_px(2)
    h5 = _corner_height_px(5)
    h20 = _corner_height_px(20)

    assert h5 > h2
    assert h20 >= h5
    assert h2 >= 420
    assert h20 <= 1400
