"""How the parts of the objects look on the plate without style properties (measured on a plate, it is the default theme of openHASP)."""

_BORDER = {"bg_opa": 255, "border_width": 1, "border_color": "#A0A5B1", "border_opa": 128, "radius": 4}

# the track of a switch, slider or bar: a dark gradient
TRACK_DEFAULTS = {"bg_color": "#52596A", "bg_grad_color": "#202839", "bg_grad_dir": 1, **_BORDER}
# what is filled or switched on: the blue of the buttons
INDICATOR_DEFAULTS = {"bg_color": "#4ACAFF", "bg_grad_color": "#0081B4", "bg_grad_dir": 1, **_BORDER}
# the knob of a switch or slider: white at the top, dark at the bottom
KNOB_DEFAULTS = {"bg_color": "#F6F8FC", "bg_grad_color": "#202839", "bg_grad_dir": 1, **_BORDER}

# the indicator of a slider or bar is this far from the edges of its track
TRACK_PADDING = 6
# the knob of a slider or switch reaches this far over its track on every side (a slider's, 4, makes it bigger than the switch's 1)
SWITCH_KNOB_PADDING = 1
SLIDER_KNOB_PADDING = 4
