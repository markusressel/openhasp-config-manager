# Fonts of the plate

The preview draws text in the fonts of the plate, so they don't have to be installed:

- `RobotoCondensed-Regular.ttf`: Roboto Condensed, the font of openHASP (its built-in fonts and the TrueType font for the other
  sizes). Licensed under the SIL Open Font License, see `OFL.txt`.
- `unscii-8-thin.ttf`: unscii by Viznut (http://viznut.fi/unscii/), the pixel font of `"text_font": 8`. Public domain.

Their families are renamed to `openHASP Roboto Condensed` and `openHASP unscii` (with fontTools), so that Qt doesn't mix them up
with installed fonts, or with font files of a device.
