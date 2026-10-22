# Open questions from implementing the layout design

Questions and findings that came up while implementing [README.md](README.md). None of them blocks the current phase; each needs a
decision afterwards. Phase 0 pins the current behaviour of everything listed under "Bugs found by phase 0"; fixing one is its own change
that updates its test on purpose.

## Test environment

1. **Where the haad tests run.** `tests/haad/` needs haad (Python 3.14), which is not installed as a package in its own uv environment
   (no `[build-system]`). The tests run in haad's environment with `PYTHONPATH=../haad` (`make test-haad`). Poetry is not involved,
   so the circular editable dependency (haad -> openhasp-config-manager -> haad) never comes up. Is that good enough, or should
   openhasp-config-manager get its own uv environment with haad as a dev dependency?
2. **`tests/ad/`** imports `openhasp_config_manager.ad`, which needs `appdaemon`, which no environment installs. `tests/conftest.py`
   now skips it (and `tests/haad/` without haad) instead of failing the collection. Delete the AppDaemon controller and its test?

## Bugs found by phase 0

Each one is pinned by a test in `tests/haad/` (named in brackets).

3. **Switch and scene button clicks don't work and drop the MQTT connection.** `SwitchObjectController._toggle_entity()` calls
   `controller.get_entity()` and `SceneButtonObjectController` calls `controller.call_service()`; `HaadController` has neither (left
   over from the AppDaemon API). The `AttributeError` is raised inside `MqttClient`'s message loop, which ends the connection and
   reconnects after 5 seconds; all plate events in between are lost. Only pages that are not deployed today (markus, bathroom) use
   them. Fix: `ha.perform_action("homeassistant/toggle", ...)` and `"scene/turn_on"`? And should `MqttClient._handle_message()`
   isolate callback errors so one broken callback can't end the connection? (`test_switch_click_fails_and_drops_the_mqtt_connection`,
   `test_scene_button_click_fails_and_drops_the_mqtt_connection`)
4. **An error in an immediate reaction aborts the whole plate setup.** `react_to(immediately=True)` propagates exceptions out of
   `ObjectController.init()`, through `initialize_objects()` and `PlateController.init()`, into `__failsafe_plate_setup()`, which
   logs it and does not retry. Triggered by: a switch or bar whose entity is `unknown`/`unavailable` at startup (the reaction gets
   `None`: `None.lower()` / `float(None)`), and a switch with a list of entities (the Markus page's light strip). Should a failing
   object only log, and the rest of the plate still come up? (`test_switch_with_unknown_entity_fails_init`,
   `test_switch_with_entity_list_fails_init`, `test_bar_with_unavailable_entity_fails_init`)
5. **The switch's StateUpdater sync always fails.** Its getter returns a `bool`, its setter calls `.lower()` on it. So a reconnect
   never restores a switch, and a switch with only `get_state` never shows anything. (`test_switch_follows_entity`,
   `test_switch_with_get_state_never_shows_a_state`)
6. **Labels show `None`.** `add_label()`'s default `text=lambda x: str(x)` replaces `LabelObjectController`'s default, which shows `-`
   for `None`. And for an entity that is `unknown` at startup, the sync shows `-` but the immediate reaction (haad passes `None`)
   shows `None` right after. (`test_label_shows_none_from_get_state`, `test_label_with_unknown_entity`)
7. **A label with `get_state` calls it twice per sync** (once in the getter, once more in the change handler).
   (`test_label_with_get_state_and_entity_list`)
8. **The slider doesn't follow its entity**, it is only set on syncs (plate setup, reconnect). (`test_slider_syncs_entity_state_but_does_not_follow_it`)
9. ~~**`CheckboxObjectController` is broken**~~: fixed. It imports `EntityTrigger` and `HaadStateEvent`, only registers a state when it
   has an entity or a `get_state`, and stays disabled while the entity has no valid state. It still only sets the text, not `val`
   (checked), and no page uses it yet (24). (`test_checkbox_*`)
10. **Object event subscriptions are never cancelled.** `OpenHaspClient.listen_state()` subscribes a wrapper of the callback, while
    the cancel task of `util_openhasp.listen_state()` unsubscribes the callback itself, which matches nothing. Buttons, switches and
    sliders stay subscribed after `terminate()`. Harmless while haad never sets a plate up twice in one process, but the design's
    re-push on `LWT online` must not register objects again. (`test_listen_state_parses_json_and_is_never_cancelled`)
11. ~~**`DeploymentController.deploy()` fails**: `ConfigUploader` calls the async `OpenHaspClient.get_files()` without awaiting it.~~
    Fixed: `ConfigUploader` is async now, which also fixes the CLI `deploy` and `upload`.
    (`test_deploy_uploads_the_generated_files_and_the_config`)
12. **The gui config goes to two different names.** `PlateController.set_gui_config()` publishes to `hasp/<controller name>/config/gui`
    (the haad registry name), everything else uses the plate's MQTT name from its config. They are the same for all of haad-home's
    plates; the device factory (§4.1) should use one source. (`test_always_on_display_while_any_page_requests_it`)
13. **Auto brightness listeners pile up** if `setup_auto_brightness()` runs twice (README §7 already names this one).
    (`test_setup_auto_brightness_again_adds_a_second_listener`)
14. **haad-home's bathroom page shows icon names instead of icons.** `IntegratedIcon` is a plain `Enum` without `__str__`, so
    `f"{IntegratedIcon.LIGHTBULB_ON}"` is `"IntegratedIcon.LIGHTBULB_ON"`, not `""` (use `.unicode`). The page is not
    deployed today. See also 15.

## Decisions taken during implementation (please confirm)

15. **No new `Icon` enum (§4.6).** `openhasp_client.icons.IntegratedIcon` already has the code points (`.unicode`). Instead of a second
    enum: should `IntegratedIcon` get `__str__`/`__format__` returning the code point (fixes 14, and `Label(text=IntegratedIcon.RUN)`
    just works), or should it become a `StrEnum`? Either changes what `str()` returns for the GUI, which uses `.name`/`.unicode` today.
16. **`Rect` helpers need pixels.** §4.8 said the helpers "resolve percentages against the screen first", but a `Rect` doesn't know the
    screen. `Rect.resolve(width, height)` turns percentages into pixels, and `inset()`/`rows()`/`cols()`/`grid()` raise for a `Rect`
    with percentages. Inside a tree, percentages are resolved against the parent automatically.
17. **Rounding is cumulative** instead of "the last child absorbs the remainder" (§4.3): each weighted child ends at
    `floor(remaining * cumulative_weight / total_weight)`. Same guarantee (no gaps, no overlaps, exact total), but the remainder is spread
    instead of piling up in the last child. Fixed sizes (pixels, percentages) are exact; with no weighted children the rest stays empty.
18. **Fixed sizes that don't fit raise** (`split()`), instead of producing negative sizes.
19. **`Theme.background_color`** becomes `bg_color` of `p<N>b0` of every owned page (§4.5 didn't say where it goes).
20. **`Page` places its children like a `Column`** (§4.3 only said it is the root).
21. **The plate pipeline runs page by page** (build, mount, register, render, push, initialize; then the next page) instead of each
    step for all pages (§5.1). That keeps the traffic of today's plates exactly as it was (the phase-0 tests didn't change).
22. **No pause between pushed messages** (§5.4). haad has no sleep on its runtime clock, and waiting for a `schedule()` inside the plate
    setup (itself a scheduled callback) deadlocks the simulator's clock, which runs timer callbacks one after another. With 2 kB batches
    a page is a few messages. If the plate struggles: add an `await runtime.sleep(...)` to haad that the simulator can serve while a
    timer callback runs?
23. **Owned objects defer property changes until their page is pushed**: `set_object_properties()`, `set_text()` and `set_hidden()`
    merge into the object's `props` (and with them into the JSONL) instead of sending commands that the push's `clearpage` would wipe.
    Not covered: `push_image()` on an owned image in `register_objects()` still sends right away (and is lost). Defer it too, or raise?
24. **No `Checkbox` leaf / `add_checkbox()`** yet (§4.4 lists them). `CheckboxObjectController` works now (9); should it follow the
    entity with `val` (checked) instead of the text?
25. **The page frame is `MarkusCodePageController`**, a separate class next to `MarkusPageController` (§4.7 put it into
    `MarkusPageController`). Its `build_layout()` creates owned objects, which would turn every existing flash page into a mixed page,
    and mixed pages raise. Merge the two once all pages are code-defined?
26. **`layout_dump_dir`** is a new field of haad-home's `OpenHaspControllerParams`, default `./openhasp-configs.output/haad` (relative to
    the working directory, like `config_dir`). The container uses `/conf/...` paths for `config_dir`: same for the dumps?
27. **`theme.yaml`'s `theme.obj.*` keys are applied verbatim** by `ObjectThemeProcessor`, so today every JSONL `btn` also gets
    `bg_color_pressed`, `icon_size`, ... and every `switch` `bg_color_on`, ... which are no openHASP properties (the plate ignores them).
    `MARKUS_THEME` (haad-home `openhasp/theme.py`) uses the properties the JSONL files assign these values to. Rename the keys in
    `theme.yaml` to real properties as well?
28. **Screen size and rotation**: the device config swaps width and height for rotated screens (`gui.rotate` odd), so layouts use the
    size the pages see. `PlateConfig.screen` is that size as well (after rotation). The test device is 320x480, rotated: 480x320.
29. **`trigger=` refreshes all StateUpdater entries of the object** (its value, its static props, its `Bound` props). The de-duplication
    keeps props from being re-sent, but a label's text is re-sent on every tick (like with `TIME_SECOND_ENTITY` today).
30. **Step 13 (migrating a page of `wt32sc01plus_2`) is not done.** It changes a deployed plate, and the page's JSONL must be removed
    from its `boot.cmd` and the plate deployed once (§6), otherwise the page is a mixed page. Which page first, and when?
31. **Pillow deprecation**: `OpenHaspImageProcessor` uses `Image.getdata()`, deprecated for Pillow 14 (2027-10-15).
32. **Explicit ids in `register_objects()` can collide with auto ids** of objects declared before them (they raise "already exists").
    Explicit ids of the tree are reserved before mounting, but `register_objects()` runs after the tree is mounted, so its explicit
    ids can't be reserved in advance. Fine (fail fast), or should `register_objects()` run first?

## The alerts page (first code-defined page)

33. **Every push clears the page**, also on `LWT online` (§5.2 said: no clear, to avoid flicker on reconnects). `wt32sc01plus_2`'s
    `boot.cmd` puts `p4b1` (header `btn`) and `p4b3` (background `obj`) on page 4 (`common/page/header.jsonl` and
    `common/content/bg.jsonl` cover pages 1-9). After a plate reboot, an update without clear would keep them as `btn`/`obj` with
    the alerts page's properties, since an update can't change an object's type. The price: a reconnect without reboot makes owned
    pages flicker once. Alternative: drop pages from those files once code-defined pages use them.
34. **Navigation is chained through all pages** (§4.7 said: only first and last). Flash sets `p3b0.next=1` (`last_page: 3` in
    `device.vars.yaml`), which made page 4 unreachable by swiping. Now haad sets `prev`/`next` of every page (1 ⇄ 2 ⇄ 3 ⇄ 4 ⇄ 1),
    overriding the flash values. Update `last_page` in `device.vars.yaml` to 4 as well, so the plate navigates right before haad
    is up?
35. **`MarkusOpenHaspController.plate_config` now sets `theme=MARKUS_THEME`** (otherwise the defaults as before). `wt32sc01plus_1`
    overrides `plate_config` without a theme; it has no code-defined pages.
36. **(Partly done.) The alerts are fixed when the page is built** (once per haad process): the tree has one card per alert.
    Now each card follows a source (`Bound` colours, icon and text from `get_state`, `hidden` while there is no alert), e.g. the
    front door card only shows while the door is open. A node with a bound `hidden` takes no space in its `Row`/`Column`/`Grid`
    while hidden (`LayoutNode.set_collapsed()`): the layout is computed again and only the `x`/`y`/`w`/`h` of the objects that moved
    are sent, so a column of conditional cards is a list from the top. This is no general partial layout update: objects are
    never added or removed at runtime. Give cards in such a column a fixed `size=`: with weights, the shown ones grow into the
    space of the hidden ones. Where should the alerts come from?
    Since then: `Repeat` (README §4.4.1) creates and deletes the cards at runtime, one per current alert. Not verified on a real plate yet:
    that `delete` removes the children of an object, and that a single JSONL object can be added to a page that is shown.
37. **Clock in the header**: `MarkusCodePageController` binds `TIME_ENTITY` like `register_header_clock()` does on the flash pages.
38. **Vertical centring of card text**: labels only align horizontally, so a card centres a label of one line between spacers.
    28 px was too low for `text_font=24` (the font's line height includes the merged MDI icons): the text overflowed, so "dots" cut
    it early and "scroll" scrolled it vertically. Now 34 px, still a guess. The library can't know font metrics; a table of line
    heights per built-in font size (12/16/24/32) in the library would let layouts size labels to their font.
39. **The alert count in the header** refreshes every 10 s (`Trigger.Time.every`), not on every change of the four sources. A
    trigger on all sources at once (a list of entities plus the time trigger) would need `trigger=` to accept that composite.
40. **haad-home's `markus.py` uses `co2_sensor.carbon_dioxide.entity_id`**, but `carbon_dioxide` is a method of `Co2Sensor`
    (`carbon_dioxide_sensor` is the entity). The page isn't deployed; it would fail at setup. The alerts page uses
    `carbon_dioxide_sensor`.

## Page claims (`plate/scheduler.py`)

`PlateBehavior`, `request_plate_behavior()` and friends are gone: a page declares `claim(active=, trigger=, priority=, keep_awake=,
wake=)` and the plate's `PageScheduler` decides the page and whether the screen stays on.

41. **Equal priority takes the page**: a newly active claim shows its page when it is among the highest-priority claims, even
    if another claim of the same priority is shown (as `go_to_this_page()` did before). Only a higher priority was meant to
    "preempt" in the proposal; the newest-wins rule keeps the old media/printer behaviour. Confirm.
42. **Lower priorities starve**: only the claims of the highest active priority are shown or rotated. A NORMAL media page is
    never shown while a HIGH claim is active. Rotating across tiers (weighted) was not done.
43. **Touch detection is limited to what the plate reports**: object events (`down`, `up`, `short`, `long`, ...), page changes
    haad didn't ask for (swipes), and `state/idle off` (a touch wakes a dimmed screen; the docs say `idle off` acts "as if a touch
    event occurred", and the state is published on changes). Not detected: a tap on the empty background while the screen is
    awake, unless the page area (`pXb0`) publishes events, which the docs don't say; to find out, subscribe to `hasp/<name>/state/#`
    on the plate and tap an empty area. haad's own `idle off` (wakeups, end of keep-awake) echoes as a touch too: a spurious pin of
    `pin` seconds.
44. **Defaults are guesses**: dwell 15 s, pin 60 s, `home_page=None` (stay on the last page when the last claim ends, as before).
    The alerts page claims `Priority.CRITICAL` with `keep_awake` and `wake` for critical alerts only; "wake" turns the screen on
    but doesn't dim it again by itself (see the TODO in `PlateController.wakeup()`).
45. **A reconnect resets the pin** (`resync()` after LWT online): the plate has restarted, so the page and screen config are
    applied again from the active claims.
46. **The printer page**: it still wakes the plate when the stage leaves the active states (to show the finished status),
    next to its claim. Could become a claim with a `wake` on end, but a claim only acts on activation.
47. **`PlateBehavior.ALWAYS_ON_DISPLAY` is now only `keep_awake`**; there is no other behaviour. The plate's idle config
    (15 s / never) while awake is hard coded in `PlateController.set_keep_awake()`.
