#!/usr/bin/env python3

# 人工蜂コロニー (ABC; Karaboga, 2005)。雇用蜂・追従蜂・偵察蜂の 3 段で食料源（候補）を更新する。
# 目的が 2 つ以上 (objectives.num_objectives >= 2) のときは多目的 ABC にする:
#   - 食料源の採否: 候補が今の食料源を支配すれば置き換え、互いに支配しなければ確率 1/2 で置き換える
#   - 追従蜂の選択: 食料源の非劣解の順位 r（0 が第 1 フロント）から、適応度 1/(1+r) のルーレットで選ぶ
#   - 評価したすべての点から非劣解を外部アーカイブに集め、num_archive を超えたら混雑距離の小さいものから捨てる
# 単目的の動作は、多目的を入れる前と同じ（同じ乱数の種で同じ答え）。

import numpy as np
from concurrent.futures import ThreadPoolExecutor
from orbital.orbital import orbital


class optimizer_abc(orbital):

  def __init__(self,mpi_instance):

    print("Constructing class: ABC")

    self.mpi_instance = mpi_instance

    self.str_num_optiter = 'number_iteration'
    self.str_residual    = 'residual'
    self.str_food_source = 'food_source'
    self.str_error       = 'solution'
    self.str_best_index  = 'best_index'
    self.str_id_history  = 'ID_history'
    self.str_archive_id       = 'archive_id'
    self.str_archive_position = 'archive_position'
    self.str_archive_score    = 'archive_score'

    self.text_color = '\033[96m'
    self.text_end = '\033[0m'

    return


  def initial_setting(self, config):

    # ディレクトリ作成は Rank 0 のみ
    if self.mpi_instance.rank == 0:
      result_dir = config['ABC']['result_dir']
      super().make_directory_rm(result_dir)

    # 全プロセスがディレクトリ作成完了を待つ
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

    # 重要: 各プロセスで異なる乱数シードを設定する
    # これを忘れると、全プロセスが同じ場所を探索して並列化の意味がなくなる
    #np.random.seed(42 + self.mpi_instance.rank)

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


  def generate_food_source(self, parameter_boundary):
    #food_source = np.array( [np.random.uniform(low=bound_low, high=bound_high) for bound_low, bound_high in parameter_boundary] )
    food_source = np.array([np.random.uniform(low=b[0], high=b[1]) for b in parameter_boundary])
    return food_source


  def fitness_value_function(self, solutioin):
    # Solution: Solution of objective function
    if solutioin >= 0:
      fitness = 1.0/(1.0+solutioin)
    else: 
      fitness = 1.0+abs(solutioin)
    return fitness


  def reshape_array(self, var, num_dim):
    #下記のreshape追加の理由、Bayesian　Optの引数が(1,dim)の次元になるので、それに合わせている。
    return var.reshape(1,num_dim)


  def roulette_wheel_selection(self, fitness_values):
        total_fitness = sum(fitness_values)
        if total_fitness == 0:
            return np.random.randint(len(fitness_values))
        probs = [f / total_fitness for f in fitness_values]
        return np.random.choice(len(fitness_values), p=probs)


  def run_optimizer_abc(self, config, objective_function, parameter_boundary):

    if self.mpi_instance.flag_mpi :
    # MPI情報の取得
      MPI = self.mpi_instance.MPI
      rank = self.mpi_instance.rank
      size = self.mpi_instance.size
      comm = self.mpi_instance.comm
    else:
      rank = 0
      size = 1
      comm = 0

    # 設定の読み込み
    num_optiter = config['ABC']['num_optiter']
    num_employ_bees = config['ABC']['num_employ_bees']
    # 正しい綴りのキーも受け付ける（vist_limit・num_onlook_bee は誤った綴りのまま公式になっていた。既知の問題 4）
    num_onlook_bees = config['ABC'].get('num_onlook_bees', config['ABC'].get('num_onlook_bee'))
    visit_limit = config['ABC'].get('visit_limit', config['ABC'].get('vist_limit'))
    if num_onlook_bees is None or visit_limit is None:
      super().stop_program('[ABC-Borealis] Error: ABC.num_onlook_bees (num_onlook_bee) and ABC.visit_limit (vist_limit) are required', self.mpi_instance)
    # 収束判定で何ステップ前の解と比べるか（既定 1 = 前のステップ）
    windowsize_residual = int( config['ABC'].get('windowsize_residual', 1) )
    num_dimension = self.num_dimension

    # 目的の数。2 以上で多目的
    num_objectives = int( config.get('objectives', {}).get('num_objectives', 1) )
    flag_multi = num_objectives > 1

    # Maximization or minimization of the objective function (PSOと同様の仕組み。多目的では目的ごとのリストも可)
    flag_Maximization_of = config['ABC'].get('maximize', False)
    if isinstance(flag_Maximization_of, list):
      if len(flag_Maximization_of) != num_objectives:
        raise ValueError(f"[ABC-Borealis] Error: ABC.maximize has {len(flag_Maximization_of)} entries, but objectives.num_objectives is {num_objectives}")
      sign_of = np.array([-1.0 if f else 1.0 for f in flag_Maximization_of])
    elif isinstance(flag_Maximization_of, bool):
      sign_of = -1.0 if flag_Maximization_of else 1.0
    else:
      raise ValueError("[ABC-Borealis] Error: config['ABC']['maximize'] must be True/False or a list.")
    super().check_maximize_supported(objective_function, flag_Maximization_of, 'ABC', self.mpi_instance)

    # 多目的のアーカイブと収束判定
    num_archive        = int( config['ABC'].get('num_archive', 100) )
    windowsize_archive = int( config['ABC'].get('windowsize_archive', 5) )
    tolerance_archive  = float( config['ABC'].get('tolerance_archive', 0.0) )

    # 目的関数が NaN・無限大を返したときに置き換える値（既知の問題 2）
    value_nonfinite = float( config['parameter_optimized'].get('value_nonfinite', 1.0e+30) )
    def evaluate(x, unique_id, step):
      score = objective_function(self.reshape_array(x, num_dimension), unique_id, step, sign_of)
      return self.sanitize_score(score, num_objectives, value_nonfinite, 'ABC')

    def accept(sol_v, sol_i):
      # 候補 (値 sol_v) で食料源 (値 sol_i) を置き換えるか
      if not flag_multi:
        return self.fitness_value_function(sol_v[0]) > self.fitness_value_function(sol_i[0])
      if self.dominates(sol_v, sol_i):
        return True
      if self.dominates(sol_i, sol_v) or np.array_equal(sol_v, sol_i):
        return False
      # 互いに支配しない: 確率 1/2 で置き換える（どちらかに偏らないように）
      return np.random.rand() < 0.5

    # 多目的: このステップで評価した点 (ID, パラメータ, 値)。ステップの終わりにアーカイブへ入れる
    step_evaluations = []
    def record(candidates, results):
      if flag_multi:
        for (x, unique_id, step), sol in zip(candidates, results):
          step_evaluations.append( (int(unique_id), np.array(x, dtype=float), np.array(sol)) )

    # 1 プロセスの中で同時に評価する数（スレッド）。外部コード(MPI並列)を呼ぶアダプタ向けで、PSO・GA と同じ仕組み。
    # 候補はどの段でも、乱数を引く順序を変えずにまとめて作ってから評価する。
    # 初期化・追従蜂・偵察蜂は段の中で候補が互いに依存しないので、num_parallel によらず以前と同じ答えになる。
    # 雇用蜂だけは、逐次では先に更新された食料源を後の蜂が参照するので、num_parallel > 1 では段の始まりの
    # 食料源から候補を作る（MPI でランクをまたぐときと同じ形）。このときは逐次と答えが変わる
    num_parallel = int( config['ABC'].get('num_parallel', 1) )
    if num_parallel > 1:
      adapter_instance = getattr(objective_function, '__self__', None)
      if not getattr(adapter_instance, 'flag_parallel_evaluation', False):
        super().stop_program(f'[ABC-Borealis] Error: ABC.num_parallel > 1 is not supported by the selected adapter: {type(adapter_instance).__name__}', self.mpi_instance)
      print(f'[ABC-Borealis] Number of concurrent evaluations: {num_parallel}')
      executor = ThreadPoolExecutor(max_workers=num_parallel)
    else:
      executor = None

    def evaluate_batch(candidates):
      # candidates: (x, unique_id, step) の並び。結果は同じ順序で返る
      if executor is None:
        return [ evaluate(x, unique_id, step) for x, unique_id, step in candidates ]
      return list( executor.map(lambda c: evaluate(*c), candidates) )

    # 各プロセスの担当範囲を決定
    # 例: 80個を4プロセスなら、各20個
    indices_per_proc = np.array_split(np.arange(num_employ_bees), size)
    my_indices = indices_per_proc[rank]

    # データ保持用
    food_source = np.zeros((num_employ_bees, num_dimension))
    solution = np.zeros((num_employ_bees, num_objectives))
    visit_counter = np.zeros(num_employ_bees, dtype=int)

    # 履歴用
    id_history = np.zeros((num_optiter, num_employ_bees), dtype=int)
    id_history_init = np.zeros((num_employ_bees), dtype=int)
    # 現在のステップでの最新IDを保持する一時配列
    current_ids = np.zeros(num_employ_bees, dtype=int)

    # --- 1. Initialization (担当分のみ計算) ---
    candidates = []
    for i in my_indices:
      food_source[i] = self.generate_food_source(parameter_boundary)
      # 重複しないIDを生成
      unique_id = self.generate_unique_id(0, 0, i+1, rank+1)
      candidates.append( (food_source[i].copy(), unique_id, 0) )
      current_ids[i] = unique_id
    results = evaluate_batch(candidates)
    record(candidates, results)
    for i, sol in zip(my_indices, results):
      solution[i] = sol

    # 初期化時の同期
    if self.mpi_instance.flag_mpi :
      self._sync_all(MPI, rank, size, comm, food_source, solution, visit_counter, current_ids)

    id_history_init = current_ids

    # 初期状態を全プロセスで共有
    #comm.Allgather(MPI.IN_PLACE, [food_source, MPI.DOUBLE])
    # solutionは1次元配列なので Allallgather か Allreduce で集約
    #solution = comm.allreduce(solution, op=MPI.SUM)

    best_solution = np.min(solution[:, 0])
    best_food_source = food_source[np.argmin(solution[:, 0])].copy()
    best_id = int(current_ids[np.argmin(solution[:, 0])])

    # 多目的の外部アーカイブ（全ランクで同じものを持つ）
    archive_ids = []
    archive_positions = np.zeros((0, num_dimension))
    archive_scores = np.zeros((0, num_objectives))
    archive_id_history = []
    archive_position_history = []
    archive_score_history = []
    archive_centroid_history = []

    # History
    best_index_history = np.zeros(num_optiter, dtype=int)
    food_source_history = np.zeros((num_optiter, num_employ_bees, num_dimension))
    solution_history = np.zeros((num_optiter, num_employ_bees, num_objectives))
    residaul_mean_history = []
    # それまでの最良の履歴（output_global.dat に書く。以前はそのステップの食料源の中の最良を書いていた。既知の問題 16）
    best_solution_history = np.zeros(num_optiter)
    best_food_source_history = np.zeros((num_optiter, num_dimension))
    best_id_history = np.zeros(num_optiter, dtype=int)
    solution_window = [ solution.copy() ]

    solution_init = solution.copy()
    solution_prev = solution.copy()

    # --- Iteration ---
    for n in range(num_optiter):
      # --- 1. Employed bee phase (担当分のみ探索) ---
      def employed_candidate(i):
        # 更新する次元を1つ選ぶ (k) と、比較対象を選ぶ (j != i)
        k = np.random.randint(num_dimension)
        j = np.random.choice([idx for idx in range(num_employ_bees) if idx != i])
        phi = np.random.uniform(-1, 1)
        v = food_source[i].copy()
        v[k] = food_source[i, k] + phi * (food_source[i, k] - food_source[j, k])
        # 境界チェック（クリッピング）
        v[k] = np.clip(v[k], parameter_boundary[k][0], parameter_boundary[k][1])
        return v, self.generate_unique_id(n+1, 1, i+1, rank+1)

      def employed_update(i, v, unique_id, sol_v):
        if accept(sol_v, solution[i]):
          food_source[i] = v
          solution[i] = sol_v
          visit_counter[i] = 0
        else:
          visit_counter[i] += 1
        current_ids[i] = unique_id

      if executor is None:
        # 逐次: 先に更新された食料源を後の蜂が参照する（以前と同じ）
        for i in my_indices:
          v, unique_id = employed_candidate(i)
          sol_v = evaluate(v, unique_id, n)
          record( [(v, unique_id, n)], [sol_v] )
          employed_update(i, v, unique_id, sol_v)
      else:
        # 並列: 段の始まりの食料源から候補をまとめて作り、同時に評価してから順に採否を決める
        candidates = [ (i,) + employed_candidate(i) for i in my_indices ]
        batch = [ (v, unique_id, n) for i, v, unique_id in candidates ]
        results = evaluate_batch(batch)
        record(batch, results)
        for (i, v, unique_id), sol_v in zip(candidates, results):
          employed_update(i, v, unique_id, sol_v)
      
      # フェーズ終了後に全プロセスを同期
      if self.mpi_instance.flag_mpi :
        self._sync_all(MPI, rank, size, comm, food_source, solution, visit_counter, current_ids)

      # --- 2. Onlooker bee phase ---
      if flag_multi:
        # 非劣解の順位 r（0 が第 1 フロント）から適応度 1/(1+r)
        fitness_values = [ 1.0/(1.0+r) for r in self.non_dominated_sort(solution) ]
      else:
        fitness_values = [self.fitness_value_function(s[0]) for s in solution]
      # 追従蜂も担当を分ける (sizeで割る)
      onlook_base  = num_onlook_bees // size
      onlook_rem   = num_onlook_bees % size
      my_onlook_count = onlook_base + (1 if rank < onlook_rem else 0)
      # 自分より前のランクが担当した追従蜂数の合計（一意なbee_idxを作るためのオフセット）
      onlook_offset = rank * onlook_base + min(rank, onlook_rem)

      # 選択先 i は全食料源からルーレット選択されるため、自分の担当範囲(my_indices)外を
      # 更新することがある。以前は _sync_all() が担当範囲外の更新を0クリアしてから
      # Allreduce(SUM) していたため、担当外への更新が消失するバグがあった。
      # そのため、更新内容を一旦ローカルに集めてから全ランクでallgatherし、
      # 全プロセスが同一の順序で適用することで、どのランクが選んだ更新も失わないようにする。
      # 更新は段の終わりにまとめて適用するので、候補はまとめて作ってから評価してよい（逐次と同じ答え）
      onlook_candidates = []
      for m_idx in range(my_onlook_count):
        i = self.roulette_wheel_selection(fitness_values)
        # 雇用蜂と同じ近傍探索を行う
        k = np.random.randint(num_dimension)
        j = np.random.choice([idx for idx in range(num_employ_bees) if idx != i])
        phi = np.random.uniform(-1, 1)

        v = food_source[i].copy()
        v[k] = food_source[i, k] + phi * (food_source[i, k] - food_source[j, k])
        v[k] = np.clip(v[k], parameter_boundary[k][0], parameter_boundary[k][1])

        unique_id = self.generate_unique_id(n+1, 2, onlook_offset+m_idx+1, rank+1)
        onlook_candidates.append( (i, v, unique_id) )
      onlook_batch = [ (v, unique_id, n) for i, v, unique_id in onlook_candidates ]
      onlook_results = evaluate_batch(onlook_batch)
      record(onlook_batch, onlook_results)
      local_onlook_updates = []
      for (i, v, unique_id), sol_v in zip(onlook_candidates, onlook_results):
        accepted = accept(sol_v, solution[i])
        local_onlook_updates.append( (i, accepted, v if accepted else None, sol_v if accepted else None, unique_id) )

      if self.mpi_instance.flag_mpi :
        gathered_onlook_updates = comm.allgather(local_onlook_updates)
      else:
        gathered_onlook_updates = [local_onlook_updates]

      # 全プロセスが同一の順序（ランク順→蜂順）で適用するため、最終状態は全ランクで一致する
      for updates_from_rank in gathered_onlook_updates:
        for i, accepted, v, sol_v, unique_id in updates_from_rank:
          if accepted:
            food_source[i] = v
            solution[i] = sol_v
            visit_counter[i] = 0
          else:
            visit_counter[i] += 1
          current_ids[i] = unique_id

      # --- 3. Scout bee phase ---
      scout_candidates = []
      for local_idx in my_indices:
        if visit_counter[local_idx] > visit_limit:
          unique_id = self.generate_unique_id(n+1, 3, local_idx+1, rank+1)
          # 新しい蜜源の生成
          food_source[local_idx] = self.generate_food_source(parameter_boundary)
          scout_candidates.append( (local_idx, unique_id) )
          current_ids[local_idx] = unique_id
          # カウンターリセット
          visit_counter[local_idx] = 0
      # 新しい蜜源の評価
      scout_batch = [ (food_source[local_idx].copy(), unique_id, n) for local_idx, unique_id in scout_candidates ]
      scout_results = evaluate_batch(scout_batch)
      record(scout_batch, scout_results)
      for (local_idx, unique_id), sol in zip(scout_candidates, scout_results):
        solution[local_idx] = sol
  
      # 重要：スカウトによって更新された情報を全プロセスに波及させる     
      if self.mpi_instance.flag_mpi :
        self._sync_all(MPI, rank, size, comm, food_source, solution, visit_counter, current_ids)

      # --- Update Global Best & History ---
      current_min_idx = np.argmin(solution[:, 0])
      #print('rank, test-current_min',rank, current_min_idx,solution)
      if solution[current_min_idx, 0] < best_solution:
        best_solution = solution[current_min_idx, 0]
        best_food_source = food_source[current_min_idx].copy()
        best_id = int(current_ids[current_min_idx])
      best_solution_history[n] = best_solution
      best_food_source_history[n] = best_food_source
      best_id_history[n] = best_id

      food_source_history[n] = food_source.copy()
      solution_history[n] = solution.copy()
      best_index_history[n] = current_min_idx
      id_history[n] = current_ids.copy()

      # windowsize_residual ステップ前の解との相対変化。分母は初期値の絶対値
      # （以前は初期値そのもので、負の値だと残差が負になって即座に収束としていた）
      solution_window.append( solution.copy() )
      solution_prev = solution_window[ max(0, len(solution_window) - 1 - windowsize_residual) ]
      residual = np.abs((solution - solution_prev) / (np.abs(solution_init) + 1e-20))
      residual_mean = np.mean(residual)
      residaul_mean_history.append(residual_mean)

      if not flag_multi:
        if rank == 0:
          print(f'Step: {n+1}, Best: {best_solution:.5e}, Residual: {self.text_color}{residual_mean:.10e}{self.text_end}')

        # 最初の windowsize_residual ステップは判定しない（1 ステップ目で更新が無いと残差 0 で打ち切られていた。既知の問題 5）
        if n + 1 > windowsize_residual and residual_mean <= config['ABC']['tolerance']:
          num_optiter = n + 1
          break
        continue

      # --- 多目的: このステップで評価したすべての点をアーカイブへ（全ランクで同じ順序で入れる）---
      if self.mpi_instance.flag_mpi :
        gathered_evaluations = comm.allgather(step_evaluations)
      else:
        gathered_evaluations = [step_evaluations]
      archive_ids, archive_positions, archive_scores = self.update_pareto_archive(
        archive_ids, archive_positions, archive_scores, [e for g in gathered_evaluations for e in g], num_archive)
      step_evaluations.clear()
      archive_id_history.append( list(archive_ids) )
      archive_position_history.append( archive_positions.copy() )
      archive_score_history.append( archive_scores.copy() )
      archive_centroid_history.append( np.mean(archive_scores, axis=0) )

      # アーカイブの重心が windowsize_archive ステップ前から tolerance_archive 以下しか動かなければ収束
      # （既定の tolerance_archive = 0 では、アーカイブがそのあいだ変わらなかったときだけ止まる）
      archive_change = np.inf
      if len(archive_centroid_history) > windowsize_archive:
        archive_change = np.linalg.norm( archive_centroid_history[-1] - archive_centroid_history[-1-windowsize_archive] )

      if rank == 0:
        print(f'Step: {n+1}, Archive size: {len(archive_ids)}, Archive change: {self.text_color}{archive_change:.10e}{self.text_end}, Residual: {residual_mean:.10e}')

      if archive_change <= tolerance_archive:
        num_optiter = n + 1
        break


    if executor is not None:
      executor.shutdown()

    # Output
    if rank == 0 and flag_multi:
      print('[ABC-Borealis] Final Pareto archive:')
      for unique_id, x, f in zip(archive_ids, archive_positions, archive_scores):
        print(f'--Pareto ID: {unique_id}, Parameter: {x}, Solution: {f}')
    elif rank == 0:
      print('Best condition:', best_food_source )
      print('Best value:', best_solution )
      print('Step, Best-condition index, Best condition, Best solution')
      for n in range(0,num_optiter):
        i_opt = best_index_history[n]
        print(n+1, i_opt+1, id_history[n,i_opt], food_source_history[n,i_opt,:], solution_history[n,i_opt,0])

    # Dictionary作成 (Rank 0のみが保存に使う)
    solution_dict = {
            self.str_num_optiter: num_optiter,
            self.str_residual: residaul_mean_history,
            self.str_food_source: food_source_history[:num_optiter],
            self.str_error: solution_history[:num_optiter],
            self.str_best_index: best_index_history[:num_optiter],
            self.str_id_history: id_history[:num_optiter],
            'best_solution': best_solution_history[:num_optiter],
            'best_food_source': best_food_source_history[:num_optiter],
            'best_id': best_id_history[:num_optiter],
            self.str_archive_id: archive_id_history,
            self.str_archive_position: archive_position_history,
            self.str_archive_score: archive_score_history
        }

    if flag_multi:
      return archive_positions, archive_scores, solution_dict
    return best_food_source, best_solution, solution_dict


  def update_pareto_archive(self, archive_ids, archive_positions, archive_scores, evaluations, num_archive):
    # アーカイブに新しい評価 (ID, パラメータ, 値) を足し、非劣解だけを残す。同じパラメータの点は 1 つにする。
    # num_archive を超えたら、混雑距離の最も小さい点を 1 つずつ捨てる（捨てるたびに距離を計算し直す）
    ids = list(archive_ids)
    positions = list(archive_positions)
    scores = list(archive_scores)
    for unique_id, x, f in evaluations:
      if any( np.array_equal(x, p) for p in positions ):
        continue
      ids.append(unique_id)
      positions.append(x)
      scores.append(f)
    positions = np.array(positions).reshape(len(ids), -1)
    scores = np.array(scores).reshape(len(ids), -1)
    keep = np.where( self.non_dominated_mask(scores) )[0]
    while len(keep) > num_archive:
      distance = self.crowding_distance( scores[keep], np.zeros(len(keep), dtype=int) )
      keep = np.delete( keep, np.argmin(distance) )
    return [ ids[k] for k in keep ], positions[keep], scores[keep]

  def _sync_all(self, MPI, rank, size, comm, food_source, solution, visit_counter, current_ids):
    #rank = self.mpi_instance.rank
    #size = self.mpi_instance.size
    # 自分の担当インデックスを再取得
    indices_per_proc = np.array_split(np.arange(len(solution)), size)
    my_indices = indices_per_proc[rank]
    
    # 1. 担当以外をゼロにした一時的な配列を作成
    fs_tmp = np.zeros_like(food_source)
    sol_tmp = np.zeros_like(solution)
    vc_tmp = np.zeros_like(visit_counter)
    id_tmp = np.zeros_like(current_ids)
    
    fs_tmp[my_indices] = food_source[my_indices]
    sol_tmp[my_indices] = solution[my_indices]
    vc_tmp[my_indices] = visit_counter[my_indices]
    id_tmp[my_indices] = current_ids[my_indices]
    
    # 2. 全プロセスで合計(SUM)して同期。これで全員が最新の「全データ」を持つ。
    comm.Allreduce(fs_tmp, food_source, op=MPI.SUM)
    comm.Allreduce(sol_tmp, solution, op=MPI.SUM)
    comm.Allreduce(vc_tmp, visit_counter, op=MPI.SUM)
    comm.Allreduce(id_tmp, current_ids, op=MPI.SUM)

  def generate_unique_id(self, iter_idx, phase_idx, bee_idx, rank):
    # 一意のIDを生成する
    # 桁数の設計例（10進数でわかる形式）
    # [イテレーション: 10^7] [フェーズ: 10^6] [鉢番号: 10^3] [ランク: 1]
    # 例: 第12ステップ, Phase 2, Bee 15, Rank -> 12 2 015 004
    # - イテレーション: 10,000,000の位 (最大999回)
    # - フェーズ: 1,000,000の位 (0-9)
    # - 蜂番号: 1,000の位 (最大999ランクまで)
    # - MPIランク: 1の位 (最大999個まで)
    #unique_id = (iter_idx * 10000000) + (phase_idx * 1000000) + (bee_idx * 1000) + rank
    unique_id = (iter_idx * 10000) + (phase_idx * 1000) + (bee_idx)
    return int(unique_id)

  def write_optimization_process(self, config, solution_dict):

    # Number of iteration
    num_optiter = solution_dict[self.str_num_optiter]
    # Number of particles
    num_employ_bees = config['ABC']['num_employ_bees']
    # Number of dimension
    num_dimension = self.num_dimension
    # Parameter name list
    solution_name_list = self.parameter_name_list
    # Number of objectives
    num_objectives = config.get('objectives', {}).get('num_objectives', 1)

    # Variables
    food_source_history   = solution_dict[self.str_food_source]
    solution_history      = solution_dict[self.str_error]
    best_index_history    = solution_dict[self.str_best_index]
    residaul_mean_history = solution_dict[self.str_residual]
    id_history            = solution_dict[self.str_id_history]

    # Output results
    filename_tmp =  config['ABC']['result_dir'] + '/' + config['ABC']['filename_output']
    print('--Writing output file...:',filename_tmp)

    file_output = open( filename_tmp , 'w')
    # Header
    header_tmp = "Variables="
    for n in range(0,len(solution_name_list)):
      header_tmp = header_tmp + solution_name_list[n] + ','
    # Addition
    if num_objectives == 1:
      header_tmp = header_tmp + ' ID' + ',' + ' Solution' + ',' + 'Residual_mean' + '\n'
    else:
      header_tmp = header_tmp + ' ID,' + ''.join( ' Error_' + str(k+1) + ',' for k in range(num_objectives) ) + ' Residual_mean' + '\n'
    file_output.write( header_tmp )

    for n in range(0, num_optiter):
      text_tmp = 'zone t="Time'+str(n+1) +' sec"' + '\n'
      text_tmp =  text_tmp + 'i='+str(num_employ_bees)+' f=point' + '\n'
      for i in range(0, num_employ_bees):
        text_tmp = text_tmp
        for j in range(0,num_dimension):
          text_tmp = text_tmp  + str( food_source_history[n,i,j] ) + ', '
        text_tmp = text_tmp + str(id_history[n,i]) + ', '
        for k in range(0, num_objectives):
          text_tmp = text_tmp + str(solution_history[n,i,k]) + ', '
        text_tmp = text_tmp + str(residaul_mean_history[n]) + '\n'
      file_output.write( text_tmp )
    file_output.close()

    return


  def write_best_solution_history(self, config, solution_dict):

    # Number of iteration
    num_optiter = solution_dict[self.str_num_optiter]
    # Number of particles
    num_employ_bees = config['ABC']['num_employ_bees']
    # Number of dimension
    num_dimension = self.num_dimension

    # Variables
    best_index_history    = solution_dict[self.str_best_index]
    food_source_history   = solution_dict[self.str_food_source]
    solution_history      = solution_dict[self.str_error]
    id_history            = solution_dict[self.str_id_history]

    # Output results: Global information
    filename_tmp =  config['ABC']['result_dir'] + '/' + config['ABC']['filename_global']
    num_objectives = config.get('objectives', {}).get('num_objectives', 1)
    if num_objectives > 1:
      # 多目的: 各ステップのアーカイブ。PSO・GA の output_global.dat と同じ形
      print('--Writing Pareto history file...:',filename_tmp)
      obj_header = ', '.join( f'Objective{k+1}' for k in range(num_objectives) )
      param_header = ', '.join( f'Parameter{m+1}' for m in range(num_dimension) )
      with open(filename_tmp, 'w') as file_output:
        file_output.write(f'Variables = Step, Pareto_ID, {obj_header}, {param_header}\n')
        for n in range(len(solution_dict[self.str_archive_id])):
          for unique_id, x, f in zip(solution_dict[self.str_archive_id][n], solution_dict[self.str_archive_position][n], solution_dict[self.str_archive_score][n]):
            line = f'{n+1}, {unique_id}, ' + ', '.join( str(v) for v in f )
            for value in x:
              line += f', {value}'
            file_output.write(line + '\n')
      return

    print('--Writing best solution file...:',filename_tmp)

    file_output = open( filename_tmp , 'w')
    # Header
    header_tmp = 'Variables = Step, GID, GSolution, '
    for n in range(0,num_dimension):
      header_tmp = header_tmp + 'GParameter_' + str(n+1) + ', '
    header_tmp = header_tmp.rstrip(',') + '\n'
    file_output.write( header_tmp )

    # それまでの最良（偵察蜂が最良の食料源を捨てても悪化しない）
    for n in range(0, num_optiter):
      text_tmp = str(n+1) + ', ' + str(solution_dict['best_id'][n]) + ', '
      text_tmp = text_tmp + str(solution_dict['best_solution'][n]) +  ', '
      for m in range(0,num_dimension):
        text_tmp = text_tmp + str( solution_dict['best_food_source'][n, m] ) + ', '
      text_tmp = text_tmp.rstrip(',') + '\n'
      file_output.write( text_tmp )
    file_output.close()

    return


  def drive_optimization(self, config, objective_function, parameter_boundary):

    best_condition, best_value, solution_dict = self.run_optimizer_abc(config, objective_function, parameter_boundary)

    if self.mpi_instance.rank == 0:
      self.write_optimization_process(config, solution_dict)

    if self.mpi_instance.rank == 0:
      self.write_best_solution_history(config, solution_dict)

    return