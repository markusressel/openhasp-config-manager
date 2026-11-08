"""When the Live device view takes a screenshot of a plate (`ScreenshotScheduler`, Qt-free)."""

from openhasp_config_manager.gui.domain.connection import LinkState
from openhasp_config_manager.gui.domain.live_screen import (
    BACKOFF_MAX,
    BACKOFF_START,
    MAX_CHANGE_WAIT,
    ScreenChange,
    ScreenshotScheduler,
    age_text,
    backoff_delay,
    reachable,
    status_text,
)


def _shown(interval: float = 30, now: float = 0.0, first: bool = True) -> ScreenshotScheduler:
    """A scheduler of a plate that is shown and reachable; with `first` the first screenshot was taken at `now`."""
    scheduler = ScreenshotScheduler(interval)
    scheduler.set_visible(True)
    scheduler.set_reachable(True, now)
    if first:
        assert scheduler.poll(now)
        scheduler.succeeded(now)
    return scheduler


def _take(scheduler: ScreenshotScheduler, now: float) -> bool:
    """:return: whether a screenshot is taken at `now` (it works right away)"""
    if not scheduler.poll(now):
        return False
    scheduler.succeeded(now)
    return True


class TestInterval:
    def test_first_screenshot_as_soon_as_the_plate_is_shown(self):
        scheduler = _shown(first=False)
        assert scheduler.poll(0.0)

    def test_interval(self):
        scheduler = _shown(interval=30)
        assert scheduler.next_wakeup() == 30
        assert not scheduler.poll(29.9)
        assert _take(scheduler, 30.0)
        assert scheduler.next_wakeup() == 60

    def test_no_interval_only_after_changes(self):
        scheduler = _shown(interval=0)
        assert scheduler.next_wakeup() is None
        assert not scheduler.poll(1000.0)
        scheduler.screen_changed(ScreenChange.COMMAND, 1000.0)
        assert _take(scheduler, 1000.0 + ScreenChange.COMMAND.delay)

    def test_changing_the_interval(self):
        scheduler = _shown(interval=300)
        scheduler.set_interval(10)
        assert scheduler.next_wakeup() == 10


class TestChanges:
    def test_shortly_after_a_change(self):
        scheduler = _shown(interval=300)
        scheduler.screen_changed(ScreenChange.RESTORED, 5.0)
        assert not scheduler.poll(5.0 + ScreenChange.RESTORED.delay - 0.1)
        assert _take(scheduler, 5.0 + ScreenChange.RESTORED.delay)
        # the interval starts again from there
        assert scheduler.next_wakeup() == 5.0 + ScreenChange.RESTORED.delay + 300

    def test_live_preview_sends_wait_until_they_are_quiet(self):
        scheduler = _shown(interval=300)
        delay = ScreenChange.LIVE_PREVIEW.delay
        # typing into a property: a send per keystroke, every half second
        for keystroke in range(6):
            now = 10.0 + keystroke * 0.5
            scheduler.screen_changed(ScreenChange.LIVE_PREVIEW, now)
            assert not scheduler.poll(now)
        last = 10.0 + 5 * 0.5
        assert scheduler.next_wakeup() == last + delay
        assert not scheduler.poll(last + delay - 0.1)
        assert _take(scheduler, last + delay)
        assert not scheduler.poll(last + delay + 5)

    def test_a_series_of_changes_is_shown_at_the_latest_after_max_wait(self):
        scheduler = _shown(interval=300)
        now = 10.0
        taken = []
        # dragging with Live preview: changes all the time
        while now < 10.0 + 2 * MAX_CHANGE_WAIT:
            scheduler.screen_changed(ScreenChange.LIVE_PREVIEW, now)
            if _take(scheduler, now):
                taken.append(now)
            now += 0.25
        assert taken[0] == 10.0 + MAX_CHANGE_WAIT

    def test_a_slower_change_is_not_shown_earlier_by_a_quicker_one(self):
        scheduler = _shown(interval=300)
        scheduler.screen_changed(ScreenChange.RESTORED, 10.0)
        scheduler.screen_changed(ScreenChange.COMMAND, 10.5)
        assert scheduler.next_wakeup() == 10.0 + ScreenChange.RESTORED.delay


class TestCoalescing:
    def test_never_two_at_once_and_one_follow_up(self):
        scheduler = _shown(interval=30)
        scheduler.refresh()
        assert scheduler.poll(1.0)
        assert scheduler.running
        # asked for again and again while it runs
        scheduler.refresh()
        scheduler.screen_changed(ScreenChange.COMMAND, 1.5)
        scheduler.refresh()
        assert not scheduler.poll(2.0)
        assert scheduler.next_wakeup() is None
        scheduler.succeeded(5.0)
        # one screenshot follows, then none
        assert _take(scheduler, 5.0)
        assert not scheduler.poll(6.0)

    def test_what_was_asked_for_before_it_started_is_in_it(self):
        scheduler = _shown(interval=30)
        scheduler.screen_changed(ScreenChange.LIVE_PREVIEW, 25.0)
        # the interval comes first and shows the change
        assert _take(scheduler, 30.0)
        assert scheduler.next_wakeup() == 60

    def test_manual_refresh_right_away(self):
        scheduler = _shown(interval=300)
        scheduler.refresh()
        assert scheduler.poll(1.0)


class TestBackoff:
    def test_delays(self):
        assert backoff_delay(0) == 0
        assert backoff_delay(1) == BACKOFF_START
        assert backoff_delay(2) == 2 * BACKOFF_START
        assert backoff_delay(100) == BACKOFF_MAX

    def test_waits_longer_after_each_failure(self):
        scheduler = _shown(interval=10)
        now = 10.0
        waits = []
        for _ in range(4):
            assert scheduler.poll(now)
            scheduler.failed("timeout", now)
            due = scheduler.next_wakeup()
            waits.append(due - now)
            now = due
        assert waits == [BACKOFF_START, 2 * BACKOFF_START, 4 * BACKOFF_START, 8 * BACKOFF_START]
        assert scheduler.state().error == "timeout"
        assert scheduler.state().failures == 4

    def test_changes_dont_shorten_the_backoff(self):
        scheduler = _shown(interval=300)
        assert scheduler.poll(10.0) is False
        scheduler.refresh()
        assert scheduler.poll(10.0)
        scheduler.failed("timeout", 10.0)
        scheduler.screen_changed(ScreenChange.COMMAND, 11.0)
        assert scheduler.next_wakeup() == 10.0 + BACKOFF_START

    def test_manual_refresh_ignores_the_backoff(self):
        scheduler = _shown(interval=10)
        assert scheduler.poll(10.0)
        scheduler.failed("timeout", 10.0)
        scheduler.refresh()
        assert scheduler.poll(11.0)

    def test_success_ends_the_backoff(self):
        scheduler = _shown(interval=10)
        assert scheduler.poll(10.0)
        scheduler.failed("timeout", 10.0)
        scheduler.refresh()
        assert scheduler.poll(11.0)
        scheduler.succeeded(12.0)
        assert scheduler.state().error is None
        assert scheduler.next_wakeup() == 22.0

    def test_plate_back_online_ends_the_backoff_and_takes_one_soon(self):
        scheduler = _shown(interval=300)
        assert not scheduler.poll(10.0)
        scheduler.refresh()
        assert scheduler.poll(10.0)
        scheduler.failed("timeout", 10.0)
        scheduler.set_reachable(False, 12.0)
        scheduler.set_reachable(True, 20.0)
        assert scheduler.state().failures == 0
        assert scheduler.next_wakeup() == 20.0 + ScreenChange.RECONNECTED.delay


class TestPause:
    def test_nothing_while_hidden(self):
        scheduler = _shown(interval=10)
        scheduler.set_visible(False)
        scheduler.refresh()
        scheduler.screen_changed(ScreenChange.RESTORED, 1.0)
        assert not scheduler.poll(100.0)
        assert scheduler.next_wakeup() is None
        assert scheduler.paused == "hidden"

    def test_shown_again_takes_what_is_due(self):
        scheduler = _shown(interval=300)
        scheduler.set_visible(False)
        scheduler.screen_changed(ScreenChange.RESTORED, 1.0)
        assert not scheduler.poll(50.0)
        scheduler.set_visible(True)
        assert _take(scheduler, 50.0)
        # an interval that passed while hidden: right away too
        scheduler.set_visible(False)
        scheduler.set_visible(True)
        assert _take(scheduler, 400.0)

    def test_nothing_while_unreachable(self):
        scheduler = _shown(interval=10)
        scheduler.set_reachable(False, 1.0)
        assert not scheduler.poll(100.0)
        assert scheduler.paused == "unreachable"

    def test_reachable_links(self):
        assert reachable(LinkState.PLATE_ONLINE)
        assert reachable(LinkState.PLATE_UNKNOWN)
        # over HTTP: the plate may answer without the broker
        assert reachable(LinkState.BROKER_UNREACHABLE)
        assert not reachable(LinkState.PLATE_OFFLINE)
        assert not reachable(LinkState.CONNECTING)
        assert not reachable(LinkState.NO_DEVICE)


class TestTexts:
    def test_age(self):
        assert age_text(None, 10.0) == "no image yet"
        assert age_text(10.0, 12.0) == "updated just now"
        assert age_text(10.0, 22.0) == "updated 12 s ago"
        assert age_text(0.0, 150.0) == "updated 2 min ago"

    def test_status(self):
        scheduler = _shown(interval=10)
        assert status_text(scheduler.state(), 12.0) == "Updated 12 s ago"
        assert scheduler.poll(30.0)
        assert status_text(scheduler.state(), 31.0) == "Taking a screenshot…"
        scheduler.failed("timeout", 31.0)
        assert status_text(scheduler.state(), 31.0) == f"Screenshot failed: timeout  ·  retrying in {int(BACKOFF_START)} s"
