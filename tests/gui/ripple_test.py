from openhasp_config_manager.gui.domain.ripple import RIPPLE_DURATION, RIPPLE_RADIUS, Ripple, active_ripples
from tests import TestBase


class TestRipple(TestBase):
    def test_grows_and_fades(self):
        ripple = Ripple(x=1, y=2, started=10.0)

        assert (ripple.radius(10.0), ripple.opacity(10.0)) == (0, 1)
        assert 0 < ripple.radius(10.0 + RIPPLE_DURATION / 2) < RIPPLE_RADIUS
        assert (ripple.radius(10.0 + RIPPLE_DURATION), ripple.opacity(10.0 + RIPPLE_DURATION)) == (RIPPLE_RADIUS, 0)
        # before it started (clock jumps) and long after
        assert ripple.progress(9.0) == 0
        assert ripple.progress(99.0) == 1

    def test_active_ripples_drops_finished_ones(self):
        old = Ripple(x=0, y=0, started=0.0)
        new = Ripple(x=0, y=0, started=10.0)

        assert active_ripples([old, new], now=10.0 + RIPPLE_DURATION / 2) == [new]
