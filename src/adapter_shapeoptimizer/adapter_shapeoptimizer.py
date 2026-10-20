#!/usr/bin/env python3

# Borealis adapter: Python script to run Borealis with preCICE for Shape Optimization.

import numpy as np
import os
import re
import sys
import shutil as shutil
import subprocess
import time
#import signal
from orbital.orbital import orbital

class adapter_shapeoptimizer(orbital):
  
  def __init__(self,mpi_instance):

    print("Constructing class: adapter_shapeoptimizer")

    self.mpi_instance = mpi_instance

    return    


  def initial_settings(self, config):

    # Get current time of the system
    self.current_time = time.time()

    self.work_dir   = config['shapeoptimizer']['work_dir']
    self.case_dir   = config['shapeoptimizer']['case_dir']
    self.step_digit = config['shapeoptimizer']['step_digit']

    # Make directory
    if self.mpi_instance.rank == 0:
      super().make_directory_rm(self.work_dir)

    # Template case 
    path_specify = config['shapeoptimizer']['directory_path_specify']
    default_path = '../../shapeoptimizer'
    manual_path  = config['shapeoptimizer']['manual_path']
    self.template_path = self.get_directory_path(path_specify, default_path, manual_path)

    self.work_dir_template = self.work_dir+'/'+self.case_dir+'_template'
    if self.mpi_instance.rank == 0:
      shutil.copytree(self.template_path, self.work_dir_template)

    # Control file and computed result file
    #self.filename_control_code = config['shapeoptimizer']['filename_control']
    #self.filename_result_code  = config['shapeoptimizer']['filename_result']

    # Execution file
    self.cmd_code = config['shapeoptimizer']['cmd_code']
    self.root_dir = os.getcwd()
    self.cmd_home = os.path.dirname(os.path.realpath(__file__)) + '/..'

    # Target parameter (corresponding to the parameter boundary)
    self.parameter_target = config['parameter_optimized']['boundary']

    # Result file: Make directory
    if self.mpi_instance.rank == 0:
      super().make_directory_rm(config['shapeoptimizer']['result_dir'])

    # Control file 
    self.config = config

    # Counter
    self.step = 1

    # Counter
    self.pid = 1

    # Delete old file
    self.filename_jobrequests = "job_requests"
    #if self.mpi_instance.rank == 0:
    #  if os.path.exists(self.filename_jobrequests):
    #    try:
    #      os.remove(self.filename_jobrequests)
    #      print(f"{self.filename_jobrequests} has been deleted.")
    #    except OSError as e:
    #      print(f"Failed to delete {self.filename_jobrequests}: {e}", file=sys.stderr)
    #      sys.exit(1)  # 終了コード1でスクリプト終了
    #  else:
    #    print(f"{self.filename_jobrequests} does not exist.")

    # 同期をとる
    if self.mpi_instance.flag_mpi:
      self.mpi_instance.comm.Barrier()

    # For result data reading
    #self.headerline_variables = 1
    #self.num_skiprows = 2

    # Get number of dimension and check its consistency
    num_dims = []
    for param in self.parameter_target:
      component_list = param.get('component', [])
      coordinate_list = param.get('coordinate', [])
      num_dim = len(component_list)
      num_dims.append(num_dim)
      #print(f"{param['name']}: number of dimensions = {num_dim}")
    # 全て同じ次元かどうかをチェック
    all_same_dim = all(n == num_dims[0] for n in num_dims)
    if all_same_dim:
      print(f"[ShapeOpt-Borealis] All the dimensions of the parameter are the same: {num_dim} dimensions")
    else:
      print(f"[ShapeOpt-Borealis] Dimenions of the parameter is different")
      print(f"[ShapeOpt-Borealis] Number of dimensions of each element: {num_dims}")
      raise SystemExit()
    self.num_dim = num_dim
    
    # Get number of boundary（= number of "name"
    num_marker = len(self.parameter_target)
    print(f"[ShapeOpt-Borealis] Number of markers: {num_marker}")
    self.num_marker = num_marker

    # Set variables for optimization
    self.displacements = np.zeros((self.num_marker,self.num_dim))
    self.forces_marker = np.zeros(self.num_dim)
    if self.num_dim == 2:
      self.moments_marker = np.zeros(1)
    else:
      self.moments_marker = np.zeros(3)

    # 非定常空気力データを目的関数として時間経過とともに形状最適化を行う
    self.in_sequential = config['shapeoptimizer']['in_sequential']
        
    # File names
    self.work_dir_series    = config['shapeoptimizer']['work_dir_series']
    self.forces_file        = config['shapeoptimizer']['filename_forces']
    self.displacements_file = config['shapeoptimizer']['filename_displacements']
    self.step_digit_series  = config['shapeoptimizer']['step_digit_series']

    # Surface area constraint
    self.flag_surfacearea_constraint = config.get('shapeoptimizer', {}).get('flag_surfacearea_constraint', False)
    if self.flag_surfacearea_constraint:
      self.work_dir_surfacearea  = config.get('shapeoptimizer', {}).get('work_dir_surfacearea', 'fluid')
      self.filename_surfacearea  = config.get('shapeoptimizer', {}).get('filename_surfacearea', 'surfacearea_su2.dat')
      self.tolerance_surfacearea = config.get('shapeoptimizer', {}).get('tolerance_surfacearea', 0.05)

    if self.in_sequential :
      # Caseディレクトリの作成
      self.work_dir_case = self.work_dir + '/' + self.case_dir + '_rank' + str(self.mpi_instance.rank+1).zfill(self.step_digit)
      print('[ShapeOpt-Borealis] --Make case directory: ', self.work_dir_case)
      shutil.copytree(self.work_dir_template, self.work_dir_case)
      # Set file names
      self.filename_displacements_base = self.work_dir_case+'/'+self.work_dir_series+'/'+os.path.splitext(self.displacements_file)[0]
      self.filename_displacements_ext  = os.path.splitext(self.displacements_file)[1]
      self.filename_forces_base        = self.work_dir_case+'/'+self.work_dir_series+'/'+os.path.splitext(self.forces_file)[0]
      self.filename_forces_ext         = os.path.splitext(self.forces_file)[1]
      if self.flag_surfacearea_constraint:
        self.filename_surfacearea_base = self.work_dir_case+'/'+self.work_dir_surfacearea+'/'+os.path.splitext(self.filename_surfacearea)[0]
        self.filename_surfacearea_ext  = os.path.splitext(self.filename_surfacearea)[1]

    # Delete old files if the files remain
    #self.delete_step_files(forces_file, digit=self.step_digit_series, directory=self.work_dir_case+'/'+self.work_dir_series)
    #self.delete_step_files(displacements_file, digit=self.step_digit_series, directory=self.work_dir_case+'/'+self.work_dir_series)

    # Indexes and powers
    #self.index_var_of = config['shapeoptimizer']['index_variable_objectivefunction']
    #self.power_var_of = config['shapeoptimizer']['power_variable_objectivefunction']

    return


  def reference_data_setting(self, config):
    # Optimizerの処理で必要。特に何も行わない
    return


  def load_mapped_data(self, filename, nDim=2):
    data = []
    with open(filename, "r") as f:
        # Skip Tecplot headers
        while True:
            line = f.readline()
            if not line:
                raise ValueError("ZONE not found in .dat file.")
            if line.strip().startswith("ZONE"):
                break
        for line in f:
            if not line.strip():
                continue  # skip empty lines
            values = line.strip().split()
            if nDim == 2 :
                d = {
                    "sample_point": [float(values[0]), float(values[1])],
                    "nearest_node_id": int(values[3]),
                    "nearest_node_coord": [float(values[4]), float(values[5])],
                    "triangle_id": int(values[7])
                }
            else:
                d = {
                    "sample_point": [float(values[0]), float(values[1]), float(values[2])],
                    "nearest_node_id": int(values[3]),
                    "nearest_node_coord": [float(values[4]), float(values[5]), float(values[6])],
                    "triangle_id": int(values[7])
                }
            data.append(d)
    return data
  
  def write_displacements(self, filename, displacements):
    if not isinstance(displacements, np.ndarray):
        raise TypeError("[ShapeOpt-Borealis-ERROR] displacements must be a numpy ndarray.")
    if displacements.ndim != 2:
        raise ValueError("[ShapeOpt-Borealis-ERROR] displacements must be a 2D numpy array.")
    try:
        with open(filename, 'w') as f:
            for row in displacements:
                f.write(' '.join(f"{val:.6e}" for val in row) + '\n')
        #print(f"[Borealis-INFO] Displacements written to '{filename}'")
    except Exception as e:
        print(f"[ShapeOpt-Borealis-ERROR] Failed to write displacements to file: {e}")

  def read_forces_marker(self, filename):
    with open(filename, 'r') as f:
        lines = f.readlines()
    # 1行目: forces
    forces = np.array([float(x) for x in lines[0].split()])
    # 2行目: moments
    moments = np.array([float(x) for x in lines[1].split()])
    return forces, moments

  def read_surfaceares_marker(self, filename):
    if not os.path.exists(filename):
      print(f"Error: {filename} does not exist.")
      return None, None
    try:
      with open(filename, 'r') as f:
        lines = f.readlines()   
        # 1行目はヘッダー、2行目にデータがある前提
        if len(lines) >= 2:
          data_line = lines[1].strip()
          # カンマまたはスペースで分割して数値に変換
          # write側でカンマ区切りにした場合はこれで行けます
          parts = data_line.replace(',', ' ').split()
          area = float(parts[0])
          area_init = float(parts[1])                
          return area, area_init
        else:
          print(f"Error: {filename} is empty or malformed.")
          return None, None
    except Exception as e:
      print(f"An error occurred while reading: {e}")
      return None, None

  def write_request_instruction(self, filename):
    print('[ShapeOpt-Borealis] Writing job requests file')
    size = self.mpi_instance.size # 並列数
    filename_request_instruction = filename
    with open(filename_request_instruction, "w") as f:
      f.write("Directories for subprocesses:\n")
      for n in range(0,size):
        work_dir_case_rank = self.work_dir + '/' + self.case_dir + '_rank' + str(n+1).zfill(self.step_digit)
        f.write(f"{work_dir_case_rank}\n")

  def write_request_instruction_para(self, filename, pid):
    comm = self.mpi_instance.comm
    rank = self.mpi_instance.rank
    # 各ランクが自分のディレクトリを作る
    work_dir_case_rank = self.work_dir + '/' + self.case_dir + '_rank' + str(pid).zfill(self.step_digit) 
    # rank 0 に集約
    all_dirs = comm.gather(work_dir_case_rank, root=0)
    # rank 0 だけ書き込み
    if rank == 0:
        str_tmp = "Directories for subprocesses:\n"
        for d in all_dirs:
            str_tmp = str_tmp + f"{d}\n"
        print('[ShapeOpt-Borealis] Writing job requests file by rank0', rank, 'Strings in file:')
        print(str_tmp)
        with open(filename, "w") as f:
            f.write(str_tmp)

  def run_subprocess(self):
    print('[ShapeOpt-Borealis] Run subprocess')
    os.chdir( self.work_dir_case )
    #subprocess.call( "./run_SU2-OPT_pps.sh" )
    proc = subprocess.Popen(["./run_SU2-OPT_pps.sh"])
    os.chdir( self.root_dir )
    return proc


  def objective_function(self, parameter_opt, *args):

    # args[0]: 粒子ID
    # args[1]: 最適化ステップ
    # args[2]: 目的関数を最大化するか最小化するか
    if not args:
      pid  = self.pid
      step = self.step
      sign_of = 1.0
    else:
      pid = args[0]
      step = args[1]
      sign_of = args[2]

    print('[ShapeOpt-Borealis] Iteration: ', pid)

    # File names
    if self.in_sequential:
      step_str = f"{step:0{self.step_digit_series}d}"
      filename_displacements_series = f"{self.filename_displacements_base}_step{step_str}{self.filename_displacements_ext}"
      filename_forces_series = f"{self.filename_forces_base}_step{step_str}{self.filename_forces_ext}"
      if self.flag_surfacearea_constraint:
        filename_surfacearea_series = f"{self.filename_surfacearea_base}_step{step_str}{self.filename_surfacearea_ext}"
    else :
      # Caseディレクトリの作成
      work_dir_case = self.work_dir + '/' + self.case_dir + '_rank' + str(pid).zfill(self.step_digit)
      print('[ShapeOpt-Borealis] --Make case directory: ', work_dir_case)
      shutil.copytree(self.work_dir_template, work_dir_case) 
      filename_displacements_base = work_dir_case+'/'+self.work_dir_series+'/'+os.path.splitext(self.displacements_file)[0]
      filename_displacements_ext  = os.path.splitext(self.displacements_file)[1]
      filename_displacements_series = f"{filename_displacements_base}{filename_displacements_ext}"
      filename_forces_base        = work_dir_case+'/'+self.work_dir_series+'/'+os.path.splitext(self.forces_file)[0]
      filename_forces_ext         = os.path.splitext(self.forces_file)[1]
      filename_forces_series = f"{filename_forces_base}{filename_forces_ext}"
      if self.flag_surfacearea_constraint:
        filename_surfacearea_base   = work_dir_case+'/'+self.work_dir_surfacearea+'/'+os.path.splitext(self.filename_surfacearea)[0]
        filename_surfacearea_ext    = os.path.splitext(self.filename_surfacearea)[1]
        filename_surfacearea_series = f"{filename_surfacearea_base}{filename_surfacearea_ext}"

    # Write displacements file
    self.displacements = parameter_opt.reshape(self.num_marker, self.num_dim)
    self.write_displacements(filename_displacements_series, self.displacements)
    print(f"[ShapeOpt-Borealis] PID {pid} and Step {step+1}: Wrote {filename_displacements_series}\n", f"Displacements: {self.displacements[1,:]}..{self.displacements[-1,:]}")

    # 形状最適化(shapeoptimizer_preCICE)サブプロセスの起動指示ファイルを生成
    # ->中間スクリプトがこれを検知して形状最適化を実行する（親プロセスをMPIで起動したとき、親プロセスが子プロセスをMPIで起動できない仕様上このような措置を図る）
    if self.in_sequential:
      if step == 0:
        if self.mpi_instance.rank == 0:
          self.write_request_instruction(self.filename_jobrequests)
    else:
      self.write_request_instruction_para(self.filename_jobrequests, pid)
      
    if self.mpi_instance.flag_mpi:
      self.mpi_instance.comm.Barrier()

    # Get forces data
    while not os.path.exists(filename_forces_series):
      time.sleep(3.0)
    self.forces_marker, self.moments_marker = self.read_forces_marker(filename_forces_series)
    print(f"[ShapeOpt-Borealis] PID {pid} and Step {step+1}: Read {filename_forces_series}\n", f"Forces and Moments: {self.forces_marker} {self.moments_marker} ")

    # Penalty
    #penalty = 0.0
    #if self.config['parameter_optimized']['flag_penalty']:
    #  boundary = self.config['parameter_optimized']['boundary']
    #  huge_tmp = self.config['parameter_optimized']['penalty_value']
    #  penalty = super().get_penalty_term(parameter_opt, boundary, huge_tmp)
    if self.config['parameter_optimized']['flag_penalty']:
      boundary  = self.config['parameter_optimized']['boundary']
      huge_tmp  = self.config['parameter_optimized']['penalty_value']
      if isinstance(huge_tmp, list):
        # 目的ごとに異なるペナルティ
        penalty = np.array([ super().get_penalty_term(parameter_opt, boundary, h) for h in huge_tmp ])
      else:
        # スカラー：全目的に同じペナルティ
        penalty = super().get_penalty_term(parameter_opt, boundary, huge_tmp)
    else:
      penalty = 0.0

    # Get surface area
    if self.flag_surfacearea_constraint:
      surfacearea, surfacearea_init = self.read_surfaceares_marker(filename_surfacearea_series)
      ratio_surfacearea = abs( (surfacearea - surfacearea_init)/surfacearea_init )
      print(f"[ShapeOpt-Borealis] PID {pid} and Step {step+1}: Read {filename_surfacearea_series}\n", f"Surface area ratio: {ratio_surfacearea}")
      if ratio_surfacearea >= self.tolerance_surfacearea:
        penalty = penalty + self.config['shapeoptimizer']['penalty_surfacearea']

    # Evaluate error
    error = sign_of * np.array([ self.forces_marker[0], self.moments_marker[0] ]) + penalty
    error = sign_of * np.array([ self.forces_marker[0], self.moments_marker[0] ]) + penalty

    # カウンタの更新
    if not args:
      self.pid  += 1
      self.step += 1

    return np.atleast_1d(error).astype(float)
