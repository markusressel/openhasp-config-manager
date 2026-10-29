# Design: tabs in the preview, and one draft for all devices

Status: implemented (all phases, see "Phases").

## Motivation

- **Switching devices reloads the whole window.** There is one `PageLayoutEditorWidget`. Selecting a device clears it and the
  Files tree, loads the device again in the background behind a "Loading" panel, and moves the connection, the log and Live
  preview to the new device. Only the drafts survive (`MainWindow.sessions`, one `PlateSession` per device and startup script).
- **Shared files are edited per device.** Every `PlateSession` holds its own copy of every file it shows, the common ones too
  (`common/parts/dot.jsonl`). Editing a shared part for one device doesn't show on another one, and the two drafts conflict when
  both are saved. The point of the common folder is to share pages between plates (of different screen sizes), so they should be
  edited once and seen on all of them.
- **Part mode has no view of its own.** "Edit the part" keeps the page and only dims what is around the instance. In a small window
  it also opens the "Add object" list and the Properties, and the part bar wraps its title after every word (its instance list
  asks for 32 characters), so little of the preview is left: at 900×600 about a third of the width.

Goal: tabs above the preview. A tab shows the pages of a device or one part. Several devices can be open, each with its own
connection and Live preview, and all of them edit one draft of the files.

## Non-goals

- The text editor keeps its own buffers: it writes files to disk, and the draft reloads them (as today, `SourceEditorSync`).
  Making text edits part of the draft is a later step.
- No change to deployments, the CLI or the file formats.

## Part 1: one draft of the files (Qt-free, `gui/domain/draft/`)

Today `PlateSession` mixes two things: the files as the draft has them (sources, directives, parts), and how one device renders
them (the `DraftRenderer` with the device's variables, the rendered objects, the instances of the parts). They are split:

```python
class ConfigDraft:
    """The files of the config directory as the draft has them, for all devices. Keyed by path (component keys are paths already)."""

    files: Dict[Path, FileDraft]      # a page file: its sources and directives
    parts: Dict[Path, PartDraft]      # a part: its objects (PartDraft exists already)
    history: UndoHistory              # see Part 2

    def is_dirty(self, path: Path) -> bool: ...
    def changes(self) -> List[ComponentChanges]: ...   # what Save writes, for all files
    def add_listener(self, listener: Callable[[FileChange], None]): ...


class DeviceDraft:
    """How one device sees the ConfigDraft: what PlateSession is today, without owning the sources."""

    def __init__(self, config: ConfigDraft, device: Device, renderer: DraftRenderer): ...
    # the API of PlateSession stays: working_objects, set_source_value, add_object, instance_of, ...
```

- `DeviceDraft` keeps the public API of `PlateSession`, so the widgets don't change in this part. `PlateSession` can stay as its
  name until the rename is worth it.
- An edit through any `DeviceDraft` changes the `ConfigDraft`. Every other `DeviceDraft` that shows the changed file renders it again
  (its `DraftChange` listeners fire as for its own edits). The entries (rendered object -> source) stay per device, because a
  device renders a shared object with its own variables.
- Files of one device (`devices/<name>/...`) belong to one `DeviceDraft` only. Common files and parts are shared.
- A file loads once. A device that is loaded later uses the draft of a file that is already in the `ConfigDraft` (with its
  changes), not the disk.
- **Speed:** an edit renders every open device that shows the file. That is 0.45 s per edit and device on the user's config
  today (TODO.md, "The draft expands the directives of every file again"). The active tab renders at once; background tabs render
  debounced, or when Live preview needs their objects. Caching the expansion of directives (the TODO item) becomes more worth it.

## Part 2: undo per file, like IntelliJ

IntelliJ and Android Studio keep the undo history with the document, not with the view: two editors of a file (or the design and XML
views of a layout) share it, and Ctrl+Z undoes the last change of the focused document. A change of several files (a refactoring) is
one *global* step: it can be undone from any of its files, and only as a whole; if one of the files changed again since, IntelliJ
refuses ("following files have changes that cannot be undone").

The same here:

- Each step of the history records the files it changed, with their states before and after (the per-file part of today's
  `DraftState`; sources that didn't change are shared between states, as now).
- **Undo in a tab** undoes the newest step that changed a file the tab shows (a device tab: the files of its pages, common ones
  included; a part tab: the part and the file that includes the instance). So Undo in the tab of device A can undo an edit of a
  shared part made in the tab of device B: it is the same file, and both tabs show it.
- **A step of several files** (an edit in part mode that moves objects of the part and changes a directive, a future "Move to
  file", a paste into several files) is undone as a whole, and only if it is the newest step in each of its files. Otherwise
  Undo is refused with the files that changed since, like IntelliJ.
- Merging (typing into one property, `merge_key`) works as now, per step.
- Saving keeps the history (as now): `mark_saved` moves the lines of the states of the saved files.

## Part 3: part mode belongs to the view

`PlateSession._part_mode` makes the whole draft of a device be in part mode. With a part tab and the pages tab of the same device
open at once, the instance that is edited belongs to the tab:

- The methods that depend on it (`is_selectable`, `read_only_reason`, the edits that `_check_part_mode` guards, `describe_part_mode`
  of the state file) take the instance as an argument, or are called on a small `PartFocus(draft, instance)` that the part tab owns.
- The draft no longer has a part mode. "A part on its own" (`part_alone.py`, the scratch `!include`) becomes a part tab without a
  page of the device.

## Part 4: tabs

```
┌ Devices ┐┌ [● touch_down_1] [○ wt32sc01plus_1] [◆ dot.jsonl · id=12 ×] ┐┌ Properties ┐
│         ││                                                            ││            │
│         ││              preview of the active tab                     ││            │
└─────────┘└────────────────────────────────────────────────────────────┘└────────────┘
```

- **Kinds:** a device tab (the pages of a device, as the center is today) and a part tab (one part, see below). Each tab has its
  own `PageLayoutEditorWidget` (preview, page, zoom, Edit/Interact mode).
- **The Devices list** focuses the tab of the device, or opens one. A tab closes with its ×. The draft of a closed tab stays (it is
  the `ConfigDraft`'s), so closing loses nothing; quitting asks about unsaved changes as now.
- **The panels follow the active tab:** Files, Properties, Code and Page JSONL. Switching tabs points them at the tab's device and
  selection, without loading anything again (the `LoadedDevice` is kept per device). The Properties and Page JSONL panels are parts
  of `PageLayoutEditorWidget` today (`property_editor`, `jsonl_preview`): each tab has its own, and the dock shows the active one.
- **A part tab** ("Edit the part"):
  - shows only the objects of the instance, zoomed to fit them; a "Show the page" toggle in its bar brings back the page around
    it, dimmed (today's view);
  - its bar is one line: the part's name (the path in its tooltip), the instance list, the toggle and "Done" (closes the tab); the
    hints (shared part, devices that saving changes) move into an info icon;
  - it belongs to a device (the instance is one of its pages). Several part tabs can be open, also of the same part on two devices.
- **The title of a tab** marks unsaved changes in the files it shows (`•`), and has a connection dot (Part 5).
- **Save** writes all changed files of the `ConfigDraft` (one draft; like IntelliJ's Save All) and lists them first if there are
  files that the active tab doesn't show. **Revert** asks which: the files of the active tab, or all.

## Part 5: connections, Live preview and the log per device

- **One connection per open device**, not per tab: a device tab and the part tabs of that device share it. `ConnectionController`
  and `PlateLink` become per device; a `PlateConnections` keeps them and closes one when the last tab of its device closes.
- **Live preview per device:** it stays on while the device's tab is in the background, and sends what the edits change for that
  device, also edits made in the tab of another device (a shared part). That is what makes plates of different sizes testable side
  by side. A part tab with Live preview sends the page of its instance.
- **Where the status is shown:**
  - a dot in the title of each tab (connected, connecting, broker unreachable, Live preview on), with the details in its tooltip;
  - a **Plates** panel (dock): one row per open device with its connection, Live preview on/off, the page the plate shows, and
    errors (out-of-sync pages); a click focuses the device's tab;
  - the status bar keeps its connection button (`StatusBar.set_connection`) for the active tab's device only.
- **The log** gets a tab per open device. The active tab of the preview selects the device's log tab; the log of a device
  streams only while its log tab is shown (as today: no connection while nobody looks).

## Part 6: the state file for an AI

`gui-state.json` describes one device today (`describe_device`, `preview.png`). It gets a list of the tabs (kind, device, part,
instance, page, connection, Live preview) and which one is active. The `device` key stays the active tab's device, so the current
readers keep working. Previews are written per device: `preview/<device>.png`, the device's current page. The README section for
LLMs and AGENTS.md are updated with it.

The open tabs and the active one are remembered for the next start (`UiSessionStore`), like the open files of the text editor.

## Phases

Each phase is one PR with tests. Phases on different files run in parallel.

1. **`ConfigDraft` and `DeviceDraft`** (Part 1, `gui/domain/draft/`), with the undo of today (one history) but stored per file.
   The window keeps one device at a time; nothing visible changes except that a shared file is one draft.
2. **Undo per file** (Part 2). After 1.
3. **Part mode in the view** (Part 3). After 1; in parallel with 2 if the two stay in different modules (`part_focus.py`).
4. **Device tabs** (Part 4 without part tabs; `gui/qt/window/`). In parallel with 1-3: it only needs today's `PlateSession` API.
5. **Connections per device** (Part 5). After 4.
6. **Part tabs** and the one-line part bar (Part 4). After 3 and 4. "A part on its own" moves into them.
7. **The state file and restoring tabs** (Part 6). After 5 and 6.

## Decisions

- **Save writes all changed files** of the `ConfigDraft`, like IntelliJ's Save All (with the list first if some aren't shown by the
  active tab).
- **Live preview runs on up to 10 devices at once.** Turning it on for an 11th one says so and names the others; nothing is turned
  off by itself.
- **A part tab renders the whole page** of its instance, also without "Show the page", and only hides the other objects: the object
  references (`b4.w` of a card) have the values of the page.

## Decisions made during implementation

### Phase 2: undo per file

- **One list of steps, not one per file.** `EditHistory` keeps the steps in the order they were made, and each `Step` knows its
  files (`files`, the keys of the files and parts it changed). The steps of one file are the steps of the list that changed it,
  in that order. A device tab undoes the newest step that changed one of the files and parts its `PlateSession` shows
  (`file_keys`, `part_keys`); the steps of files it doesn't show (the own files of other devices) are skipped, not undone.
- **Refused steps.** A step is undone only if no newer step changed one of its files. If one did, the undo is refused with the
  files that changed since (`BlockedStepError` in the history, `UndoRefusedError` with the paths relative to the config directory
  in the session, `OperationStatus.failed` in the window). Such a file is always one the tab doesn't show: a newer step in a
  file it shows would be the one to undo. Nothing is undone in part.
- **Redo is symmetric.** The steps to redo are in the order they were undone; a tab redoes the step undone last in its files,
  and only if no step undone after it changed one of its files (those are redone first). A redone step is the newest step of
  its files again.
- **A new edit drops the steps to redo of the files it changes**, not all of them: the own file of another device keeps what it
  can redo, like a document in IntelliJ. The drop goes on through the files of a dropped step: a step to redo that would be
  redone after a dropped one in one of its files is dropped too (its state before would never come back, and redoing it would
  bring back the changes of the dropped step too). An edit without files (the generic use of `EditHistory`) drops
  everything, as before.
- **Merging stays with the newest step of all files** (`merge_key`, `seal`), as before: an edit in between, also through another
  device, ends the merging. A merged step has the files of all its edits.
- **The Undo and Redo actions** show the step the active tab would undo (`PlateSession.next_undo`, `next_redo`: description,
  files, files changed since). The tooltip lists the files of a step of several files and why it would be refused; the action
  stays enabled, so that the refusal is explained when it is triggered. The window refreshes them when a tab is activated, since
  an edit in another tab can change them without a change of the files of this one.

### Phase 3: part mode in the view

- **Part 3: both ways.** The methods that depend on part mode are those of `PlateSession` with the instance as an argument
  (`part_instance`, None for the objects of the files), and a `PartFocus` (`gui/domain/draft/part_focus.py`) binds them to its
  instance. Until part tabs exist (phase 6) the editor owns the focus (`PageLayoutEditorWidget.part_focus`, edits go through
  `editor.editing`).
- **The draft keeps the instances of the open focuses up to date.** A `PartFocus` registers with its draft until it is
  closed: a save moves the instance with the lines of its `!include`, and a reload finds it again by its description (or
  ends it, `instance` is None then), as for the part mode of the draft before. Alternative: the view finds its instance again
  after every save and reload, which needs the description from before them.

### Phase 5: connections per device

- **Phase 5: `PlateLink` stays in the editor of the device tab.** `PlateConnections` keeps the connection of each open device,
  while Live preview, Clear page and Restore plate stay in the `PageLayoutEditorWidget` that owns them (toolbar, busy state,
  error banner). A device has only one tab until the part tabs (phase 6), which decide how a part tab and the device tab share
  Live preview. `PlateLink` follows the draft of its device itself (`set_session`), so edits from other tabs reach it.
- **Phase 5: the page the plate shows** is what the plate reports on its `state/page` topic. It sends that only when the page
  changes, so the Plates panel shows "–" until the plate switched pages once after connecting.

### Phase 6: part tabs

- **One tab per part and device.** "Edit the part" focuses the part tab of that part and device if there is one (and moves it to
  the instance asked for), else opens one next to the active tab. Its title is `part.jsonl · device`, with `•` while the part or
  a file that includes the instance has unsaved changes. A part on its own is a part tab too (`PartTab.alone`), with its own
  draft; the device tab no longer has a state of its own for it.
- **The undo scope of a part tab** is the part and the files of the `!include` chain of its instance
  (`PartFocus.undo_scope`): undo there doesn't step through edits of other files of the device, which the device tab undoes.
  The scope follows the instance when another one is chosen.
- **Save writes every changed file of the `ConfigDraft`** (Part 4), from any tab: one question lists the files the active
  tab doesn't show (for a part tab: other than its undo scope) and the shared files, then all are written and every draft
  that shows them is marked saved. A part on its own is the exception: its draft is its own (placeholder vars, maybe a copy
  of a part that the shared draft has too, which would be written twice), so only its tab saves it, also when the tab is
  closed in the background. Revert still drops the draft of the active tab.
- **One `PlateLink` per device, not per editor** (supersedes "`PlateLink` stays in the editor of the device tab" of phase 5).
  `PlateConnections` keeps it with the connection, and every tab of the device shows its actions (Live preview, Clear page,
  Restore plate). Live preview sends the page of the tab of the device that was active last (`PlateLink.set_view`); closing
  that tab hands it to another tab of the device. Busy state and error banner are those of that tab's editor. Alternative: a
  Live preview per tab, which would send two pages to one plate.
- **The focus is found again by its description** after a reload or a revert (`PlateSession.load` goes on with the focuses of
  the draft), or on the first instance if that one is gone; a part tab closes, with a message in the status bar, when the
  device doesn't include the part anymore.
- **Only the instance is shown**: the other objects of the page are hidden (`EditableWidget.set_shown`, which `set_dimmed`
  doesn't undo), and the view is zoomed to fit the instance (up to 4x, with a margin), centered between the bars, without
  scrollbars. "Show the page" goes back to the dimmed page and the zoom of the page.
- **A small window stays usable**: a part tab hides the device controls over the preview (they belong to the device tab), the
  widget picker shrinks to its icons when the editor is narrow (in device tabs too), and the buttons of the part bar lose their
  titles before the bar would wrap. The instance list is at least 4 characters wide. The window's minimum size is 960x600.
  The preview is never narrower than its widest floating bar, also after a bar got wider (an event filter follows their
  layouts): before, a stale minimum and a wider font (a fallback font on CI) pushed the editor under the Properties dock.
  The test of the small window runs with the default font and one 1.5 times as large.

### Phase 7: the state file and restoring tabs

- **`tabs` and `active_tab` next to the keys of before.** Each tab has its kind (`device`, `part`), device, part (relative to
  the config directory), instance (its description, as `part_mode`), `alone`, page, connection state, Live preview and
  `unsaved`. `device`, `problems` and `connection` stay those of the active tab, so the readers of schema 1 keep working; the
  schema version is not bumped, since nothing was removed.
- **One image per open device, at `preview/<device>/current.png`**, not `preview/<device>.png`: the `preview` command writes
  `preview/<device>/page_<n>.png` from the files on disk, and the two stay apart in one folder per device (the command only
  removes its `page_*.png`). A device has one image also with several tabs: the page of its tab that was active last (the one
  Live preview sends, `PlateLink.view`), referenced from each of its tabs. The image of a background device is rendered again
  only after its editor reported a change (`GuiStatePublisher.request(device)`), the active one with every write as before.
  The image goes with the last tab of the device, all of them when the GUI quits, and those of an earlier run on start.
- **`preview.png` stays**, as the image of the active tab (the same bytes as its device's `current.png`), for readers and
  instructions written for it (the LLM section of the README).
- **Restoring tabs.** `UiSession.open_tabs` keeps the device, part and instance description of each tab, `active_tab` the
  index; `selected_device` stays the active tab's device (a session without `open_tabs` of an older version opens it). The
  device tabs open in their order; a part tab opens once its device is loaded, after the other tabs of its device, in the
  instance with the same description, or the first one (or on its own, if no page includes the part anymore). A part tab
  whose device tab was closed brings that one back too: a part tab needs the device loaded, which is done for a device tab.
  Tabs of devices or part files that are gone are skipped (logged). The page and the zoom of a tab are not restored, and
  Live preview is never turned on again. While part tabs wait for their device, the tabs are not remembered, so quitting
  before the devices are loaded keeps the tabs of the last session.
