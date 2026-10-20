#!/usr/bin/env python3

# Borealis adapter: Python script to run Borealis with preCICE for Shape Optimization.

# 外部コード(SU2+shapeoptimizer_preCICE)はMPI並列で起動するため、Borealis本体はmpirunで起動しない。
# 複数ケースの同時実行は、オプティマイザ側(PSO.num_parallel)がスレッドで目的関数を同時に呼び出すことで実現する。
# 以前のジョブ依頼ファイル(job_requests)+外部監視スクリプト方式は previous/adapter_shapeoptimizer_requestfile.py を参照。

import numpy as np
import os
import sys
import shutil as shutil
import subprocess
import signal
import atexit
import threading
import queue
import time
from orbital.orbital import orbital

class adapter_shapeoptimizer(orbital):

  def __init__(self,mpi_instance):

    print("Constructing class: adapter_shapeoptimizer")

    self.mpi_instance = mpi_instance

    # objective_functionをスレッドから同時に呼び出してよいことをオプティマイザへ示すフラグ
    self.flag_parallel_evaluation = True
    # 最大化の符号を自分で掛けることをオプティマイザへ示すフラグ（既知の問題 1）
    self.flag_apply_sign = True

    return


  def initial_settings(self, config):

    # Get current time of the system
    self.current_time = time.time()

    self.work_dir   = config['shapeoptimizer']['work_dir']
    self.case_dir   = config['shapeoptimizer']['case_dir']
    self.step_digit = config['shapeoptimizer']['step_digit']

    if self.mpi_instance.flag_mpi:
      print('[ShapeOpt-Borealis] Warning: Borealis is launched with MPI. External MPI codes may fail to start from MPI-launched processes.')
      print('[ShapeOpt-Borealis] Warning: Launch Borealis without mpirun and use PSO.num_parallel for concurrent evaluations.')

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

    # Counter (used only when the optimizer does not pass IDs, e.g. Bayesian optimization)
    self.step = 1
    self.pid = 1
    self.lock_counter = threading.Lock()

    # 同期をとる
    if self.mpi_instance.flag_mpi:
      self.mpi_instance.comm.Barrier()

    # Get number of dimension and check its consistency
    num_dims = []
    for param in self.parameter_target:
      component_list = param.get('component', [])
      num_dim = len(component_list)
      num_dims.append(num_dim)
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

    # Parallel execution of external code
    # 各ケースにCPUコアの組(slot)を割り当て、環境変数BOREALIS_CPU_SET/BOREALIS_NUM_CPU/BOREALIS_SLOTで実行スクリプトへ渡す
    kind_optimizer = config['optimizer']['kind_optimizer']
    num_parallel = int( config.get(kind_optimizer, {}).get('num_parallel', 1) )
    self.num_cpu_per_case = int( config['shapeoptimizer'].get('num_cpu_per_case', 2) )
    self.cpu_offset       = int( config['shapeoptimizer'].get('cpu_offset', 0) )
    self.flag_cpu_set     = config['shapeoptimizer'].get('flag_cpu_set', True)
    self.polling_interval = float( config['shapeoptimizer'].get('polling_interval', 3.0) )
    self.timeout_finalize = float( config['shapeoptimizer'].get('timeout_finalize', 600.0) )
    self.penalty_failure  = float( config['shapeoptimizer'].get('penalty_failure', 1.e+10) )
    # コアの割り当て方。affinity: このプロセスに使うことが許されたコアの並び（ジョブスケジューラが割り当てたコア）から順に取る。
    # absolute: 0 番からの絶対番号（以前の動き）。ジョブのコアが 0 番から始まらないと外れる（既知の問題 20）
    self.cpu_assignment   = config['shapeoptimizer'].get('cpu_assignment', 'affinity')
    if self.cpu_assignment not in ('affinity', 'absolute'):
      raise ValueError(f"shapeoptimizer.cpu_assignment must be affinity or absolute: {self.cpu_assignment}")
    try:
      self.cpu_available = sorted( os.sched_getaffinity(0) )
    except AttributeError:
      # sched_getaffinity の無い OS（macOS など）
      self.cpu_available = list( range(os.cpu_count()) )

    # 目的関数の値: 1 目的なら [抗力]、2 目的なら [抗力, モーメント]（以前は常に 2 つ返し、単目的で止まっていた。既知の問題 15）
    self.num_objectives = int( config.get('objectives', {}).get('num_objectives', 1) )
    if self.num_objectives not in (1, 2):
      raise ValueError(f"shapeoptimizer supports objectives.num_objectives = 1 (drag) or 2 (drag and moment): {self.num_objectives}")

    if self.in_sequential:
      # 逐次最適化では粒子ごとに連成計算が常駐するため、粒子番号をそのままslotとして使う
      if kind_optimizer != 'PSO':
        print('[ShapeOpt-Borealis] Error: in_sequential: True is supported only with PSO.')
        raise SystemExit()
      self.num_particle = int( config['PSO']['num_particle'] )
      num_slot = self.num_particle
      self.proc_sequential = {}
    else:
      num_slot = num_parallel
      self.queue_slot = queue.Queue()
      for n in range(0, num_slot):
        self.queue_slot.put(n)

    num_cpu_required = self.cpu_offset + num_slot * self.num_cpu_per_case
    num_cpu_available = len(self.cpu_available) if self.cpu_assignment == 'affinity' else os.cpu_count()
    print(f"[ShapeOpt-Borealis] Number of slots: {num_slot}, CPUs per case: {self.num_cpu_per_case}, CPUs required: {num_cpu_required}, "
          f"CPU assignment: {self.cpu_assignment} ({num_cpu_available} CPUs available)")
    if self.flag_cpu_set and num_cpu_required > num_cpu_available:
      raise ValueError(f"[ShapeOpt-Borealis] CPUs required ({num_cpu_required}) exceed CPUs available ({num_cpu_available}). "
                       "Reduce num_parallel or num_cpu_per_case, or request more cores for the job.")

    # 終了時(正常終了・例外とも)に残っている外部コードのプロセスを停止する
    self.procs_running = set()
    self.lock_procs = threading.Lock()
    atexit.register(self.terminate_subprocesses)

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


  def get_subprocess_env(self, slot):
    # os.environはPython起動時のスナップショットであり、mpi4pyのimport(MPI_Init)時にC側で追加されるOMPI_*/PMIX_*等を含まない。
    # env=Noneのままだとそれらが子プロセスに継承され、子プロセス側のmpirunが失敗する
    env = dict(os.environ)
    env['BOREALIS_SLOT']    = str(slot)
    env['BOREALIS_NUM_CPU'] = str(self.num_cpu_per_case)
    if self.flag_cpu_set:
      cpu_start = self.cpu_offset + slot * self.num_cpu_per_case
      if self.cpu_assignment == 'affinity':
        cpu_list = self.cpu_available[cpu_start : cpu_start + self.num_cpu_per_case]
      else:
        cpu_list = range(cpu_start, cpu_start + self.num_cpu_per_case)
      env['BOREALIS_CPU_SET'] = ','.join( str(c) for c in cpu_list )
    return env


  def run_code(self, work_dir_case, slot):
    print(f'[ShapeOpt-Borealis] Run subprocess: {work_dir_case}, slot: {slot}')
    env = self.get_subprocess_env(slot)
    # start_new_session: 実行スクリプトが起動するmpirun等をプロセスグループごと停止できるようにする
    with open(work_dir_case + '/log_subprocess', 'w') as file_log:
      proc = subprocess.Popen( [self.cmd_code], cwd=work_dir_case, env=env, stdout=file_log, stderr=subprocess.STDOUT, start_new_session=True )
    with self.lock_procs:
      self.procs_running.add(proc)
    return proc


  def kill_subprocess(self, proc):
    # 実行スクリプト自体が終了していても、取り残された子プロセス(mpirun等)があればまとめて停止する
    try:
      os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
      pass
    proc.poll()
    with self.lock_procs:
      self.procs_running.discard(proc)


  def terminate_subprocesses(self):
    with self.lock_procs:
      procs = list(self.procs_running)
    for proc in procs:
      self.kill_subprocess(proc)


  def wait_file(self, filename, proc):
    # 外部コードの出力ファイルを待つ。ファイルが出る前にプロセスが終了した場合は失敗とする
    while not os.path.exists(filename):
      if proc.poll() is not None:
        return os.path.exists(filename)
      time.sleep(self.polling_interval)
    return True


  def wait_subprocess(self, proc, work_dir_case):
    # 次のケースが同じCPUコアを使うため、slotを返す前に終了を待つ
    try:
      proc.wait(timeout=self.timeout_finalize)
    except subprocess.TimeoutExpired:
      print(f'[ShapeOpt-Borealis] Warning: Subprocess did not finish within {self.timeout_finalize} s and was killed: {work_dir_case}')
    self.kill_subprocess(proc)


  def objective_function(self, parameter_opt, *args):

    # args[0]: 粒子ID
    # args[1]: 最適化ステップ
    # args[2]: 目的関数を最大化するか最小化するか
    if not args:
      with self.lock_counter:
        pid  = self.pid
        step = self.step
        self.pid  += 1
        self.step += 1
      sign_of = 1.0
    else:
      pid = args[0]
      step = args[1]
      sign_of = args[2]

    print('[ShapeOpt-Borealis] Iteration: ', pid)

    # Case directory and file names
    if self.in_sequential:
      # 粒子ごとの常駐ケース。ステップごとにファイル名の末尾を変える
      slot = (pid - 1) % self.num_particle
      work_dir_case = self.work_dir + '/' + self.case_dir + '_rank' + str(slot+1).zfill(self.step_digit)
      suffix_series = f"_step{step:0{self.step_digit_series}d}"
      if step == 0:
        print('[ShapeOpt-Borealis] --Make case directory: ', work_dir_case)
        shutil.copytree(self.work_dir_template, work_dir_case)
    else:
      work_dir_case = self.work_dir + '/' + self.case_dir + '_rank' + str(pid).zfill(self.step_digit)
      suffix_series = ''
      print('[ShapeOpt-Borealis] --Make case directory: ', work_dir_case)
      shutil.copytree(self.work_dir_template, work_dir_case)

    filename_displacements_series = self.get_filename_series(work_dir_case, self.work_dir_series, self.displacements_file, suffix_series)
    filename_forces_series        = self.get_filename_series(work_dir_case, self.work_dir_series, self.forces_file, suffix_series)
    if self.flag_surfacearea_constraint:
      filename_surfacearea_series = self.get_filename_series(work_dir_case, self.work_dir_surfacearea, self.filename_surfacearea, suffix_series)

    # Write displacements file (shapeoptimizer_preCICEは起動直後に読み込むため、起動前に書く)
    displacements = parameter_opt.reshape(self.num_marker, self.num_dim)
    self.write_displacements(filename_displacements_series, displacements)
    print(f"[ShapeOpt-Borealis] PID {pid} and Step {step+1}: Wrote {filename_displacements_series}\n", f"Displacements: {displacements[1,:]}..{displacements[-1,:]}")

    # Run external code and get forces data
    if self.in_sequential:
      if step == 0:
        self.proc_sequential[slot] = self.run_code(work_dir_case, slot)
      proc = self.proc_sequential[slot]
      flag_success = self.wait_file(filename_forces_series, proc)
      if flag_success:
        # 常駐プロセスが書き込み中の可能性があるため、読めるまで再試行する
        for n in range(0, 10):
          try:
            forces_marker, moments_marker = self.read_forces_marker(filename_forces_series)
            break
          except (IndexError, ValueError):
            time.sleep(0.5)
        else:
          flag_success = False
    else:
      slot = self.queue_slot.get()
      try:
        proc = self.run_code(work_dir_case, slot)
        flag_success = self.wait_file(filename_forces_series, proc)
        self.wait_subprocess(proc, work_dir_case)
      finally:
        self.queue_slot.put(slot)
      if flag_success:
        forces_marker, moments_marker = self.read_forces_marker(filename_forces_series)

    if not flag_success:
      print(f"[ShapeOpt-Borealis] Error: PID {pid} and Step {step+1}: {filename_forces_series} was not obtained. See {work_dir_case}/log_subprocess")
      return np.full(self.num_objectives, self.penalty_failure)
    print(f"[ShapeOpt-Borealis] PID {pid} and Step {step+1}: Read {filename_forces_series}\n", f"Forces and Moments: {forces_marker} {moments_marker} ")

    # Penalty
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
    if np.ndim(penalty) > 0:
      penalty = np.asarray(penalty)[:self.num_objectives]
    error = sign_of * np.array([ forces_marker[0], moments_marker[0] ])[:self.num_objectives] + penalty

    return np.atleast_1d(error).astype(float)


  def get_filename_series(self, work_dir_case, sub_dir, filename, suffix):
    base, ext = os.path.splitext(filename)
    return f"{work_dir_case}/{sub_dir}/{base}{suffix}{ext}"
