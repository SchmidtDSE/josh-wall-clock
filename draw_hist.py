"""Render a comparison chart of Josh vs. Mesa wall-time benchmark trials.

The figure has two rows (top = threaded, bottom = non-threaded). Each row shows,
on the left, one marker per trial stacked up from a wall-time baseline, and on
the right, average-time bars for the ai and expert models.

Each left-panel marker encodes two dimensions:
  *   shape: square = ai model, circle = expert (manual) model
  *   color: green = Josh, purple = Mesa
A circle is drawn on top of a square whenever both land in the same time bucket,
so both remain visible. A count axis on the far left shows how many trials are
stacked in each bucket.

The right panel shows two columns -- ai and expert -- each with a Josh and a
Mesa bar on a shared 0-300 minute axis. Each bar's label is left-aligned with
the mean time in parentheses, and the bar sits directly below.

Only the Python standard library and Sketchingpy are used.
"""

import csv
import math
import os
from collections import defaultdict

import sketchingpy

# --- Data -------------------------------------------------------------------

RESULTS_CSV = os.path.join(os.path.dirname(__file__), "results", "all_results.csv")
OUTPUT_PNG = os.path.join(os.path.dirname(__file__), "draw_hist.png")

# --- Appearance -------------------------------------------------------------

WIDTH = 1320
HEIGHT = 720

COLOR_JOSH = "#105B45"
COLOR_MESA = "#4B497D"
COLOR_DIFF = "#484848"
FILL_JOSH = "#1b9e77"
FILL_MESA = "#7570b3"
FILL_DIFF = "#606060"
COLOR_BG = "#FFFFFF"
COLOR_INK = "#1a1a1a"
COLOR_MUTED = "#6b6b6b"
COLOR_BASELINE = "#cccccc"

BIN_WIDTH = 10  # minutes (larger buckets so markers touch horizontally)

# Left panel (distribution) geometry.
LEFT_X0, LEFT_X1 = 84, 650
RIGHT_X0, RIGHT_X1 = 700, 1240
COLUMN_GAP = 40
TOP_Y0, TOP_Y1 = 160, 316
BOT_Y0, BOT_Y1 = 436, 592
ROW_LABEL_X = 26
COUNT_AXIS_X = 56
LEGEND_Y = 675

MARKER_SIZE = 9        # diameter of a circle / side of a square
MARKER_PITCH = 11      # vertical step between stacked markers
MARKER_BASE_OFFSET = 8 # how far above the baseline the first marker sits

# Right-panel bar geometry. Both columns share a 0-300 minute scale.
RIGHT_MAX = 300.0
GROUP_W = (RIGHT_X1 - RIGHT_X0 - COLUMN_GAP) / 2.0
BAR_H = 8
BAR_SLOT = 26
GROUP_LABEL_Y = 44

# All text uses Lato Regular.
_FONT_CANDIDATES = [
    os.path.expanduser("~/Lato2OFL/Lato-Regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _first_existing(paths, fallback):
  """Return the first path that exists, or a fallback.

  @param paths: Candidate filesystem paths, in preference order.
  @type paths: list of str
  @param fallback: Value returned when none of the paths exist.
  @type fallback: str
  @return: The first existing path, else C{fallback}.
  @rtype: str
  """
  for path in paths:
    if os.path.exists(path):
      return path
  return fallback


FONT = _first_existing(_FONT_CANDIDATES, _FONT_CANDIDATES[0])
FONT_BOLD = FONT


def load_trials(path):
  """Group trial wall times by (implementation, model, threaded).

  :param path: Path to the results CSV.
  :return: Map of (implementation, model, threaded) to lists of wall minutes.
  """
  groups = {}
  with open(path, newline="") as handle:
    for row in csv.DictReader(handle):
      key = (row["implementation"], row["model"], row["threaded"])
      minutes = float(row["wallSeconds"]) / 60.0
      groups.setdefault(key, []).append(minutes)
  return groups


def _mean(values):
  """Return the mean of a sequence, or 0.0 when empty.

  :param values: The values to average.
  :return: The arithmetic mean, or 0.0.
  """
  return sum(values) / len(values) if values else 0.0


def _bin_for(minutes, edges):
  """Return the bin index a minute falls into, clamped to C{edges}.

  :param minutes: A wall time in minutes.
  :param edges: The left edge of each bin.
  :return: The 0-based bin index.
  """
  index = int((minutes - edges[0]) // BIN_WIDTH)
  return max(0, min(index, len(edges) - 1))


class Layout:
  """Pixel geometry and the shared minute scales across rows.

  @ivar x_lo: Low end of the left minute axis.
  @ivar x_hi: High end of the left minute axis.
  @ivar edges: Left edge of each minute bin for the left panel.
  @ivar right_max: Fixed right-bar minute axis maximum (0-300).
  """

  def __init__(self, x_lo, x_hi, edges):
    self.x_lo = x_lo
    self.x_hi = x_hi
    self.edges = edges
    self.right_max = RIGHT_MAX

  def left_x(self, minutes):
    """Map a minute value to an x pixel on the left axis."""
    span = self.x_hi - self.x_lo
    return LEFT_X0 + (minutes - self.x_lo) / span * (LEFT_X1 - LEFT_X0)


class DistributionPanel:
  """Left side of one row: one marker per trial stacked up by wall time."""

  def __init__(self, sketch, layout, series, band_y0, band_y1):
    self._sketch = sketch
    self._layout = layout
    self._baseline = band_y1
    self._top_y = band_y0
    self._series = series
    self._max_count = 0

  def _y_for_count(self, count):
    """Return the y pixel for a stacked count (0 = baseline).

    :param count: The number of markers stacked (0-based height).
    :return: The y pixel of that stack position.
    """
    if count <= 0:
      return self._baseline
    return self._baseline - MARKER_BASE_OFFSET - (count - 1) * MARKER_PITCH

  def draw(self):
    """Draw the baseline, stacked markers, and the left count axis."""
    sketch = self._sketch
    layout = self._layout

    sketch.clear_fill()
    sketch.set_stroke(COLOR_BASELINE)
    sketch.set_stroke_weight(1)
    sketch.draw_line(LEFT_X0, self._baseline, LEFT_X1, self._baseline)

    # Order determines stacking: squares (ai) first, circles (expert) on top.
    order = [
        ("josh", "ai", "square", FILL_JOSH),
        ("mesa", "ai", "square", FILL_MESA),
        ("josh", "manual", "circle", FILL_JOSH),
        ("mesa", "manual", "circle", FILL_MESA),
    ]
    bins = defaultdict(list)
    for impl, model, shape, fill in order:
      for minutes in self._series.get((impl, model), ()):
        index = _bin_for(minutes, self._layout.edges)
        bins[index].append((shape, fill))
    self._max_count = max((len(v) for v in bins.values()), default=0)

    sketch.clear_stroke()
    sketch.set_rect_mode("center")
    sketch.set_ellipse_mode("center")
    for index in sorted(bins):
      x = self._layout.left_x(self._layout.edges[index])
      for i, (shape, fill) in enumerate(bins[index]):
        cy = self._y_for_count(i + 1)
        sketch.set_fill(fill)
        if shape == "circle":
          sketch.draw_ellipse(x, cy, MARKER_SIZE, MARKER_SIZE)
        else:
          sketch.draw_rect(x, cy, MARKER_SIZE, MARKER_SIZE)

    self._draw_count_axis()

  def _draw_count_axis(self):
    """Draw the stacked-count ticks on the far left of the row (0-15, step 3)."""
    sketch = self._sketch
    sketch.clear_stroke()
    sketch.set_fill(COLOR_MUTED)
    sketch.set_text_font(FONT, 15)
    sketch.set_text_align("right", "center")
    for count in range(0, 16, 3):
      sketch.draw_text(COUNT_AXIS_X + 5, self._y_for_count(count), str(count))


class AveragePanel:
  """Draws the ai and expert two-column bar groups on the right of one row.

  Both columns share a fixed 0-300 minute axis. Each column shows a Josh and a
  Mesa bar, with a left-aligned label giving the runtime name and its mean wall
  time in parentheses, and the bar drawn directly below the label.
  """

  def __init__(self, sketch, layout, means, band_y0, band_y1):
    self._sketch = sketch
    self._layout = layout
    self._top_y = band_y0
    self._bottom_y = band_y1
    self._means = means

  @staticmethod
  def _column_x(model):
    """Return the left x pixel of a column given its model key.

    :param model: C{"ai"} or C{"manual"}.
    :return: The column's left x pixel.
    """
    index = 0 if model == "ai" else 1
    return RIGHT_X0 + index * (GROUP_W + COLUMN_GAP)

  def _right_x(self, model, minutes):
    """Map a minute to an x pixel within a column on the 0-300 axis."""
    return self._column_x(model) + (minutes / RIGHT_MAX) * GROUP_W

  def draw(self):
    """Draw the ai and expert columns, left to right."""
    for model in ["ai", "manual"]:
      self._draw_column(model)

  def _draw_column(self, model):
    """Draw one column: header, two labeled bars, and the shared 0-300 axis."""
    sketch = self._sketch
    gx0 = self._column_x(model)
    gx1 = gx0 + GROUP_W
    gcx = (gx0 + gx1) / 2
    label = "AI" if model == "ai" else "Expert"

    sketch.clear_stroke()
    sketch.set_fill(COLOR_INK)
    sketch.set_text_font(FONT_BOLD, 18)
    sketch.set_text_align("center", "bottom")
    sketch.draw_text(gcx, self._top_y + 8, label)

    josh_mean, mesa_mean = self._means.get(model, (0.0, 0.0))
    bars = [
        ("Josh", josh_mean, COLOR_JOSH, FILL_JOSH),
        ("Mesa", mesa_mean, COLOR_MESA, FILL_MESA),
    ]
    y = self._top_y + GROUP_LABEL_Y + 5
    for i, (name, minutes, ink, fill) in enumerate(bars):
      sketch.clear_stroke()
      sketch.set_fill(ink)
      sketch.set_text_font(FONT_BOLD, 15)
      sketch.set_text_align("left", "bottom")
      sketch.draw_text(gx0, y, "%s (%d min)" % (name, round(minutes)))
      sketch.set_fill(fill)
      sketch.set_rect_mode("corners")
      sketch.draw_rect(gx0, y + 2, self._right_x(model, minutes), y + 2 + BAR_H)
      # 10px extra padding between the Josh and Mesa bars
      gap = BAR_H + BAR_SLOT + (10 if i == 0 else 0)
      y += gap

    self._draw_column_axis(gx0, gx1, gcx)

  def _draw_column_axis(self, gx0, gx1, gcx):
    """Draw the 0-300 tick row for one column (both columns share this)."""
    sketch = self._sketch
    axis_y = self._bottom_y
    for tick in range(0, int(RIGHT_MAX) + 1, 100):
      x = gx0 + (tick / RIGHT_MAX) * (gx1 - gx0)
      sketch.clear_fill()
      sketch.set_stroke(COLOR_MUTED)
      sketch.set_stroke_weight(1)
      sketch.draw_line(x, axis_y + 4, x, axis_y + 9)
      sketch.clear_stroke()
      sketch.set_fill(COLOR_MUTED)
      sketch.set_text_font(FONT, 14)
      sketch.set_text_align("center", "top")
      sketch.draw_text(x, axis_y + 12, str(tick))
    sketch.clear_stroke()
    sketch.set_fill(COLOR_MUTED)
    sketch.set_text_font(FONT, 15)
    sketch.set_text_align("center", "top")
    sketch.draw_text(gcx, axis_y + 28, "minutes")


def draw_legend(sketch):
  """Draw the square/circle legend aligned with the two right columns."""
  for index, (label, shape) in enumerate([("AI", "square"), ("Expert", "circle")]):
    gx0 = RIGHT_X0 + index * (GROUP_W + COLUMN_GAP)
    gcx = gx0 + GROUP_W / 2
    marker_x = gcx - MARKER_SIZE / 2 - 4
    sketch.clear_stroke()
    sketch.set_fill(COLOR_INK)
    if shape == "square":
      sketch.set_rect_mode("center")
      sketch.draw_rect(marker_x, LEGEND_Y, MARKER_SIZE, MARKER_SIZE)
    else:
      sketch.set_ellipse_mode("center")
      sketch.draw_ellipse(marker_x, LEGEND_Y, MARKER_SIZE, MARKER_SIZE)
    sketch.set_fill(COLOR_INK)
    sketch.set_text_font(FONT_BOLD, 16)
    sketch.set_text_align("left", "center")
    sketch.draw_text(marker_x + MARKER_SIZE / 2 + 6, LEGEND_Y, label)


class RowPresenter:
  """One row (a threaded/non-threaded condition): distribution + average bars."""

  def __init__(self, sketch, layout, series, band_y0, band_y1):
    self._distribution = DistributionPanel(sketch, layout, series, band_y0, band_y1)
    means = {
        "ai": (_mean(series.get(("josh", "ai"), [])),
               _mean(series.get(("mesa", "ai"), []))),
        "manual": (_mean(series.get(("josh", "manual"), [])),
                   _mean(series.get(("mesa", "manual"), []))),
    }
    self._average = AveragePanel(sketch, layout, means, band_y0, band_y1)

  def draw(self):
    self._distribution.draw()
    self._average.draw()


class MainPresenter:
  """Full figure: chrome plus the threaded and unthreaded rows."""

  TITLE = "Josh vs. Mesa wall time: expert models are fastest; threaded runs beat serial."

  def __init__(self, sketch, layout, groups):
    self._sketch = sketch
    self._layout = layout
    self._top = RowPresenter(sketch, layout, self._series(groups, "true"), TOP_Y0, TOP_Y1)
    self._bottom = RowPresenter(sketch, layout, self._series(groups, "false"), BOT_Y0, BOT_Y1)

  @staticmethod
  def _series(groups, threaded):
    """Rebuild a (implementation, model) -> minutes map for one row."""
    out = {}
    for (impl, model, thr), values in groups.items():
      if thr == threaded:
        out.setdefault((impl, model), []).extend(values)
    return out

  def draw(self):
    sketch = self._sketch
    sketch.clear(COLOR_BG)
    self._draw_title()
    self._draw_subtitles()
    self._draw_row_labels()
    self._top.draw()
    self._bottom.draw()
    self._draw_wall_time_axis()
    draw_legend(sketch)

  def _draw_title(self):
    sketch = self._sketch
    sketch.clear_stroke()
    sketch.set_fill(COLOR_INK)
    sketch.set_text_font(FONT_BOLD, 25)
    sketch.set_text_align("left", "top")
    sketch.draw_text(28, 22, self.TITLE)

  def _draw_subtitles(self):
    sketch = self._sketch
    sketch.clear_stroke()
    sketch.set_fill(COLOR_MUTED)
    sketch.set_text_font(FONT, 18)
    sketch.set_text_align("center", "baseline")
    sketch.draw_text((LEFT_X0 + LEFT_X1) / 2, 108, "each marker = one experiment")
    sketch.draw_text((RIGHT_X0 + RIGHT_X1) / 2, 108, "average of experiments")

  def _draw_row_labels(self):
    self._rotated_label((TOP_Y0 + TOP_Y1) / 2, "# threaded experiments")
    self._rotated_label((BOT_Y0 + BOT_Y1) / 2, "# unthreaded experiments")

  def _rotated_label(self, center_y, text):
    sketch = self._sketch
    sketch.clear_stroke()
    sketch.set_fill(COLOR_INK)
    sketch.set_text_font(FONT_BOLD, 18)
    sketch.set_text_align("center", "center")
    sketch.set_angle_mode("degrees")
    sketch.push_transform()
    sketch.translate(ROW_LABEL_X, center_y)
    sketch.rotate(-90)
    sketch.draw_text(0, 0, text)
    sketch.pop_transform()

  def _draw_wall_time_axis(self):
    layout = self._layout
    base_y = BOT_Y1
    left_ticks = [t for t in range(100, int(layout.x_hi) + 1, 50) if t >= layout.x_lo]
    self._tick_row([(layout.left_x(t), t) for t in left_ticks], base_y,
                   (LEFT_X0 + LEFT_X1) / 2, "wall time (minutes)")

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
    sketch.set_text_font(FONT, 18)
    sketch.set_text_align("center", "top")
    sketch.draw_text(title_x, base_y + 30, title)


def build_layout(groups):
  """Derive the shared scales from the trial data."""
  everything = [v for values in groups.values() for v in values]
  x_lo = math.floor(min(everything) / 10) * 10
  x_hi = math.ceil(max(everything) / 10) * 10
  edges = [x_lo + i * BIN_WIDTH for i in range(int((x_hi - x_lo) / BIN_WIDTH) + 1)]
  return Layout(x_lo, x_hi, edges)


def main():
  groups = load_trials(RESULTS_CSV)
  layout = build_layout(groups)
  sketch = sketchingpy.Sketch2DStatic(WIDTH, HEIGHT)
  MainPresenter(sketch, layout, groups).draw()
  sketch.save_image(OUTPUT_PNG)
  print("wrote", OUTPUT_PNG)


if __name__ == "__main__":
  main()