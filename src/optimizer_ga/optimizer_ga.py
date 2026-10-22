#!/usr/bin/env python3

# 遺伝的アルゴリズム (GA)。実数値の GA を NSGA-II の世代交代で回す。
#   - 選択: 2 個体のトーナメント（非劣解の順位、同じなら混雑距離の大きいほう）
#   - 交叉: SBX (simulated binary crossover; Deb and Agrawal, 1995)
#   - 突然変異: 多項式突然変異 (polynomial mutation; Deb and Goyal, 1996)
#   - 世代交代: 親と子を合わせた 2N 個から、非劣解の順位と混雑距離で N 個を残す (NSGA-II; Deb et al., 2002)
# 単目的では、これは最良の個体が必ず残る (mu + lambda) のエリート保存の GA になる。
# 1 世代に評価するのは子の N 個だけ（親の値は持ち越す）。
#
# MPI では、遺伝的な操作は rank 0 だけが行って全ランクに配り、評価だけを分担する
# （ランクごとに乱数の種が違っても、全ランクの集団が一致するように）。
# 1.6 までの GA は試作のまま borealis.py で外してあった。これはそれを置き換えたもの。

import numpy as np
from concurrent.futures import ThreadPoolExecutor
from orbital.orbital import orbital


class optimizer_ga(orbital):

  def __init__(self,mpi_instance):

    print("Constructing class: GA")

    self.mpi_instance = mpi_instance

    self.str_num_generation = 'number_generation'
    self.str_residual       = 'residual'
    self.str_population     = 'population'
    self.str_error          = 'solution'
    self.str_id             = 'id'
    self.str_rank           = 'rank'
    self.str_front_id       = 'front_id'
    self.str_front_position = 'front_position'
    self.str_front_score    = 'front_score'

    self.text_color = '\033[96m'
    self.text_end = '\033[0m'

    return


  def initial_setting(self, config):

    if self.mpi_instance.rank == 0:
      result_dir = config['GA']['result_dir']
      super().make_directory_rm(result_dir)
    if self.mpi_instance.flag_mpi :
      self.mpi_instance.comm.Barrier()

    boundary = config['parameter_optimized']['boundary']
    parameter_name_list = []
    for n in range(0, len(boundary) ):
      parameter_component = boundary[n]['component']
      for m in range(0, len(parameter_component)):
        parameter_name_list.append( parameter_component[m]['type'] )

    self.num_dimension = len(parameter_name_list)
    self.parameter_name_list = parameter_name_list

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


  # ---------------------------------------------------------------------------
  # NSGA-II の道具（支配・非劣解ソート・混雑距離は orbital にあり、ABC と共有する）
  # ---------------------------------------------------------------------------
  def environmental_selection(self, scores, num_select):
    # 順位の小さい順、同じ順位では混雑距離の大きい順に num_select 個を選ぶ
    rank = self.non_dominated_sort(scores)
    distance = self.crowding_distance(scores, rank)
    order = np.lexsort( (-distance, rank) )
    return order[:num_select]


  def tournament(self, rank, distance, tournament_size):
    candidate = np.random.choice(len(rank), size=tournament_size, replace=False)
    best = candidate[0]
    for c in candidate[1:]:
      if rank[c] < rank[best] or (rank[c] == rank[best] and distance[c] > distance[best]):
        best = c
    return best


  # ---------------------------------------------------------------------------
  # 実数値の交叉と突然変異（範囲つき）
  # ---------------------------------------------------------------------------
  def crossover_sbx(self, parent1, parent2, lower, upper, eta):
    # SBX: 成分ごとに確率 0.5 で、親の広がりに応じた分布から子を作る（範囲つきの形）
    child1 = parent1.copy()
    child2 = parent2.copy()
    for k in range(len(parent1)):
      if np.random.rand() > 0.5 or abs(parent1[k] - parent2[k]) < 1.0e-14:
        continue
      y1, y2 = min(parent1[k], parent2[k]), max(parent1[k], parent2[k])
      yl, yu = lower[k], upper[k]
      rand = np.random.rand()
      beta = 1.0 + 2.0*(y1 - yl)/(y2 - y1)
      alpha = 2.0 - beta**(-(eta + 1.0))
      betaq = (rand*alpha)**(1.0/(eta + 1.0)) if rand <= 1.0/alpha else (1.0/(2.0 - rand*alpha))**(1.0/(eta + 1.0))
      c1 = 0.5*((y1 + y2) - betaq*(y2 - y1))
      beta = 1.0 + 2.0*(yu - y2)/(y2 - y1)
      alpha = 2.0 - beta**(-(eta + 1.0))
      betaq = (rand*alpha)**(1.0/(eta + 1.0)) if rand <= 1.0/alpha else (1.0/(2.0 - rand*alpha))**(1.0/(eta + 1.0))
      c2 = 0.5*((y1 + y2) + betaq*(y2 - y1))
      c1 = min(max(c1, yl), yu)
      c2 = min(max(c2, yl), yu)
      if np.random.rand() <= 0.5:
        c1, c2 = c2, c1
      child1[k], child2[k] = c1, c2
    return child1, child2


  def mutation_polynomial(self, individual, lower, upper, rate, eta):
    # 多項式突然変異: 成分ごとに確率 rate で、範囲の内側に少しずらす
    child = individual.copy()
    for k in range(len(child)):
      if np.random.rand() >= rate:
        continue
      y, yl, yu = child[k], lower[k], upper[k]
      if yu - yl <= 0.0:
        continue
      delta1 = (y - yl)/(yu - yl)
      delta2 = (yu - y)/(yu - yl)
      rand = np.random.rand()
      power = 1.0/(eta + 1.0)
      if rand < 0.5:
        value = 2.0*rand + (1.0 - 2.0*rand)*(1.0 - delta1)**(eta + 1.0)
        deltaq = value**power - 1.0
      else:
        value = 2.0*(1.0 - rand) + 2.0*(rand - 0.5)*(1.0 - delta2)**(eta + 1.0)
        deltaq = 1.0 - value**power
      child[k] = min(max(y + deltaq*(yu - yl), yl), yu)
    return child


  def make_offspring(self, population, scores, num_offspring, lower, upper, setting):
    rank = self.non_dominated_sort(scores)
    distance = self.crowding_distance(scores, rank)
    offspring = []
    while len(offspring) < num_offspring:
      parent1 = population[ self.tournament(rank, distance, setting['tournament_size']) ]
      parent2 = population[ self.tournament(rank, distance, setting['tournament_size']) ]
      if np.random.rand() < setting['crossover_rate']:
        child1, child2 = self.crossover_sbx(parent1, parent2, lower, upper, setting['eta_crossover'])
      else:
        child1, child2 = parent1.copy(), parent2.copy()
      offspring.append( self.mutation_polynomial(child1, lower, upper, setting['mutation_rate'], setting['eta_mutation']) )
      offspring.append( self.mutation_polynomial(child2, lower, upper, setting['mutation_rate'], setting['eta_mutation']) )
    return np.array(offspring[:num_offspring])


  # ---------------------------------------------------------------------------
  # 本体
  # ---------------------------------------------------------------------------
  def run_optimizer_ga(self, config, objective_function, parameter_boundary):

    setting_ga = config['GA']
    num_objectives = config.get('objectives', {}).get('num_objectives', 1)
    num_generation = int( setting_ga['num_generation'] )
    num_population = int( setting_ga['num_population'] )
    num_dimension = self.num_dimension
    if num_population < 4:
      super().stop_program('[GA-Borealis] Error: GA.num_population must be 4 or more', self.mpi_instance)

    setting = {
      'tournament_size': int( setting_ga.get('tournament_size', 2) ),
      'crossover_rate':  float( setting_ga.get('crossover_rate', 0.9) ),
      'eta_crossover':   float( setting_ga.get('eta_crossover', 15.0) ),
      'mutation_rate':   float( setting_ga.get('mutation_rate', 1.0/num_dimension) ),
      'eta_mutation':    float( setting_ga.get('eta_mutation', 20.0) ),
    }
    windowsize_residual = int( setting_ga.get('windowsize_residual', 20) )
    tolerance_residual  = float( setting_ga.get('tolerance_residual', 1.0e-5) )

    # Maximization or minimization of the objective function (PSO と同じ仕組み。符号を掛けるのはアダプタ)
    flag_maximize = setting_ga.get('maximize', False)
    if isinstance(flag_maximize, list):
      if len(flag_maximize) != num_objectives:
        raise ValueError(f"[GA-Borealis] Error: GA.maximize has {len(flag_maximize)} entries, but objectives.num_objectives is {num_objectives}")
      sign_of = np.array([-1.0 if f else 1.0 for f in flag_maximize])
    elif isinstance(flag_maximize, bool):
      sign_of = -1.0 if flag_maximize else 1.0
    else:
      raise ValueError("[GA-Borealis] Error: config['GA']['maximize'] must be True/False or a list.")
    super().check_maximize_supported(objective_function, flag_maximize, 'GA', self.mpi_instance)
    value_nonfinite = float( config['parameter_optimized'].get('value_nonfinite', 1.0e+30) )

    lower = np.array([ b[0] for b in parameter_boundary ], dtype=float)
    upper = np.array([ b[1] for b in parameter_boundary ], dtype=float)

    # MPI と並列評価
    flag_mpi = self.mpi_instance.flag_mpi
    rank_mpi = self.mpi_instance.rank
    if flag_mpi:
      comm = self.mpi_instance.comm
      size = self.mpi_instance.size
      if num_population < size:
        super().stop_program(f'[GA-Borealis] Error: GA.num_population ({num_population}) is smaller than the number of processes ({size})', self.mpi_instance)
      indices_per_proc = np.array_split( np.arange(num_population), size )
      my_indices = indices_per_proc[rank_mpi]
    else:
      my_indices = np.arange(num_population)

    num_parallel = int( setting_ga.get('num_parallel', 1) )
    if num_parallel > 1:
      adapter_instance = getattr(objective_function, '__self__', None)
      if not getattr(adapter_instance, 'flag_parallel_evaluation', False):
        super().stop_program(f'[GA-Borealis] Error: GA.num_parallel > 1 is not supported by the selected adapter: {type(adapter_instance).__name__}', self.mpi_instance)
      print(f'[GA-Borealis] Number of concurrent evaluations: {num_parallel}')
      executor = ThreadPoolExecutor(max_workers=num_parallel)
    else:
      executor = None

    def evaluate_population(candidates, generation):
      # 評価の番号は PSO と同じく generation*N + i + 1
      def evaluate(i):
        score = objective_function( candidates[i].reshape(1, num_dimension), generation*num_population + i + 1, generation, sign_of )
        return self.sanitize_score( score, num_objectives, value_nonfinite, 'GA' )
      if executor is None:
        local = [ evaluate(i) for i in my_indices ]
      else:
        local = list( executor.map(evaluate, my_indices) )
      if flag_mpi:
        gathered = comm.allgather( list(zip(my_indices, local)) )
        result = [None]*num_population
        for part in gathered:
          for i, score in part:
            result[i] = score
        return np.array(result)
      return np.array(local)

    # 初期集団（rank 0 が作って配る）
    if rank_mpi == 0:
      population = np.random.uniform(lower, upper, size=(num_population, num_dimension))
    else:
      population = None
    if flag_mpi:
      population = comm.bcast(population, root=0)
    scores = evaluate_population(population, 0)
    ids = np.arange(num_population) + 1

    # History（各世代の集団。0 は初期集団）
    population_history = [ population.copy() ]
    score_history = [ scores.copy() ]
    id_history = [ ids.copy() ]
    rank_history = [ self.non_dominated_sort(scores) ]
    residual_history = [ 1.0 ]
    mean_score_history = [ np.mean(scores, axis=0) ]
    residual_init = None
    num_generation_optimized = num_generation

    for n in range(1, num_generation + 1):
      # 子を作る（rank 0 が作って配る）
      if rank_mpi == 0:
        offspring = self.make_offspring(population, scores, num_population, lower, upper, setting)
      else:
        offspring = None
      if flag_mpi:
        offspring = comm.bcast(offspring, root=0)
      offspring_scores = evaluate_population(offspring, n)
      offspring_ids = n*num_population + np.arange(num_population) + 1

      # 親と子を合わせて N 個を残す（全ランクで同じ計算。乱数は使わない）
      merged_population = np.vstack( [population, offspring] )
      merged_scores = np.vstack( [scores, offspring_scores] )
      merged_ids = np.concatenate( [ids, offspring_ids] )
      selected = self.environmental_selection(merged_scores, num_population)
      population, scores, ids = merged_population[selected], merged_scores[selected], merged_ids[selected]
      rank_population = self.non_dominated_sort(scores)

      population_history.append( population.copy() )
      score_history.append( scores.copy() )
      id_history.append( ids.copy() )
      rank_history.append( rank_population )

      # 収束の判定: 集団の値の平均の、windowsize_residual 世代前からの相対変化
      mean_score_history.append( np.mean(scores, axis=0) )
      residual = 1.0
      if n >= windowsize_residual:
        residual = np.linalg.norm( mean_score_history[-1] - mean_score_history[-1-windowsize_residual] ) \
                   / ( np.linalg.norm(mean_score_history[0]) + 1.0e-15 )
        if residual_init is None:
          residual_init = residual
      residual_history.append( residual )

      if rank_mpi == 0:
        best_text = f'{np.min(scores[:, 0]):.10e}' if num_objectives == 1 else f'front size {int(np.sum(rank_population == 0))}'
        print('[GA-Borealis] Generation:', n, ', Best:', best_text, ', Residual:', self.text_color + f'{residual:.10e}' + self.text_end)

      if residual_init is not None and residual <= tolerance_residual and abs(residual - residual_init) > 1.0e-15:
        num_generation_optimized = n
        break

    if executor is not None:
      executor.shutdown()

    # 第 1 フロント（単目的なら最良の 1 個）の履歴
    front_id, front_position, front_score = [], [], []
    for n in range(len(population_history)):
      front = np.where(rank_history[n] == 0)[0]
      if num_objectives == 1:
        front = front[ np.argsort(score_history[n][front, 0], kind='stable')[:1] ]
      front_id.append( id_history[n][front] )
      front_position.append( population_history[n][front] )
      front_score.append( score_history[n][front] )

    if rank_mpi == 0:
      print("[GA-Borealis] Final front:")
      for i, x, f in zip(front_id[-1], front_position[-1], front_score[-1]):
        print(f"--ID: {i}, Parameter: {x}, Solution: {f}")

    solution_dict = {
      self.str_num_generation: num_generation_optimized,
      self.str_residual:       residual_history,
      self.str_population:     population_history,
      self.str_error:          score_history,
      self.str_id:             id_history,
      self.str_rank:           rank_history,
      self.str_front_id:       front_id,
      self.str_front_position: front_position,
      self.str_front_score:    front_score,
    }
    return solution_dict


  def write_optimization_process(self, config, solution_dict):

    # 各世代の集団（0 は初期集団）: パラメータ、番号、目的関数の値、非劣解の順位、残差
    num_objectives = config.get('objectives', {}).get('num_objectives', 1)
    filename_tmp = config['GA']['result_dir'] + '/' + config['GA']['filename_output']
    print('[GA-Borealis] Writing output file...:', filename_tmp)

    header_tmp = "Variables="
    for name in self.parameter_name_list:
      header_tmp = header_tmp + name + ','
    header_tmp = header_tmp + ' ID,'
    for k in range(num_objectives):
      header_tmp = header_tmp + ' Error_' + str(k+1) + ','
    header_tmp = header_tmp + ' Rank, Residual_mean\n'

    with open(filename_tmp, 'w') as file_output:
      file_output.write(header_tmp)
      for n in range(len(solution_dict[self.str_population])):
        population = solution_dict[self.str_population][n]
        text_tmp = 'zone t="Generation' + str(n) + '"\n' + 'i=' + str(len(population)) + ' f=point\n'
        for i in range(len(population)):
          text_tmp = text_tmp + ', '.join( str(x) for x in population[i] ) + ', '
          text_tmp = text_tmp + str(solution_dict[self.str_id][n][i]) + ', '
          text_tmp = text_tmp + ', '.join( str(f) for f in solution_dict[self.str_error][n][i] ) + ', '
          text_tmp = text_tmp + str(solution_dict[self.str_rank][n][i]) + ', ' + str(solution_dict[self.str_residual][n]) + '\n'
        file_output.write(text_tmp)

    return


  def write_best_solution_history(self, config, solution_dict):

    # 各世代の第 1 フロント（単目的では最良）: PSO の output_global.dat と同じ形
    num_objectives = config.get('objectives', {}).get('num_objectives', 1)
    filename_tmp = config['GA']['result_dir'] + '/' + config['GA']['filename_global']
    print('[GA-Borealis] Writing front history file...:', filename_tmp)

    obj_header = ', '.join( f'Objective{k+1}' for k in range(num_objectives) )
    param_header = ', '.join( f'Parameter{n+1}' for n in range(self.num_dimension) )
    with open(filename_tmp, 'w') as file_output:
      file_output.write(f'Variables = Step, Pareto_ID, {obj_header}, {param_header}\n')
      for n in range(len(solution_dict[self.str_front_id])):
        for i, x, f in zip(solution_dict[self.str_front_id][n], solution_dict[self.str_front_position][n], solution_dict[self.str_front_score][n]):
          line = f'{n}, {i}, ' + ', '.join( str(v) for v in f )
          for value in x:
            line += f', {value}'
          file_output.write(line + '\n')

    return


  def drive_optimization(self, config, objective_function, parameter_boundary):

    solution_dict = self.run_optimizer_ga(config, objective_function, parameter_boundary)

    if self.mpi_instance.rank == 0:
      self.write_optimization_process(config, solution_dict)

    if self.mpi_instance.rank == 0:
      self.write_best_solution_history(config, solution_dict)

    return
