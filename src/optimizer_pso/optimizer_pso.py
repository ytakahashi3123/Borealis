#!/usr/bin/env python3

import numpy as np
from orbital.orbital import orbital


class optimizer_pso(orbital):

  def __init__(self, mpi_instance):

    print("Constructing class: PSO")

    self.mpi_instance = mpi_instance

    self.str_num_optiter = 'number_iteration'
    self.str_residual = 'residual_hisotry'
    self.str_position = 'position'
    self.str_velocity = 'velocity'
    self.str_error = 'error'
    self.str_archive_id = 'archive_id'
    self.str_archive_position = 'archive_position'
    self.str_archive_score = 'archive_score'
    self.str_archive_size = 'archive_size'

    self.text_color = '\033[96m'
    self.text_end = '\033[0m'

    return


  def initial_setting(self, config):

    if self.mpi_instance.rank == 0:
      result_dir = config['PSO']['result_dir']
      super().make_directory_rm(result_dir)
    if self.mpi_instance.flag_mpi :
      self.mpi_instance.comm.Barrier()

    boundary = config['parameter_optimized']['boundary']
    num_dimension = 0
    parameter_name_list = []
    for n in range(0, len(boundary) ):
      parameter_component = boundary[n]['component']
      for m in range(0, len(parameter_component)):
        parameter_name_list.append( parameter_component[m]['type'] )
        num_dimension = num_dimension + 1

    self.num_dimension = num_dimension
    self.parameter_name_list = parameter_name_list

    # Parameter boundary at initial step
    try:
      self.boundary_initial = config['parameter_optimized']['boundary_initial']
      self.flag_boundary_initial = True
    except (KeyError):
      self.flag_boundary_initial = False

    # Parameter velocity at initial step
    try:
      self.velocity_initial = config['parameter_optimized']['velocity_initial']
      self.flag_velocity_initial = True
    except (KeyError):
      self.flag_velocity_initial = False

    # Kind of computation of redisuals
    self.kind_residual_computation = ( config.get('PSO', {}).get('kind_residual_computation', 'relative_change') )
    print(f'[PSO-Borealis] Residual computation: {self.kind_residual_computation}')

    return


  def boundary_setting(self, config):
    # Setting parameter's boundaries
    boundary = config['parameter_optimized']['boundary']
    parameter_boundary = []
    for n in range(0, len(boundary) ):
      parameter_component = boundary[n]['component']
      for m in range(0, len(parameter_component)):
        parameter_boundary.append( (parameter_component[m]['bound_min'],parameter_component[m]['bound_max']) )
    return parameter_boundary


  # For multi-objective optimization
  def dominates(self, a, b):
    return np.all(a <= b) and np.any(a < b)

  def update_archive(self, num_objectives, ids, positions, scores):
    #　全履歴・全粒子から最も良いものを探すのか良いのか、１世代・全粒子からが良いのか（今回は後者とした）
#    all_ids = self.ids + list(ids)
#    all_positions = self.archive_positions + list(positions)
#    all_scores = self.archive_scores + list(scores)
    all_ids = list(ids)
    all_positions = list(positions)
    all_scores = list(scores)
    if num_objectives == 1:
      ids_best = np.argmin([ np.atleast_1d(s)[0] for s in all_scores ])
      archive_ids = [all_ids[ids_best]]
      archive_positions = [ np.array(all_positions[ids_best]).copy() ]
      archive_scores = [ np.array(all_scores[ids_best]).copy() ]
    else:
      archive_ids = []
      archive_positions = []
      archive_scores = []
      for i, score_i in enumerate(all_scores):
        dominated = False
        for j, score_j in enumerate(all_scores):
          if i != j and self.dominates(score_j, score_i):
            dominated = True
            break
        if not dominated:
          archive_ids.append(all_ids[i])
          archive_positions.append(np.array(all_positions[i]))
          archive_scores.append(np.array(score_i))
    return archive_ids, archive_positions, archive_scores

  def select_global_best(self, archive_positions,archive_scores):
    #if len(archive_scores[0]) == 1:
    #    idx = np.argmin([ s[0] for s in archive_scores ])
    #    return archive_positions[idx]
    idx = np.random.randint( len(archive_positions) )
    return archive_positions[idx]
  
  def select_global_best_cd(self, archive_positions, archive_scores):
    if len(archive_scores[0]) == 1:
      idx = np.argmin([s[0] for s in archive_scores])
      return archive_positions[idx]
    distance = self.crowding_distance(archive_scores)
    idx = np.argmax(distance)
    return archive_positions[idx]

  def crowding_distance(self, scores):
    # パレートフロントの疎な領域にある解を優先して leader に選ぶ
    scores = np.array(scores)
    n_points = len(scores)
    n_obj = scores.shape[1]
    distance = np.zeros(n_points)
    for m in range(n_obj):
      idx = np.argsort(scores[:, m])
      distance[idx[0]] = np.inf
      distance[idx[-1]] = np.inf
      f_min = scores[idx[0], m]
      f_max = scores[idx[-1], m]
      if abs(f_max - f_min) < 1e-15:
        continue
      for i in range(1, n_points - 1):
        distance[idx[i]] += (scores[idx[i+1], m] - scores[idx[i-1], m]) / (f_max - f_min)
    return distance

  # PSO routine
  def run_pso(self, config, objective_function, parameter_boundary):

    # Number of objectives
    num_objectives = config.get('objectives', {}).get('num_objectives', 1)
    # Dimension 
    num_dimension = self.num_dimension
    # Number of particles
    num_particle = config['PSO']['num_particle']
    # Number of iteration
    num_optiter = config['PSO']['num_optiter']
    # Actural number of iteration after optimization
    num_optiter_optimized = num_optiter

    # Convergence parameters for single/multi-objective optimization
    windowsize_residual = int( config['PSO'].get('windowsize_residual',20) )
    tolerance_residual  = float( config['PSO'].get('tolerance_residual',1e-5) )
    windowsize_archive  = int( config['PSO'].get('windowsize_archive',5) )
    tolerance_archive   = float( config['PSO'].get('tolerance_archive',1.0) )
    
    # Particle parameters
    inertia        = config['PSO']['inertia']
    cognitive_coef = config['PSO']['cognitive_coef']
    social_coef    = config['PSO']['social_coef']

    # Maximization or minimization of the objective function
    #flag_Maximization_of = config['PSO']['maximize']
    #if not isinstance(flag_Maximization_of, bool):
    #  raise ValueError("[PSO-Borealis] Error: config['PSO']['maximize'] must be True or False.")
    #sign_of = -1.0 if flag_Maximization_of else 1.0
    flag_Maximization_of = config['PSO']['maximize']
    if isinstance(flag_Maximization_of, list):
      sign_of = np.array([-1.0 if f else 1.0 for f in flag_Maximization_of])
    elif isinstance(flag_Maximization_of, bool):
      sign_of = -1.0 if flag_Maximization_of else 1.0
    else:
      raise ValueError("[PSO-Borealis] Error: config['PSO']['maximize'] must be True/False or a list.")

    # MPI settings
    flag_mpi = self.mpi_instance.flag_mpi
    if flag_mpi :
      MPI = self.mpi_instance.MPI
      comm = self.mpi_instance.comm
      size = self.mpi_instance.size
      rank = self.mpi_instance.rank
      particle_size = num_particle // size
      num_particle_start = rank * particle_size
      num_particle_end   = (rank + 1) * particle_size if rank < size - 1 else num_particle
      print(f'[PSO-Borealis] Rank: {rank}, Iter_start: {num_particle_start}, Iter_zend: {num_particle_end}')
    else :
      rank = 0
      num_particle_start = 0
      num_particle_end = num_particle

    # Initialize particles
    particle_position = []
    particle_velocity = []
    particle_best_position = []
    particle_best_score = []
    particle_best_score_history = []

    archive_ids = []
    archive_positions = []
    archive_scores = []

    # ループ前に初期残差を保存する変数を用意
    residual_mean_init = None 

    # Initial settings
    for n in range(0, num_particle):
      # Positions
      if self.flag_boundary_initial :
        low  = self.boundary_initial['bound_min']
        high = self.boundary_initial['bound_max']
        position_tmp = []
        for m in range(0,len(parameter_boundary)):
          position_tmp.append( np.random.uniform(low, high) )
        position_tmp = np.array( position_tmp )
      else :
        position_tmp = np.array( [np.random.uniform(low, high) for low, high in parameter_boundary] )
      
      # Velocities
      if self.flag_velocity_initial :
        low  = self.velocity_initial['velocity_min']
        high = self.velocity_initial['velocity_max']
        velocity_tmp = np.array( [np.random.uniform(low, high) for _ in range(num_dimension)] )
      else :
        velocity_tmp = np.array( [np.random.uniform(-1.0, 1.0) for _ in range(num_dimension)] )

      particle_position.append( position_tmp )
      particle_velocity.append( velocity_tmp )
      particle_best_position.append( position_tmp.copy() )
      particle_best_score.append( np.full(num_objectives, np.inf) )

    # History variables
    archive_id_history = []
    archive_position_history = []
    archive_score_history = []
    archive_size_history = []

    particle_position_history = np.zeros(num_optiter*num_particle*num_dimension).reshape(num_optiter,num_particle,num_dimension)
    particle_velocity_history = np.zeros(num_optiter*num_particle*num_dimension).reshape(num_optiter,num_particle,num_dimension)
    particle_solution = np.zeros( (num_optiter, num_particle, num_objectives) )

    # For residual
    residual_mean_history = []
    #archive_score_mean_prev = np.zeros(1)

    for n in range(0, num_optiter):
      local_ids = []
      local_positions = []
      local_scores = []
      leader_position = None
      
      for i in range(num_particle_start, num_particle_end):
        # パーソナルベストの更新: 下記のreshape追加の理由、Bayesian Optの引数が(1,dim)の次元になるので、それに合わせている。
        id_serial = n*num_particle + i + 1
        score = objective_function( particle_position[i].reshape(1, num_dimension), id_serial, n, sign_of )

        particle_solution[n,i,:] = score
        if self.dominates(score, particle_best_score[i]):
          particle_best_position[i] = particle_position[i].copy()
          particle_best_score[i] = score.copy()

        local_ids.append( id_serial )
        local_positions.append( particle_position[i].copy() )
        local_scores.append( score.copy() )

      # Global best with MPI process
      if flag_mpi:
        gathered_positions = comm.gather( local_positions, root=0 )
        gathered_scores = comm.gather( local_scores, root=0 )
        gathered_ids = comm.gather(local_ids, root=0)

        if rank == 0:
          all_positions = []
          all_scores = []
          all_ids = []
          for p in gathered_positions:
            all_positions.extend(p)
          for s in gathered_scores:
            all_scores.extend(s)
          for d in gathered_ids:
            all_ids.extend(d)
          archive_ids, archive_positions, archive_scores = self.update_archive( num_objectives, all_ids, all_positions, all_scores)
          leader_position = self.select_global_best(archive_positions,archive_scores)
          #leader_position = self.select_global_best_cd(archive_positions,archive_scores)
        else:
          archive_ids = None
          archive_positions = None
          archive_scores = None
          leader_position = None

        archive_ids = comm.bcast(archive_ids, root=0)
        archive_positions = comm.bcast(archive_positions, root=0)
        archive_scores = comm.bcast(archive_scores, root=0)
        leader_position = comm.bcast(leader_position, root=0 )
      else:
        archive_ids, archive_positions, archive_scores = self.update_archive( num_objectives, local_ids, local_positions, local_scores)
        leader_position = self.select_global_best(archive_positions,archive_scores)
        #leader_position = self.select_global_best_cd(archive_positions,archive_scores)
      
      # History
      archive_id_history.append( np.array(archive_ids).copy() )
      archive_position_history.append( np.array(archive_positions).copy() )
      archive_score_history.append( np.array(archive_scores).copy() )
      archive_size_history.append( len(archive_positions) )

      # パーティクルの速度の更新
      for i in range(num_particle_start, num_particle_end):
        particle_velocity_history[n,i,:] = particle_velocity[i][:]
        particle_position_history[n,i,:] = particle_position[i][:]
        # Update position and velocity of particle for next step
        rand1 = np.random.rand(num_dimension)
        rand2 = np.random.rand(num_dimension)
        cognitive_velocity = cognitive_coef * rand1 * ( particle_best_position[i] - particle_position[i] )
        social_velocity = social_coef * rand2 * ( leader_position - particle_position[i] )
        particle_velocity[i] = inertia * particle_velocity[i] + cognitive_velocity + social_velocity
        particle_position[i] = particle_position[i] + particle_velocity[i]


      # Residual of objective function
      # --Initialize residual reference values at first iteration
      #if n == 0: 
      #  particle_best_score_init = [ np.atleast_1d(score).copy() for score in particle_best_score ]
      #  particle_best_score_prev = [ np.zeros(num_objectives) for _ in range(num_particle) ]
      particle_best_score_history.append( [np.atleast_1d(score).copy() for score in particle_best_score] )
      # --Compute swarm residual
      flag_residual = False
      residual_mean = 1.0
      #if n+1 >= windowsize_residual :
      if len(particle_best_score_history) >= windowsize_residual :
        current_pbest = particle_best_score_history[-1]
        old_pbest = particle_best_score_history[-windowsize_residual]
        residual = np.zeros(num_particle)
        for i in range(num_particle_start, num_particle_end):
          #numerator = np.linalg.norm(particle_best_score[i] - particle_best_score_prev[i])
          #denominator = np.linalg.norm(particle_best_score_init[i]) + 1.0e-15
          numerator = np.linalg.norm( current_pbest[i] - old_pbest[i] )
          #
          # 初期スコアのノルム->初期値がたまたま 0 に近いと分母が ε だけになり、残差が過大評価されて収束しにくくなる(多目的の場合、各目的関数のスケールが大きく異なると np.linalg.norm が大きい目的に引きずられる)
          denominator = np.linalg.norm( particle_best_score_history[0][i] ) + 1.0e-15
          #
          # 初期スコアのノルム->window内の平均スコアを基準にする
          #ref = np.mean([particle_best_score_history[-windowsize_residual + k][i] for k in range(windowsize_residual)], axis=0)
          #denominator = np.linalg.norm(ref) + 1e-15
          #
          residual[i] = numerator / denominator
        if flag_mpi:
          # 各ランクの分が合算されてしまう(ランク0以外の粒子分の残差は足し算されているだけで平均ではない。)
          #residual = comm.allreduce( residual, op=MPI.SUM)
          #residual_mean = np.mean(residual)
          # 各ランクの局所分のみ平均してからallreduce
          local_residual_sum = np.sum(residual[num_particle_start:num_particle_end])
          global_residual_sum = comm.allreduce(local_residual_sum, op=MPI.SUM)
          residual_mean = global_residual_sum / num_particle
        else:
          residual_mean = np.mean(residual)
        # 残差が初めて計算されたステップの値を保存
        if residual_mean_init is None:
          residual_mean_init = residual_mean

      residual_mean_history.append(residual_mean)
      # 収束判定：tolerance以下、かつ初期残差と同一でない
      if residual_mean_init is not None:
        is_not_initial = abs(residual_mean - residual_mean_init) > 1.0e-15
      else:
        is_not_initial = False
      #if residual_mean <= tolerance_residual:
      #  flag_residual = True
      if residual_mean <= tolerance_residual and is_not_initial:
        flag_residual = True

      # --Check archive stagnation
      flag_archive = False
      if num_objectives > 1:
        archive_change = 1.0
        # アーカイブのサイズだけで判定（アーカイブ内の解の位置やスコアの変化は無視している。サイズが安定していても、解の分布が動いていれば収束とは言えない）
        #if len(archive_size_history) >= windowsize_archive:
        #  recent_sizes = archive_size_history[-windowsize_archive:]
        #  range_size = max(recent_sizes) - min(recent_sizes)
        #  if range_size <= tolerance_archive:
        #    flag_archive = True
        #　アーカイブスコアの重心変化で判定
        if len(archive_score_history) >= windowsize_archive:
          centroid_now = np.mean(archive_score_history[-1], axis=0)
          centroid_old = np.mean(archive_score_history[-windowsize_archive], axis=0)
          archive_change = np.linalg.norm(centroid_now - centroid_old)
          if archive_change <= tolerance_archive:
            flag_archive = True

      # --Display residual
      if rank == 0:
        if num_objectives == 1:
          print('[PSO-Borealis] Step:', n+1, ', Swarm residual:', self.text_color + f'{residual_mean:.10e}' + self.text_end)
        else:
          print('[PSO-Borealis] Step:', n+1, ', Swarm residual:', self.text_color + f'{residual_mean:.10e}'  + self.text_end, 
                                             ', Archive change:', self.text_color + f'{archive_change:.10e}' + self.text_end)

      # --Convergence check
      if num_objectives == 1:
        # 単目的：残差のみで収束判定
        if flag_residual:
          num_optiter_optimized = n+1
          break
      else:
        # 多目的：残差 AND アーカイブ停滞
        if flag_residual and flag_archive:
          num_optiter_optimized = n+1
          break

    # MPI process for history data
    if flag_mpi :
      particle_position_history = comm.allreduce(particle_position_history, op=MPI.SUM)
      particle_velocity_history = comm.allreduce(particle_velocity_history, op=MPI.SUM)
      particle_solution         = comm.allreduce(particle_solution, op=MPI.SUM)

    # Display
    if rank == 0:
      print("[PSO-Borealis] Pareto history summary:")
      for n in range(0, num_optiter_optimized):
        print( f"[PSO-Borealis] Step:, {n+1}, Archive Size: {archive_size_history[n]} " )
        for j in range(0,archive_size_history[n]):
          print( f"--Pareto ID: {archive_id_history[n][j]}, Archive Score: {archive_score_history[n][j]}" )
      print("[PSO-Borealis] Final Pareto archive:")
      for j, (ids, pos, score) in enumerate( zip( archive_ids, archive_positions, archive_scores ) ):
        print( f"--Pareto ID: {ids}, " f"Parameter: {pos}, " f"Solution: {score}"  )

    # Store data
    solution_dict = {}
    solution_dict[self.str_num_optiter]  = num_optiter_optimized
    solution_dict[self.str_residual]     = residual_mean_history
    solution_dict[self.str_position]     = particle_position_history
    solution_dict[self.str_velocity]     = particle_velocity_history
    solution_dict[self.str_error]        = particle_solution
    solution_dict[self.str_archive_id] = archive_id_history
    solution_dict[self.str_archive_position] = archive_position_history
    solution_dict[self.str_archive_score] = archive_score_history
    solution_dict[self.str_archive_size] = archive_size_history

    return solution_dict


  def write_optimization_process(self, config, solution_dict):

    # Number of iteration
    num_optiter = solution_dict[self.str_num_optiter]
    # Number of particles
    num_particle = config['PSO']['num_particle']
    # Number of dimension
    num_dimension = self.num_dimension
    # Number of objectives
    num_objectives = config.get('objectives', {}).get('num_objectives', 1)

    # Parameter name list
    solution_name_list = self.parameter_name_list.copy()
    boundary = config['parameter_optimized']['boundary']
    for n in range(0, len(boundary)):
      parameter_component = boundary[n]['component']
      for m in range(0, len(parameter_component)):
        solution_name_list.append( parameter_component[m]['type'] + '_Velocity' )

    # Variables
    particle_position_history = solution_dict[self.str_position]
    particle_velocity_history = solution_dict[self.str_velocity]
    particle_solution         = solution_dict[self.str_error]
    residual_mean_history     = solution_dict[self.str_residual]

    # Optional: archive size history
    try:
      archive_size_history = solution_dict[self.str_archive_size]
      flag_archive_size = True
    except KeyError:
      flag_archive_size = False

    # Output results: Particles
    filename_tmp = ( config['PSO']['result_dir'] + '/' + config['PSO']['filename_output'] )
    print( '[PSO-Borealis] Writing output file...:', filename_tmp )
    file_output = open(filename_tmp, 'w')

    # Header
    header_tmp = "Variables="
    for n in range(0, len(solution_name_list)):
      header_tmp = header_tmp + solution_name_list[n] + ','
    # Addition
    header_tmp = header_tmp + ' ID,'
    for k in range(0, num_objectives):
      header_tmp = header_tmp + ' Error_' + str(k+1) + ','
    header_tmp = header_tmp + ' Residual_mean'
    # Optional archive size
    if flag_archive_size:
      header_tmp = header_tmp + ', Archive_size'
    header_tmp = header_tmp + '\n'
    file_output.write(header_tmp)

    for i in range(0, num_optiter):
      text_tmp = ( 'zone t="Time' + str(i+1) + ' sec"' + '\n' )
      text_tmp = ( text_tmp + 'i=' + str(num_particle) + ' f=point' + '\n' )
      for n in range(0, num_particle):
        text_tmp = text_tmp
        # Position
        for m in range(0, num_dimension):
          text_tmp = ( text_tmp + str(particle_position_history[i, n, m]) + ', ' )
        # Velocity
        for m in range(0, num_dimension):
          text_tmp = ( text_tmp + str(particle_velocity_history[i, n, m]) + ', ' )
        # Particle ID
        text_tmp = text_tmp + str(n+1) + ', '
        # Multi-objective error
        for k in range(0, num_objectives):
          text_tmp = ( text_tmp + str(particle_solution[i, n, k]) + ', ' )
        # Residual
        text_tmp = ( text_tmp + str(residual_mean_history[i]) )
        # Optional archive size
        if flag_archive_size:
          text_tmp = ( text_tmp + ', ' + str(archive_size_history[i]))
        text_tmp = text_tmp + '\n'
      file_output.write(text_tmp)
    file_output.close()

    return


  def write_best_solution_history(self, config, solution_dict):

    # Number of iteration
    num_optiter = solution_dict[self.str_num_optiter]
    # Number of particles
    num_particle = config['PSO']['num_particle']
    # Number of dimension
    num_dimension = self.num_dimension
    # Number of objectives
    num_objectives = config.get('objectives', {}).get('num_objectives', 1)

    # Variables
    archive_ids = solution_dict[ self.str_archive_id ]
    archive_positions = solution_dict[ self.str_archive_position ]
    archive_scores = solution_dict[ self.str_archive_score ]

    # Output results: Global particle information
    filename_tmp = ( config['PSO']['result_dir'] + '/' + config['PSO']['filename_global'] )
    print( '[PSO-Borealis] Writing Pareto history file...:', filename_tmp )

    with open(filename_tmp, 'w') as file_output:
      # Header
      obj_header = ', '.join( f'Objective{k+1}' for k in range(num_objectives) )
      param_header = ', '.join( f'Parameter{n+1}' for n in range(self.num_dimension) )
      header = f'Variables = Step, Pareto_ID, {obj_header}, {param_header}'
      file_output.write(header + '\n')

      for step in range( len(archive_scores) ):
        ids_step = archive_ids[step]
        scores_step = archive_scores[step]
        pos_step = archive_positions[step]
        for j in range( len(scores_step) ):
          score_text = ', '.join( str(score) for score in np.atleast_1d(scores_step[j]) )
          line = f'{step+1}, {ids_step[j]}, {score_text}'
          for x in pos_step[j]:
            line += f', {x}'
          file_output.write(line + '\n')

    return


  def drive_optimization(self, config, objective_function, parameter_boundary):

    solution_dict = self.run_pso(config, objective_function, parameter_boundary)

    if self.mpi_instance.rank == 0:
      self.write_optimization_process(config, solution_dict)

    if self.mpi_instance.rank == 0:
      self.write_best_solution_history(config, solution_dict)

    return

