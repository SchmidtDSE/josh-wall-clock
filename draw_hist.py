"""Render a comparison chart of Josh vs. Mesa wall-clock benchmark trials.

The figure has two rows (top = threaded, bottom = non-threaded). Each row shows,
on the left, overlaid semi-transparent histograms of the individual trials and,
on the right, average-time bars for Josh, Mesa, and the time Josh saved (labeled
with the percent reduction).

Only the Python standard library and Sketchingpy are used.
"""

import csv
import math
import os

import sketchingpy

# --- Data -------------------------------------------------------------------

RESULTS_CSV = os.path.join(os.path.dirname(__file__), "results", "all_results.csv")
OUTPUT_PNG = os.path.join(os.path.dirname(__file__), "draw_hist.png")

# --- Appearance -------------------------------------------------------------

WIDTH = 1180
HEIGHT = 732

# Bars use the brand colors; labels use darker shades for WCAG contrast on white.
COLOR_JOSH = "#157A5C"
COLOR_MESA = "#6865AE"
COLOR_DIFF = "#606060"
FILL_JOSH = "#1b9e77"  # solid: the distributions don't overlap in practice
FILL_MESA = "#7570b3"
FILL_DIFF = "#606060"
COLOR_BG = "#FFFFFF"
COLOR_INK = "#1a1a1a"
COLOR_MUTED = "#6b6b6b"
COLOR_BASELINE = "#cccccc"

BIN_WIDTH = 5  # minutes

# Histograms (left) share one minute axis; average bars (right) share another.
LEFT_X0, LEFT_X1 = 84, 688
RIGHT_X0, RIGHT_X1 = 792, 1140
TOP_Y0, TOP_Y1 = 124, 356
BOT_Y0, BOT_Y1 = 428, 660
ROW_LABEL_X = 29

# All text uses Lato Regular.
_FONT_CANDIDATES = [
    os.path.expanduser("~/Lato2OFL/Lato-Regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _first_existing(paths, fallback):
    for path in paths:
        if os.path.exists(path):
            return path
    return fallback


FONT = _first_existing(_FONT_CANDIDATES, _FONT_CANDIDATES[0])
FONT_BOLD = FONT


def load_trials(path):
    """Return {(implementation, threaded): [wall minutes, ...]} from the CSV."""
    groups = {}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["implementation"], row["threaded"])
            minutes = float(row["wallSeconds"]) / 60.0
            groups.setdefault(key, []).append(minutes)
    return groups


def histogram(values, edges):
    """Return per-bin experiment counts (each bin is [edge, edge+width))."""
    counts = [0] * len(edges)
    for value in values:
        index = int((value - edges[0]) // BIN_WIDTH)
        index = max(0, min(index, len(edges) - 1))
        counts[index] += 1
    return counts


# --- Layout / shared scales -------------------------------------------------


class Layout:
    """Pixel geometry and the minute/percent scales shared across presenters."""

    def __init__(self, x_lo, x_hi, y_max, right_max, edges):
        self.x_lo = x_lo
        self.x_hi = x_hi
        self.y_max = y_max
        self.right_max = right_max
        self.edges = edges

    def left_x(self, minutes):
        span = self.x_hi - self.x_lo
        return LEFT_X0 + (minutes - self.x_lo) / span * (LEFT_X1 - LEFT_X0)

    def right_x(self, minutes):
        return RIGHT_X0 + (minutes / self.right_max) * (RIGHT_X1 - RIGHT_X0)

    def hist_y(self, pct, baseline, plot_h):
        return baseline - (pct / self.y_max) * plot_h


# --- Presenters -------------------------------------------------------------


class HistogramPresenter:
    """Left side of one row: overlaid Josh/Mesa histograms with a negative-space grid."""

    def __init__(self, sketch, layout, josh, mesa, band_y0, band_y1):
        self._sketch = sketch
        self._layout = layout
        self._josh = josh
        self._mesa = mesa
        self._baseline = band_y1
        self._plot_h = (band_y1 - band_y0) - 22

    def draw(self):
        self._draw_baseline()
        self._draw_series(self._josh, FILL_JOSH)
        self._draw_series(self._mesa, FILL_MESA)
        self._draw_negative_space_grid()

    def _draw_baseline(self):
        sketch = self._sketch
        sketch.clear_fill()
        sketch.set_stroke(COLOR_BASELINE)
        sketch.set_stroke_weight(1)
        sketch.draw_line(LEFT_X0, self._baseline, LEFT_X1, self._baseline)

    def _draw_series(self, values, fill):
        sketch = self._sketch
        layout = self._layout
        sketch.clear_stroke()
        sketch.set_fill(fill)
        sketch.set_rect_mode("corners")
        for edge, pct in zip(layout.edges, histogram(values, layout.edges)):
            if pct <= 0:
                continue
            x1 = layout.left_x(edge)
            x2 = layout.left_x(edge + BIN_WIDTH) - 2  # 2px gap between bars
            top = layout.hist_y(pct, self._baseline, self._plot_h)
            sketch.draw_rect(x1, top, x2, self._baseline)

    MAJOR_STEP = 2

    def _draw_negative_space_grid(self):
        """White lines carved through the bars at each tick and the half-ticks
        between them; percent labels at the major ticks only."""
        sketch = self._sketch
        layout = self._layout
        # Gridlines at every half-tick (e.g. 10%, 20%, 30%, ...); skip the baseline.
        sketch.clear_fill()
        sketch.set_stroke(COLOR_BG)
        sketch.set_stroke_weight(2)
        pct = self.MAJOR_STEP / 2.0
        while pct <= layout.y_max + 0.001:
            y = layout.hist_y(pct, self._baseline, self._plot_h)
            sketch.draw_line(LEFT_X0, y, LEFT_X1, y)
            pct += self.MAJOR_STEP / 2.0
        # Labels at the major ticks only.
        sketch.clear_stroke()
        sketch.set_fill(COLOR_MUTED)
        sketch.set_text_font(FONT, 17)
        sketch.set_text_align("right", "center")
        pct = 0
        while pct <= layout.y_max + 0.001:
            y = layout.hist_y(pct, self._baseline, self._plot_h)
            sketch.draw_text(LEFT_X0 - 8, y, "%d" % pct)
            pct += self.MAJOR_STEP


class AveragePresenter:
    """Right side of one row: Josh, Mesa, and time-saved bars (length in minutes)."""

    BAR_H = 15

    def __init__(self, sketch, layout, josh_mean, mesa_mean, band_y0, band_y1):
        self._sketch = sketch
        self._layout = layout
        self._josh_mean = josh_mean
        self._mesa_mean = mesa_mean
        self._band_y0 = band_y0
        self._band_y1 = band_y1

    def draw(self):
        saved = self._mesa_mean - self._josh_mean
        pct_faster = 100.0 * saved / self._mesa_mean
        self._draw_bar(0, "Josh (%.0f minutes)" % self._josh_mean, self._josh_mean,
                       COLOR_JOSH, FILL_JOSH)
        self._draw_bar(1, "Mesa (%.0f minutes)" % self._mesa_mean, self._mesa_mean,
                       COLOR_MESA, FILL_MESA)
        self._draw_bar(2, "%.0f%% faster (%.0f minutes)" % (pct_faster, saved), saved,
                       COLOR_DIFF, FILL_DIFF)

    def _draw_bar(self, slot, label, minutes, ink, fill):
        sketch = self._sketch
        layout = self._layout
        slot_h = (self._band_y1 - self._band_y0) / 3.0
        slot_top = self._band_y0 + slot * slot_h

        sketch.clear_stroke()
        sketch.set_fill(ink)
        sketch.set_text_font(FONT_BOLD, 18)
        sketch.set_text_align("left", "bottom")
        sketch.draw_text(RIGHT_X0, slot_top + 18, label)

        bar_top = slot_top + 24
        sketch.set_fill(fill)
        sketch.set_rect_mode("corners")
        sketch.draw_rect(RIGHT_X0, bar_top, layout.right_x(minutes), bar_top + self.BAR_H)


class TrialPresenter:
    """One row (a single threaded/non-threaded condition): histogram + averages."""

    def __init__(self, sketch, layout, josh, mesa, band_y0, band_y1):
        self._histogram = HistogramPresenter(sketch, layout, josh, mesa, band_y0, band_y1)
        self._average = AveragePresenter(
            sketch, layout, sum(josh) / len(josh), sum(mesa) / len(mesa), band_y0, band_y1
        )

    def draw(self):
        self._histogram.draw()
        self._average.draw()


class MainPresenter:
    """Full figure: chrome (title, subtitles, rotated labels, axes) plus both rows."""

    TITLE = "Josh runs faster in both the threaded and non-threaded trials."

    def __init__(self, sketch, layout, groups):
        self._sketch = sketch
        self._layout = layout
        self._top = TrialPresenter(
            sketch, layout,
            groups[("josh", "true")], groups[("mesa", "true")], TOP_Y0, TOP_Y1,
        )
        self._bottom = TrialPresenter(
            sketch, layout,
            groups[("josh", "false")], groups[("mesa", "false")], BOT_Y0, BOT_Y1,
        )

    def draw(self):
        self._sketch.clear(COLOR_BG)
        self._draw_title()
        self._draw_subtitles()
        self._draw_row_labels()
        self._top.draw()
        self._bottom.draw()
        self._draw_minute_axes()

    def _draw_title(self):
        sketch = self._sketch
        sketch.clear_stroke()
        sketch.set_fill(COLOR_INK)
        sketch.set_text_font(FONT_BOLD, 29)
        sketch.set_text_align("left", "top")
        sketch.draw_text(28, 26, self.TITLE)

    def _draw_subtitles(self):
        sketch = self._sketch
        sketch.clear_stroke()
        sketch.set_fill(COLOR_MUTED)
        sketch.set_text_font(FONT, 19)
        sketch.set_text_align("center", "baseline")
        sketch.draw_text((LEFT_X0 + LEFT_X1) / 2, 96, "distribution of individual experiments")
        sketch.draw_text((RIGHT_X0 + RIGHT_X1) / 2, 96, "average of experiments")

    def _draw_row_labels(self):
        self._rotated_label(self.TOP_CENTER(), "# threaded experiments")
        self._rotated_label(self.BOT_CENTER(), "# unthreaded experiments")

    @staticmethod
    def TOP_CENTER():
        return (TOP_Y0 + TOP_Y1) / 2

    @staticmethod
    def BOT_CENTER():
        return (BOT_Y0 + BOT_Y1) / 2

    def _rotated_label(self, center_y, text):
        sketch = self._sketch
        sketch.clear_stroke()
        sketch.set_fill(COLOR_INK)
        sketch.set_text_font(FONT_BOLD, 20)
        sketch.set_text_align("center", "center")
        sketch.set_angle_mode("degrees")
        sketch.push_transform()
        sketch.translate(ROW_LABEL_X, center_y)
        sketch.rotate(-90)
        sketch.draw_text(0, 0, text)
        sketch.pop_transform()

    def _draw_minute_axes(self):
        """Tick the two shared horizontal (minute) axes beneath the bottom row."""
        layout = self._layout
        base_y = BOT_Y1
        # Left axis: histogram minutes.
        left_ticks = [t for t in range(100, int(layout.x_hi) + 1, 50) if t >= layout.x_lo]
        self._tick_row([(layout.left_x(t), t) for t in left_ticks], base_y,
                       (LEFT_X0 + LEFT_X1) / 2, "wall time (minutes)")
        # Right axis: average minutes.
        right_ticks = list(range(0, int(layout.right_max) + 1, 100))
        self._tick_row([(layout.right_x(t), t) for t in right_ticks], base_y,
                       (RIGHT_X0 + RIGHT_X1) / 2, "wall time (minutes)")

    def _tick_row(self, positions, base_y, title_x, title):
        sketch = self._sketch
        for x, value in positions:
            sketch.clear_fill()
            sketch.set_stroke(COLOR_MUTED)
            sketch.set_stroke_weight(1)
            sketch.draw_line(x, base_y + 4, x, base_y + 9)
            sketch.clear_stroke()
            sketch.set_fill(COLOR_MUTED)
            sketch.set_text_font(FONT, 17)
            sketch.set_text_align("center", "top")
            sketch.draw_text(x, base_y + 12, str(value))
        sketch.clear_stroke()
        sketch.set_fill(COLOR_MUTED)
        sketch.set_text_font(FONT, 19)
        sketch.set_text_align("center", "top")
        sketch.draw_text(title_x, base_y + 30, title)


def build_layout(groups):
    everything = [v for values in groups.values() for v in values]
    x_lo = math.floor(min(everything) / 10) * 10
    x_hi = math.ceil(max(everything) / 10) * 10
    edges = [x_lo + i * BIN_WIDTH for i in range(int((x_hi - x_lo) / BIN_WIDTH) + 1)]

    peak = max(
        max(histogram(values, edges)) for values in groups.values()
    )
    y_max = int(math.ceil(peak / 2.0) * 2)

    means = [sum(values) / len(values) for values in groups.values()]
    right_max = math.ceil(max(means) / 100.0) * 100

    return Layout(x_lo, x_hi, y_max, right_max, edges)


def main():
    groups = load_trials(RESULTS_CSV)
    layout = build_layout(groups)
    sketch = sketchingpy.Sketch2DStatic(WIDTH, HEIGHT)
    MainPresenter(sketch, layout, groups).draw()
    sketch.save_image(OUTPUT_PNG)
    print("wrote", OUTPUT_PNG)


if __name__ == "__main__":
    main()
