# DDRAM experiment figure style

All experiment figures should load `figure_palette.toml` and use its semantic
color assignments. This keeps configurations recognizable across separate
plots while retaining the contrasting Cyberpunk palette selected for the
project.

The current conventions are:

- no refresh or the ordinary two-view baseline: green;
- Oracle refresh: blue, with periwinkle/cobalt for one/two views;
- NACK refresh: orange, with apricot/orange for one/two views;
- auto-precharge: orange;
- queue-aware scheduling: violet;
- zero reference lines: rose;
- box-plot medians: fuchsia.
- aggregate columns: light-gray background with a dashed charcoal separator.

Black and gray remain acceptable for text, axes, outlines, and grid lines; they
should not be used to distinguish experimental configurations. New figure
scripts should prefer semantic entries over selecting an arbitrary color.
