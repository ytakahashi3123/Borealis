#!/usr/bin/env python3

import numpy as np
from orbital.orbital import orbital


class adapter_simple_function(orbital):

  def __init__(self,mpi_instance):

    print("Constructing class: adapter_simple_function")

    self.mpi_instance = mpi_instance

    # 最大化の符号を自分で掛ける（既知の問題 1）。状態を持たないのでスレッドから同時に呼んでよい
    self.flag_apply_sign = True
    self.flag_parallel_evaluation = True

    return

  
  def initial_settings(self, config):

    # Control file 
    #self.config = config
    
    # Number of objectives
    self.num_objectives = config['objectives']['num_objectives']

    #if config['simple_function']['flag_eval']:
    #x = 2
    #function_user = eval(config['simple_function']['function_eval'])
    #print(function_user)

    # Function output
    if self.mpi_instance.rank == 0:
      if( config['simple_function']['flag_output'] ):
        result_dir   = config['simple_function']['result_dir']
        filename_tmp = result_dir + '/' + config['simple_function']['filename_output']
        super().make_directory_rm(result_dir)
        x_div = config['simple_function']['function_discrete']
        x_min = config['simple_function']['function_bound_min']
        x_max = config['simple_function']['function_bound_max']
        x_tmp = np.linspace(x_min, x_max, x_div)
        y_tmp = self.function(x_tmp)
        #header_tmp = 'Variables=x, y'
        header_tmp    = 'Variables=x, f1, f2'
        delimiter_tmp = '\t'
        comments_tmp  = ''
        #output_tmp    = np.c_[x_tmp, y_tmp]
        #np.savetxt(filename_tmp, output_tmp, header=header_tmp, delimiter=delimiter_tmp, comments=comments_tmp )
        f_tmp = np.array( [self.function(np.array([x])) for x in x_tmp] )
        output_tmp = np.c_[ x_tmp, f_tmp[:, 0], f_tmp[:, 1] ]
        np.savetxt(filename_tmp, output_tmp, header=header_tmp, delimiter=delimiter_tmp, comments=comments_tmp )

    # Counter
    self.iter = 1
     
    return


  def reference_data_setting(self, config):

    return


  #def function(self, x):
  #  return 2*np.sin(x) + 4*np.cos(2 * x) + 3*np.cos(2/5 * x)

  #def objective_function(self, x):
  # Ackley
  #  y1 = 22.71828
  #  y2 = -20 * np.exp(-0.2 * np.sqrt(1.0 / len(x) * np.sum(x ** 2, axis=0)))
  #  y4 = -np.exp(1.0 / len(x) * np.sum(np.cos(2.0 * np.pi * x), axis=0))
  #  return y1 + y2 + y4

#  def function(self, x):
#    # Sphere_function
#    return np.sum(x**2)

  def function(self, x):
    # For multi-objective: Sphere_function with shift
    x = np.asarray(x)
    objectives = []
    for i in range(self.num_objectives):
      shift = float(i) * 2.0
      f = np.sum((x - shift) ** 2)
      objectives.append(f)
    return np.array(objectives)


  @orbital.time_measurement_decorated
  def objective_function(self, parameter_opt, *args):

    if args: self.iter = args[0]
    # 最大化の符号（PSO・ABC が第 4 引数で渡す）
    sign_of = args[2] if len(args) > 2 else 1.0

    #print('Iteration: ', self.iter)

    x = np.asarray(parameter_opt)

    # Function
    result = sign_of * self.function(x)

    if not args: self.iter += 1

    return np.atleast_1d(result).astype(float)
