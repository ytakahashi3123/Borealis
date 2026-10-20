#!/usr/bin/env python3

# ベイズ最適化。bayesian-optimization (https://github.com/bayesian-optimization/BayesianOptimization) を使う。
# 1.6 までは GPyOpt を使っていたが、保守が止まり numpy 2 で動かないため置き換えた（既知の問題 22）。
#
# 候補を 1 つずつ出して結果を登録する形（suggest / register）で回す。こうすると、
#   - PSO・ABC と同じく、評価の番号 (id, step, sign) を目的関数に渡せる（ケースのディレクトリの番号がそろう）
#   - NaN・無限大の値を共通の処理（orbital.sanitize_score）で置き換えられる
# bayesian-optimization は最大化するので、最小化のときは目的関数の値の符号を反転して登録する。

import numpy as np
from orbital.orbital import orbital


class Bayesian_optimization(orbital):

  def __init__(self,mpi_instance):

    print("Constructing class: Bayesian_optimization")

    self.mpi_instance = mpi_instance

    self.str_error = 'Error'

    return


  def initial_setting(self, config):

    if self.mpi_instance.rank == 0:
      result_dir = config['Bayesian_optimization']['result_dir']
      super().make_directory_rm(result_dir)
    if self.mpi_instance.flag_mpi :
      self.mpi_instance.comm.Barrier()

    return


  def boundary_setting(self, config):

    # Setting parameter's boundaries
    # bayesian-optimization はパラメータを名前で持つので、成分の名前（type）が重なっても困らないよう、
    # 通し番号の名前（p0000, p0001, ...）を付ける。辞書の順序はそのまま保たれる
    boundary = config['parameter_optimized']['boundary']
    parameter_boundary = {}
    self.parameter_name_list = []
    count = 0
    for n in range(0, len(boundary) ):
      boundary_name = boundary[n]['name']
      parameter_component = boundary[n]['component']
      for m in range(0,  len(parameter_component)):
        bound_type = parameter_component[m]['type']
        bound_min  = parameter_component[m]['bound_min']
        bound_max  = parameter_component[m]['bound_max']
        parameter_boundary[f'p{count:04d}'] = (float(bound_min), float(bound_max))
        self.parameter_name_list.append(bound_type)
        print( 'Boundary in',bound_type,'component of',boundary_name,'(min--max):', bound_min,'--',bound_max)
        count += 1

    return parameter_boundary


  def make_acquisition(self, config, random_state):

    from bayes_opt import acquisition

    setting = config['Bayesian_optimization']
    kind = str( setting.get('acquisition_type', 'EI') )
    if kind.endswith('_MCMC'):
      raise ValueError(f'[BO-Borealis] acquisition_type {kind} is not available (the MCMC variants were GPyOpt only). Use EI, PI or LCB.')
    if kind == 'EI':
      return acquisition.ExpectedImprovement( xi=float(setting.get('acquisition_xi', 0.01)), random_state=random_state )
    elif kind in ('PI', 'MPI'):
      # MPI は GPyOpt での名前（maximum probability of improvement）
      return acquisition.ProbabilityOfImprovement( xi=float(setting.get('acquisition_xi', 0.01)), random_state=random_state )
    elif kind in ('LCB', 'UCB'):
      # 最小化の LCB は、符号を反転した値の UCB と同じ。重み kappa は acquisition_weight
      return acquisition.UpperConfidenceBound( kappa=float(setting.get('acquisition_weight', 2.0)), random_state=random_state )
    else:
      raise ValueError(f'[BO-Borealis] acquisition_type must be EI, PI (MPI) or LCB (UCB): {kind}')


  def bayesian_optimization(self, config, objective_function, parameter_boundary):

    from bayes_opt import BayesianOptimization

    setting = config['Bayesian_optimization']

    model_type = setting.get('model_type', 'GP')
    if model_type != 'GP':
      raise ValueError(f'[BO-Borealis] model_type {model_type} is not available; bayesian-optimization uses a Gaussian process (GP).')

    flag_maximize = bool( setting.get('maximize', False) )
    sign_target = 1.0 if flag_maximize else -1.0      # bayesian-optimization は最大化する
    num_initial = int( setting.get('initial_design_numdata', 5) )
    num_optiter = int( setting['num_optiter'] )
    value_nonfinite = float( config['parameter_optimized'].get('value_nonfinite', 1.0e+30) )

    # 乱数の種: optimizer.seed があれば使う（無ければ numpy の大域の乱数から 1 つ取る）
    seed = config.get('optimizer', {}).get('seed')
    random_state = int(seed) + self.mpi_instance.rank if seed is not None else int( np.random.randint(0, 2**31-1) )

    optimizer = BayesianOptimization( f=None,
                                      pbounds=parameter_boundary,
                                      acquisition_function=self.make_acquisition(config, random_state),
                                      random_state=random_state,
                                      verbose=0,
                                      allow_duplicate_points=True )
    optimizer.set_gp_params( normalize_y=bool(setting.get('normalize_Y', True)) )

    keys = list(parameter_boundary.keys())
    num_dimension = len(keys)
    position_history = []
    error_history = []

    num_total = num_initial + num_optiter
    for n in range(0, num_total):
      # 最初の num_initial 点は一様乱数、そのあとは獲得関数が最大になる点
      if n < num_initial:
        params = optimizer.random_sample(1)[0]
      else:
        params = optimizer.suggest()
      x = np.array([ float(params[key]) for key in keys ])

      # 目的関数: PSO・ABC と同じく (x, 番号, ステップ, 符号) で呼ぶ。最大化はここで扱うので符号は 1
      score = objective_function( x.reshape(1, num_dimension), n+1, n, 1.0 )
      # NaN・無限大は、最適化の向きで十分に悪い値に置き換える
      error = float( super().sanitize_score( -sign_target*np.atleast_1d(score), 1, value_nonfinite, 'BO' )[0] ) * (-sign_target)

      optimizer.register( params=params, target=sign_target*error )
      position_history.append(x)
      error_history.append(error)
      kind = 'initial' if n < num_initial else 'step'
      print(f'[BO-Borealis] {kind} {n+1}/{num_total}: error = {error:.10e}')

    position_history = np.array(position_history)
    error_history = np.array(error_history)
    index_best = int( np.argmax(error_history) if flag_maximize else np.argmin(error_history) )

    print("Optimized solutions:")
    print("--Solutions :" , position_history[index_best])
    print("--Error     :" , error_history[index_best])
    print("--Epoch     :" , index_best + 1)

    solution_dict = {}
    for m, name in enumerate(self.parameter_name_list):
      solution_dict[m] = position_history[:, m]
    solution_dict[self.str_error] = error_history
    solution_dict['index_best'] = index_best
    solution_dict['flag_maximize'] = flag_maximize

    return optimizer, solution_dict


  def write_optimization_data(self, config, solution_dict):

    # Output results: 評価した順に、パラメータ・誤差・番号（Epoch）
    filename_tmp =  config['Bayesian_optimization']['result_dir'] + '/' + config['Bayesian_optimization']['filename_output']
    print('--Writing output file...:',filename_tmp)

    header_tmp = "Variables="
    for name in self.parameter_name_list:
      header_tmp = header_tmp + name + ','
    header_tmp = header_tmp + self.str_error + ',' + 'Epoch' + '\n'

    error_history = solution_dict[self.str_error]
    num_step = len(error_history)
    text_tmp = ''
    for n in range(0, num_step):
      for m in range(0, len(self.parameter_name_list)):
        text_tmp = text_tmp + str( solution_dict[m][n] ) + ', '
      text_tmp = text_tmp + str( error_history[n] ) + ', ' + str( float(n+1) ) + '\n'

    with open(filename_tmp, 'w') as file_output:
      file_output.write( header_tmp )
      file_output.write( text_tmp )

    return


  def plot_optimization_process(self, config, solution_dict):

    # 収束の図（それまでの最良）。獲得関数の図は GPyOpt だけの機能だったので作らない
    setting = config['Bayesian_optimization']
    if setting.get('flag_image_convergence', False):
      # matplotlib は図を作るときだけ要る。無ければ図を作らずに終える（最適化の結果はすでに書いてある）
      try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
      except ImportError:
        print('[BO-Borealis] Warning: matplotlib is not installed; the convergence image is not written')
        return
      error_history = solution_dict[self.str_error]
      if solution_dict['flag_maximize']:
        best = np.maximum.accumulate(error_history)
      else:
        best = np.minimum.accumulate(error_history)
      fig, ax = plt.subplots(figsize=(5, 3.4))
      ax.plot(np.arange(1, len(error_history)+1), error_history, '.', color='0.6', label='evaluated')
      ax.plot(np.arange(1, len(error_history)+1), best, '-', label='best so far')
      ax.set_xlabel('evaluation')
      ax.set_ylabel('objective')
      ax.legend()
      fig.tight_layout()
      filename_tmp = setting['result_dir'] + '/' + setting.get('filename_image_convergence', 'convergence.png')
      fig.savefig(filename_tmp)
      plt.close(fig)
    if setting.get('flag_image_acquisition', False):
      print('[BO-Borealis] Warning: flag_image_acquisition is not supported (it was a GPyOpt feature)')

    return


  def drive_optimization(self, config, objective_function, parameter_boundary):

    # Bayesian optimization
    optimizer, solution_dict = self.bayesian_optimization(config, objective_function, parameter_boundary)

    # Write data
    if self.mpi_instance.rank == 0:
      self.write_optimization_data(config, solution_dict)

    # Plot data
    if self.mpi_instance.rank == 0:
      self.plot_optimization_process(config, solution_dict)

    return
