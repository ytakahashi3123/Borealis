#!/usr/bin/env python3

from functools import wraps
from mpi4py import MPI


class mpi():

  def __init__(self):

    self.MPI = MPI
    self.comm = MPI.COMM_WORLD
    self.rank = MPI.COMM_WORLD.Get_rank()
    self.size = MPI.COMM_WORLD.Get_size()
    self.name = MPI.Get_processor_name()

    if self.size == 1:
      self.flag_mpi = False
    else :
      self.flag_mpi = True

    #if config['mpi']['flag_mpi']:
    #  self.MPI = MPI
    #  self.comm = MPI.COMM_WORLD
    #  self.rank = MPI.COMM_WORLD.Get_rank()
    #  self.size = MPI.COMM_WORLD.Get_size()
    #  self.flag_mpi = True
    #else:
    #  self.rank = 0
    #  self.size = 1
    #  self.flag_mpi = False

    return


  # Decorator for time measurement
  def mpitime_measurement_decorated(func):
    @wraps(func)
    def wrapper(*args, **kargs) :
      #text_blue = '\033[94m'
      #text_green = '\033[92m'
      text_yellow = '\033[93m'
      text_end = '\033[0m'
      flag_time_measurement = False
      if flag_time_measurement :
        start_time = MPI.Wtime()
        result = func(*args,**kargs)
        elapsed_time = MPI.Wtime() - start_time
        if MPI.COMM_WORLD.Get_rank() == 0:
          print('Elapsed time of '+str(func.__name__)+str(':'),text_yellow + str(elapsed_time) + text_end,'s')
      else :
        result = func(*args,**kargs)
      return result 
    return wrapper

