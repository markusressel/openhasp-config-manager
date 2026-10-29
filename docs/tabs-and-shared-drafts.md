# Design: tabs in the preview, and one draft for all devices

Status: proposal, not implemented.

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

## Open questions

- Is Save writing all changed files right, or should it be the files of the active tab (with Save All next to it)?
- How many devices with Live preview at once are practical (one MQTT client per device, rendering per edit)?
- Should a part tab without "Show the page" still render the page for its object references (`b4.w` of a card)? Proposal: yes,
  it renders as on the page and only hides the other objects, so the values are those of the page.
