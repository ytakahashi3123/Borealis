#!/usr/bin/env python3

# Borealis: Bayesian optimization for finding a realizable solution for a discretized equation
# Version 1.6.0
# Date: 2026/08/31

# Author: Yusuke Takahashi, Hokkaido University
# Contact: ytakahashi@eng.hokudai.ac.jp

code_name = "Borealis"
version = "1.6.1"

import numpy as np
from mpi.mpi import mpi
from orbital.orbital import orbital

def main():

  # MPI settings
  mpi_instance = mpi()

  # Class orbital
  orbit = orbital()

  # Read control file
  file_control_default = orbit.file_control_default
  arg          = orbit.argument(file_control_default)
  file_control = arg.file
  config       = orbit.read_config_yaml(file_control)

  # Select adapter
  if config['adapter']['kind_adapter'] == 'tacode':
    from adapter_tacode.adapter_tacode import adapter_tacode
    adapter = adapter_tacode(mpi_instance)
  elif config['adapter']['kind_adapter'] == 'simple_function':
    from adapter_template.adapter_simple_function import adapter_simple_function
    adapter = adapter_simple_function(mpi_instance)
  elif config['adapter']['kind_adapter'] == 'example_externalcode':
    from adapter_template.adapter_example_externalcode import adapter_example_externalcode
    adapter = adapter_example_externalcode(mpi_instance)
  elif config['adapter']['kind_adapter'] == 'heatcond':
    from adapter_heatcond.adapter_heatcond import adapter_heatcond
    adapter = adapter_heatcond(mpi_instance)
  elif config['adapter']['kind_adapter'] == 'cage':
    from adapter_cage.adapter_cage import adapter_cage
    adapter = adapter_cage(mpi_instance)
  elif config['adapter']['kind_adapter'] == 'shapeoptimizer':
    from adapter_shapeoptimizer.adapter_shapeoptimizer import adapter_shapeoptimizer
    adapter = adapter_shapeoptimizer(mpi_instance)
  elif config['adapter']['kind_adapter'] == 'shapeoptimizer_mp':
    from adapter_shapeoptimizer_mp.adapter_shapeoptimizer import adapter_shapeoptimizer
    adapter = adapter_shapeoptimizer(mpi_instance)
  elif config['adapter']['kind_adapter'] == 'pixelflow':
    from adapter_pixelflow.adapter_pixelflow import adapter_pixelflow
    adapter = adapter_pixelflow(mpi_instance)
  elif config['adapter']['kind_adapter'] == 'user':
    from adapter_user.adapter_user import adapter_user
    adapter = adapter_user(mpi_instance)
  else:
    print('Error, invalid adapter is selected. Check adapter.kind_adapter in',file_control,':', config['adapter']['kind_adapter'])
    print('Program stopped.')
    exit()

  # Initialize for simulation software defined in adapter
  adapter.initial_settings(config)

  # Reference data for objective function
  adapter.reference_data_setting(config)

  # Objective function
  objective_function = adapter.objective_function

  # Class optimization
  if config['optimizer']['kind_optimizer'] == 'Bayesian_optimization':
    from Bayesian_optimization.Bayesian_optimization import Bayesian_optimization
    optimizer = Bayesian_optimization(mpi_instance)
  elif config['optimizer']['kind_optimizer'] == 'PSO':
    from optimizer_pso.optimizer_pso import optimizer_pso
    optimizer = optimizer_pso(mpi_instance)
  elif config['optimizer']['kind_optimizer'] == 'PSO_mp':
    from optimizer_pso_mp.optimizer_pso import optimizer_pso
    optimizer = optimizer_pso(mpi_instance)
  elif config['optimizer']['kind_optimizer'] == 'ABC':
    from optimizer_abc.optimizer_abc import optimizer_abc
    optimizer = optimizer_abc(mpi_instance)
  #elif config['optimizer']['kind_optimizer'] == 'GA':
  #  from optimizer_ga.optimizer_ga import optimizer_ga
  #  optimizer = optimizer_ga(mpi_instance)
  else:
    print('Error, invalid optimizer is selected. Check optimizer.kind_optimizer in',file_control,':', config['optimizer']['kind_optimizer'])
    print('Program stopped.')
    exit()

  # Initial setting
  optimizer.initial_setting(config)

  # Define parameter boundaries
  parameter_boundary = optimizer.boundary_setting(config)

  # Run Bayesian optimization
  optimizer.drive_optimization(config, objective_function, parameter_boundary)

  return


if __name__ == '__main__':

  print('Program name:',code_name, 'version:', version)
  print('Initialize optimization process')

  main()

  print('Finalize optimization process')
  exit()

