import itertools
import math
import random

import mesa

MIN_TEMPERATURE = 270
MAX_TEMPERATURE = 330
TEMPERATURE_RANGE = MAX_TEMPERATURE - MIN_TEMPERATURE
MID_TEMPERATURE = (MAX_TEMPERATURE + MIN_TEMPERATURE) / 2

MIN_PRECIPITATION = 300
MAX_PRECIPITATION = 500
PRECIPITATION_RANGE = MAX_PRECIPITATION - MIN_PRECIPITATION
MID_PRECIPITATION = (MIN_PRECIPITATION + MAX_PRECIPITATION) / 2


class ForeverTreeModel(mesa.Model):

  def __init__(self, width, height, num_per_space=10, rng=None):
    super().__init__(rng=rng)
    self._grid = mesa.discrete_space.OrthogonalMooreGrid(
      (width, height),
      torus=True,
      random=self.random
    )

    unique_spaces = itertools.product(
      range(0, width),
      range(0, height)
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



class ForeverTreeAgent(mesa.discrete_space.CellAgent):

  def __init__(self, model, cell):
    super().__init__(model)

    self._cell = cell
    self._age = 0
    self._height = 0

  def grow(self):
    self._age += 1
    self._height += self._get_new_growth()

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
    return MID_TEMPERATURE

  def _get_precipitation(self):
    return MID_PRECIPITATION



def main():
  model = ForeverTreeModel(100, 100)
  for _ in range(0, 101):
    model.step()


if __name__ == '__main__':
  main()
