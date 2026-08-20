import csv
import itertools
import math
import multiprocessing
import random
import statistics
import sys

import haversine
import mesa
import netCDF4
import numpy
import pathos.pools

USAGE_STR = 'USAGE: python3 forevertree_manual.py [replicates] [threaded] [output]'
NUM_ARGS = 3

MIN_TEMPERATURE = 270
MAX_TEMPERATURE = 330
TEMPERATURE_RANGE = MAX_TEMPERATURE - MIN_TEMPERATURE
MID_TEMPERATURE = (MAX_TEMPERATURE + MIN_TEMPERATURE) / 2

MIN_PRECIPITATION = 300
MAX_PRECIPITATION = 500
PRECIPITATION_RANGE = MAX_PRECIPITATION - MIN_PRECIPITATION
MID_PRECIPITATION = (MIN_PRECIPITATION + MAX_PRECIPITATION) / 2

MIN_LAT = 35.80
MAX_LAT = 36.73
MIN_LON = -119.52
MAX_LON = -117.98
CELL_SIZE_KM = 1
NUM_TIMESTEPS = 101

START_YEAR = 2024

EXPECTED_FIELDS = [
  'year',
  'nTrees',
  'meanAge',
  'meanHeight',
  'temperature',
  'precipitation'
]


class ForeverTreeModel(mesa.Model):

  def __init__(self, grid_size, temperatures, precipitations, num_per_space=10, rng=None):
    super().__init__(rng=rng)
    self._grid_size = grid_size
    self._temperatures = temperatures
    self._precipitations = precipitations
    self._step = 0

    self._grid = mesa.discrete_space.OrthogonalMooreGrid(
      (grid_size.get_width_cells(), grid_size.get_height_cells()),
      torus=True,
      random=self.random
    )

    unique_spaces = itertools.product(
      range(0, grid_size.get_width_cells()),
      range(0, grid_size.get_height_cells())
    )
    repeated_agent_spaces = itertools.chain(*map(
      lambda x: [x] * 10,
      unique_spaces
    ))
    spaces = list(repeated_agent_spaces)
    num_agents = len(spaces)

    ForeverTreeAgent.create_agents(
      self,
      num_agents,
      spaces
    )

  def step(self):
    self.agents.do('grow')
    self._step += 1

  def get_temperature(self, cell):
    return self._temperatures.get_value(cell[0], cell[1], self._step)

  def get_precipitation(self, cell):
    raw_value = self._precipitations.get_value(cell[0], cell[1], self._step)
    return self._convert_precipitation_to_mm(raw_value)

  def report_data(self):
    grouped_agents_nested = itertools.groupby(self.agents, key=lambda x: x.get_cell())
    grouped_agents = map(lambda x: list(x[1]), grouped_agents_nested)
    return map(lambda agents: self._report_cell_data(agents), grouped_agents)
  
  def _report_cell_data(self, agents):
    first_agent = agents[0]
    return {
      'year': self._step + START_YEAR,
      'nTrees': len(agents),
      'meanAge': statistics.mean(map(lambda x: x.get_age(), agents)),
      'meanHeight': statistics.mean(map(lambda x: x.get_height(), agents)),
      'temperature': self.get_temperature(first_agent.get_cell()),
      'precipitation': self.get_precipitation(first_agent.get_cell())
    }

  def _convert_precipitation_to_mm(self, value):
    return 31536000 * value



class ForeverTreeAgent(mesa.discrete_space.CellAgent):

  def __init__(self, model, cell):
    super().__init__(model)

    self._cell = cell
    self._age = 0
    self._height = 0

  def grow(self):
    self._age += 1
    self._height += self._get_new_growth()

  def get_cell(self):
    return self._cell

  def get_age(self):
    return self._age

  def get_height(self):
    return self._height

  def _get_new_growth(self):
    temperature_impact = self._get_temperature_impact()
    precipitation_impact = self._get_precipitation_impact()
    stochastic_adjust = self._get_stochastic_adjust()
    return temperature_impact * precipitation_impact * stochastic_adjust

  def _get_temperature_impact(self):
    temperature = self._get_temperature()
    temperature_offset = temperature - MID_TEMPERATURE
    temperature_percent = temperature_offset / TEMPERATURE_RANGE
    parabolic_value = (temperature_percent ** 2) * 4
    return 1 - parabolic_value

  def _get_precipitation_impact(self):
    precipitation = self._get_precipitation()
    precipitation_offset = precipitation - MID_PRECIPITATION
    precipitation_percent = precipitation_offset / PRECIPITATION_RANGE
    exp_value = math.exp(-1 * precipitation_percent * 10)
    return 1 / (1 + exp_value)

  def _get_stochastic_adjust(self):
    return random.gauss(mu=1, sigma=0.05)

  def _get_temperature(self):
    return self.model.get_temperature(self._cell)

  def _get_precipitation(self):
    return self.model.get_precipitation(self._cell)


class GridSize:

  def __init__(self, start_lat, end_lat, start_lon, end_lon, cell_size_km):
    self._start_lat = start_lat
    self._end_lat = end_lat
    self._start_lon = start_lon
    self._end_lon = end_lon
    self._cell_size_km = cell_size_km
    self._width_km = haversine.haversine(
      (start_lat, start_lon),
      (end_lat, start_lon)
    )
    self._height_km = haversine.haversine(
      (start_lat, start_lon),
      (start_lat, end_lon)
    )
    self._width_cells = math.floor(self._width_km / self._cell_size_km)
    self._height_cells = math.floor(self._height_km / self._cell_size_km)
  
  def get_start_lat(self):
    return self._start_lat
  
  def get_end_lat(self):
    return self._end_lat
  
  def get_start_lon(self):
    return self._start_lon
  
  def get_end_lon(self):
    return self._end_lon
  
  def get_cell_size(self):
    return self._cell_size
  
  def get_width_km(self):
    return self._width_km
  
  def get_height_km(self):
    return self._height_km

  def get_width_cells(self):
    return self._width_cells

  def get_height_cells(self):
    return self._height_cells


class ClimateVariable:

  def __init__(self, grid_size, net_cdf, variable):
    self._grid_size = grid_size
    self._net_cdf = net_cdf
    self._variable = variable

    variable_size = self._net_cdf[self._variable].shape
    self._time = variable_size[0]
    self._y_size = variable_size[1]
    self._x_size = variable_size[2]

    self._data = net_cdf.variables[self._variable][:]

    self._assert_area()

  def get_grid_size(self):
    return self._grid_size

  def get_native_time(self):
    return self._time

  def get_native_x_size(self):
    return self._x_size

  def get_native_y_size(self):
    return self._y_size

  def get_value(self, x, y, timestep):
    percent_x = x / self._grid_size.get_width_cells()
    percent_y = y / self._grid_size.get_height_cells()
    mapped_x = math.floor(percent_x * self._x_size)
    mapped_y = math.floor(percent_y * self._y_size)
    return self._data[timestep, mapped_y, mapped_x]

  def _assert_area(self):
    assert abs(min(self._net_cdf.variables['lat']) - MIN_LAT) < 0.0001
    assert abs(max(self._net_cdf.variables['lat']) - MAX_LAT) < 0.0001
    assert abs(min(self._net_cdf.variables['lon']) - MIN_LON) < 0.0001
    assert abs(max(self._net_cdf.variables['lon']) - MAX_LON) < 0.0001


class CacheClimateVariable:

  def __init__(self, climate_variable):
    self._last_timestep = None
    self._climate_variable = climate_variable
    self._cache = {}

  def get_grid_size(self):
    return self._climate_variable.get_grid_size()

  def get_native_time(self):
    return self._climate_variable.get_native_time()

  def get_native_x_size(self):
    return self._climate_variable.get_native_x_size()

  def get_native_y_size(self):
    return self._climate_variable.get_native_y_size()

  def get_value(self, x, y, timestep):
    if self._last_timestep != timestep:
      self._last_timestep = timestep
      self._cache = {}

    key = (x, y)
    if key not in self._cache:
      self._cache[key] = self._climate_variable.get_value(x, y, timestep)

    return self._cache[key]


class ReplicateKit:

  def __init__(self, temperatures, precipitations, model):
    self._temperatures = temperatures
    self._precipitations = precipitations
    self._model = model
  
  def get_temperatures(self):
    return self._temperatures
  
  def get_precipitations(self):
    return self._precipitations
  
  def get_model(self):
    return self._model


def build_replicate_kit():
  grid_size = GridSize(MIN_LAT, MAX_LAT, MIN_LON, MAX_LON, CELL_SIZE_KM)
  
  temperatures_raw = netCDF4.Dataset('../data/maxtemp_synthetic.nc', 'r', format="NETCDF4")
  temperatures_native = CacheClimateVariable(ClimateVariable(grid_size, temperatures_raw, 'tasmax'))
  temperatures = temperatures_native
  
  precipitations_raw = netCDF4.Dataset('../data/precip_synthetic.nc', 'r', format="NETCDF4")
  precipitations_native = CacheClimateVariable(ClimateVariable(grid_size, precipitations_raw, 'pr'))
  precipitations = precipitations_native

  model = ForeverTreeModel(grid_size, temperatures, precipitations)
  return ReplicateKit(temperatures, precipitations, model)


def run_replicate(replicate_kit, output_loc):
  temperatures = replicate_kit.get_temperatures()
  precipitations = replicate_kit.get_precipitations()
  model = replicate_kit.get_model()

  with open(output_loc, 'w') as f:
    writer = csv.DictWriter(f, fieldnames=EXPECTED_FIELDS)
    writer.writeheader()

    for step in range(0, NUM_TIMESTEPS):
      print(' > Step %d in %s' % (step, output_loc))
      model.step()
      writer.writerows(model.report_data())


def main_with_parallel(replicates, output_template):
  def run_contained_replicate(output_location):
    kit = build_replicate_kit()
    run_replicate(kit, output_location)
    return output_location

  output_locations = map(lambda x: output_template % x, range(0, replicates))
  num_nodes = multiprocessing.cpu_count() - 1
  pool = pathos.pools.ProcessPool(nodes=num_nodes)

  for completed_loc in pool.imap(run_contained_replicate, output_locations):
    print('Completed %s' % completed_loc)


def main_without_parallel(replicates, output_template):
  print('Loading...')
  kit = build_replicate_kit()

  for replicate in range(0, replicates):
    print('Running replicate %d...' % replicate)
    run_replicate(kit, output_template % replicate)


def main():

  if len(sys.argv) != NUM_ARGS + 1:
    print(USAGE_STR)
    return

  replicates = int(sys.argv[1])
  
  threaded_str = sys.argv[2].lower().strip()
  threaded = threaded_str == '1' or threaded_str == 't' or threaded_str == 'true'

  output_template = sys.argv[3]

  if threaded:
    print('Running parallel.')
    main_with_parallel(replicates, output_template)
  else:
    print('Running without parallelism.')
    main_without_parallel(replicates, output_template)


if __name__ == '__main__':
  main()
