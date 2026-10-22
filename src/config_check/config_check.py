#!/usr/bin/env python3

# 設定ファイル (borealis.yml) のキーを検査する。
# 知らないキーを書いても止まらないので、綴りを誤ったキーは黙って既定値で走っていた（既知の問題 4）。
# 選んだ手法・アダプタのセクションと共通のセクションについて、
#   - コードが読まないキー（綴りの誤りなど）
#   - 読まれるが効かないキー、古い名前のキー
# を警告として返す。止めはしない（既存の設定ファイルを壊さないため）。
# キーの一覧は report/config_reference_ja.md と対応させること。


# 共通のセクション
KEYS_COMMON = {
  'adapter': {'kind_adapter'},
  'optimizer': {'kind_optimizer', 'seed'},
  'objectives': {'num_objectives', 'kind_objectives', 'shape_type'},
  'parameter_optimized': {'boundary', 'boundary_initial', 'velocity_initial', 'flag_penalty', 'penalty_value',
                          'value_nonfinite', 'flag_with_timeerror', 'set_altitude', 'set_count_pass', 'weight_time',
                          'flag_Connectedness', 'flag_boundary_measure_penalty', 'boundary_measure'},
  'reference': {'directory_path_specify', 'manual_path', 'filename_input', 'var_x', 'var_y', 'timeunit'},
}

# 手法のセクション
KEYS_OPTIMIZER = {
  'PSO': {'num_particle', 'num_optiter', 'inertia', 'cognitive_coef', 'social_coef', 'maximize',
          'windowsize_residual', 'tolerance_residual', 'windowsize_archive', 'tolerance_archive',
          'num_parallel', 'result_dir', 'filename_output', 'filename_global',
          'inertia_schedule', 'inertia_max', 'inertia_min', 'coefficient_schedule', 'cognitive_coef_initial',
          'cognitive_coef_final', 'social_coef_initial', 'social_coef_final'},
  'ABC': {'num_employ_bees', 'num_onlook_bees', 'num_onlook_bee', 'visit_limit', 'vist_limit', 'num_optiter',
          'tolerance', 'windowsize_residual', 'maximize', 'num_parallel', 'result_dir', 'filename_output', 'filename_global',
          'num_archive', 'windowsize_archive', 'tolerance_archive'},
  'GA': {'num_generation', 'num_population', 'tournament_size', 'crossover_rate', 'eta_crossover', 'mutation_rate',
         'eta_mutation', 'maximize', 'windowsize_residual', 'tolerance_residual', 'num_parallel', 'result_dir',
         'filename_output', 'filename_global'},
  'Bayesian_optimization': {'model_type', 'normalize_Y', 'maximize', 'initial_design_numdata', 'acquisition_type',
                            'acquisition_weight', 'acquisition_xi', 'num_optiter', 'result_dir', 'filename_output',
                            'flag_image_convergence', 'filename_image_convergence', 'boundary', 'num_parallel'},
}

# アダプタのセクション
KEYS_EXTERNAL = {'work_dir', 'case_dir', 'step_digit', 'directory_path_specify', 'manual_path',
                 'filename_control', 'filename_result', 'cmd_code', 'result_dir', 'flag_output', 'filename_output'}
KEYS_ADAPTER = {
  'tacode': KEYS_EXTERNAL | {'code_system', 'target_time', 'time_start', 'time_end'},
  'simple_function': {'flag_output', 'result_dir', 'filename_output', 'function_discrete',
                      'function_bound_min', 'function_bound_max', 'function_type'},
  'example_externalcode': (KEYS_EXTERNAL - {'cmd_code'}) | {'cmd_externalcode', 'x_min', 'x_max', 'x_offset'},
  'heatcond': KEYS_EXTERNAL | {'x_min', 'x_max', 'x_offset', 'variables_output'},
  'cage': KEYS_EXTERNAL | {'x_min', 'x_max', 'x_offset', 'var_x', 'var_y', 'variables_output'},
  'shapeoptimizer': {'work_dir', 'case_dir', 'step_digit', 'directory_path_specify', 'manual_path', 'cmd_code',
                     'result_dir', 'in_sequential', 'work_dir_series', 'filename_forces', 'filename_displacements',
                     'step_digit_series', 'flag_surfacearea_constraint', 'work_dir_surfacearea', 'filename_surfacearea',
                     'tolerance_surfacearea', 'penalty_surfacearea', 'num_cpu_per_case', 'cpu_offset', 'cpu_assignment',
                     'flag_cpu_set', 'polling_interval', 'timeout_finalize', 'penalty_failure'},
  'pixelflow': {'work_dir', 'case_dir', 'step_digit', 'directory_path_specify', 'manual_path', 'cmd_code',
                'filename_control', 'filename_result', 'filename_forces'},
  'user': KEYS_EXTERNAL | {'x_min', 'x_max'},
}

# 読まれるが効かないキー、古い名前のキー: (セクション, キー) -> 案内
KEYS_NO_EFFECT = {
  ('PSO', 'tolerance'): 'not read; use PSO.tolerance_residual',
  ('PSO', 'kind_residual_computation'): 'not read',
  ('PSO', 'times_spte_pso'): 'not read',
  ('GA', 'mutation_limit'): 'not read (a key of the former prototype GA; the polynomial mutation uses GA.eta_mutation)',
  ('GA', 'tolerance'): 'not read (a key of the former prototype GA); use GA.tolerance_residual',
  ('Bayesian_optimization', 'initial_design_type'): 'not read',
  ('Bayesian_optimization', 'model_update_interval'): 'not read',
  ('Bayesian_optimization', 'acquisition_optimizer_type'): 'not read (a GPyOpt option; bayesian-optimization maximizes the acquisition itself)',
  ('Bayesian_optimization', 'verbosity'): 'not read (a GPyOpt option)',
  ('Bayesian_optimization', 'flag_image_acquisition'): 'not supported (a GPyOpt feature)',
  ('Bayesian_optimization', 'filename_image_acquisition'): 'not supported (a GPyOpt feature)',
  ('tacode', 'convert_timeunit_tapost'): 'not read',
  ('cage', 'x_min'): 'read but has no effect',
  ('cage', 'x_max'): 'read but has no effect',
  ('cage', 'x_offset'): 'read but has no effect',
  ('shapeoptimizer', 'power_variable_objectivefunction'): 'not read; objectives.num_objectives selects drag (1) or drag and moment (2)',
  ('shapeoptimizer', 'filename_result'): 'not read',
  ('shapeoptimizer', 'flag_output'): 'not read',
  ('shapeoptimizer', 'filename_output'): 'not read',
  ('pixelflow', 'result_dir'): 'not read',
  ('pixelflow', 'flag_output'): 'not read',
  ('pixelflow', 'filename_output'): 'not read',
  ('parameter_optimized', 'weight_time'): 'read, but the time error is not added to the objective (known issue 27)',
}

# 古い綴りのキー（読むが、正しい綴りを勧める）
KEYS_OLD_SPELLING = {
  ('ABC', 'vist_limit'): 'visit_limit',
  ('ABC', 'num_onlook_bee'): 'num_onlook_bees',
}

# reference を読まないアダプタ
ADAPTERS_WITHOUT_REFERENCE = {'simple_function', 'shapeoptimizer', 'pixelflow'}

SECTIONS_OTHER = set()   # 外してある手法（書いてあっても読まない）


def check_config(config):
  """設定を検査し、警告の文の並びを返す"""
  warnings = []
  if not isinstance(config, dict):
    return ['the configuration file is empty or not a mapping']

  kind_adapter = config.get('adapter', {}).get('kind_adapter')
  kind_optimizer = config.get('optimizer', {}).get('kind_optimizer')

  known_top = set(KEYS_COMMON) | set(KEYS_OPTIMIZER) | set(KEYS_ADAPTER) | SECTIONS_OTHER
  for section in config:
    if section not in known_top:
      warnings.append(f"unknown section '{section}' is not read")

  sections = dict(KEYS_COMMON)
  if kind_optimizer in KEYS_OPTIMIZER:
    sections[kind_optimizer] = KEYS_OPTIMIZER[kind_optimizer]
  if kind_adapter in KEYS_ADAPTER:
    sections[kind_adapter] = KEYS_ADAPTER[kind_adapter]

  for section, known in sections.items():
    values = config.get(section)
    if not isinstance(values, dict):
      continue
    if section == 'reference' and kind_adapter in ADAPTERS_WITHOUT_REFERENCE:
      warnings.append(f"section 'reference' is not read by the adapter '{kind_adapter}'")
      continue
    for key in values:
      if (section, key) in KEYS_NO_EFFECT:
        warnings.append(f"{section}.{key}: {KEYS_NO_EFFECT[(section, key)]}")
      elif (section, key) in KEYS_OLD_SPELLING:
        warnings.append(f"{section}.{key}: old spelling, still accepted; write {section}.{KEYS_OLD_SPELLING[(section, key)]}")
      elif key not in known:
        warnings.append(f"{section}.{key}: unknown key, not read (misspelled?)")

  # parameter_optimized.boundary の中
  boundary = config.get('parameter_optimized', {}).get('boundary') or []
  for n, param in enumerate(boundary if isinstance(boundary, list) else []):
    for key in param:
      if key == 'coordinate':
        warnings.append(f"parameter_optimized.boundary[{n}].coordinate: not read")
      elif key not in ('name', 'component'):
        warnings.append(f"parameter_optimized.boundary[{n}].{key}: unknown key, not read")
    for m, component in enumerate(param.get('component') or []):
      for key in component:
        if key not in ('type', 'bound_min', 'bound_max'):
          warnings.append(f"parameter_optimized.boundary[{n}].component[{m}].{key}: unknown key, not read")

  return warnings
