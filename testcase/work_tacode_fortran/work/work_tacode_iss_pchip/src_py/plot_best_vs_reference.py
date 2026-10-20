#!/usr/bin/env python3
"""
plot_best_vs_reference.py

PSO最適化(result_PSO/output_global.dat)のベスト解（全ステップ中でObjectiveが
最小のケース）が計算した軌道(経過時刻 vs 高度)と、リファレンス軌道(GPR再構成)を
比較プロットするスクリプト。

ワーキングディレクトリ(borealis.yml があるディレクトリ、例: work_tacode_iss/)の
1階層下の src_py/ に置くことを想定している。カレントディレクトリに関わらず、
このファイル自身の場所からワーキングディレクトリへ自動的に移動してから
borealis.yml 等の相対パスを解決する。他のケースでも同じ場所(<case>/src_py/)に
置けばそのまま使える。

実行方法:
  python3 testcase/work_tacode_fortran/work/work_tacode_iss/src_py/plot_best_vs_reference.py
  (どのディレクトリから実行してもよい)

出力:
  result_PSO/comparison_altitude.png
"""

import os
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import yaml

# borealis.yml があるワーキングディレクトリ(このファイルの1階層上)へ移動
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def read_config_yaml(file_control):
  with open(file_control) as f:
    return yaml.safe_load(f)


def find_best_case(filename_global):
  """result_PSO/output_global.dat から Objective が最小(nanを除く)の行を探す。"""
  with open(filename_global) as f:
    lines = f.readlines()

  best_id = None
  best_obj = None
  for line in lines[1:]:  # skip header ("Variables = ...")
    line = line.strip()
    if not line:
      continue
    fields = [s.strip() for s in line.split(',')]
    pareto_id = int(fields[1])
    try:
      obj = float(fields[2])
    except ValueError:
      continue
    if np.isnan(obj):
      continue
    if best_obj is None or obj < best_obj:
      best_obj = obj
      best_id = pareto_id

  if best_id is None:
    raise RuntimeError(f'No valid (non-NaN) objective found in {filename_global}')
  return best_id, best_obj


def read_tacode_trajectory(filename):
  """tacode-Fortran の trajectory.dat (variables=... ヘッダ) を読み込む。"""
  with open(filename) as f:
    lines = f.readlines()
  variables_line = lines[0].replace('variables=', '').strip()
  words = variables_line.split(',')

  data = np.loadtxt(filename, comments=None, skiprows=2)
  col = {name: i for i, name in enumerate(words)}
  time_s = data[:, col['time[s]']]
  altitude_km = data[:, col['altitude[km]']]
  return time_s, altitude_km


def read_reference_altitude(filename):
  """reference/<case>/output/trajectory_altitude.dat (time[s], mean, std) を読み込む。"""
  data = np.loadtxt(filename, comments=('#'), delimiter=None, skiprows=1)
  time_abs_sec = data[:, 0]
  mean = data[:, 1]
  std = data[:, 2]
  return time_abs_sec, mean, std


def main():
  file_control = sys.argv[1] if len(sys.argv) > 1 else 'borealis.yml'
  config = read_config_yaml(file_control)

  # PSO best solution
  pso_cfg = config['PSO']
  filename_global = os.path.join(pso_cfg['result_dir'], pso_cfg['filename_global'])
  best_id, best_obj = find_best_case(filename_global)
  print(f'Best case: Pareto_ID={best_id}, Objective={best_obj}')

  # Corresponding tacode case directory
  tacode_cfg = config['tacode']
  step_digit = tacode_cfg['step_digit']
  case_dir = os.path.join(tacode_cfg['work_dir'], tacode_cfg['case_dir'] + str(best_id).zfill(step_digit))
  filename_traj = os.path.join(case_dir, tacode_cfg['filename_result'])
  print(f'Reading best-case trajectory...: {filename_traj}')
  time_s, altitude_km = read_tacode_trajectory(filename_traj)

  # Reference trajectory (altitude)
  ref_cfg = config['reference']
  reference_path = ref_cfg['manual_path']
  filename_ref = os.path.join(reference_path, 'trajectory_altitude.dat')
  print(f'Reading reference trajectory...: {filename_ref}')
  ref_time_abs_sec, ref_mean, ref_std = read_reference_altitude(filename_ref)
  # Align reference to the same "elapsed time since target_time" basis as tacode's time[s]
  ref_time_elapsed = ref_time_abs_sec - ref_time_abs_sec[0]

  # Evaluation window actually used by evaluate_error (time_start/time_end relative to target_time)
  target_time_day = tacode_cfg['target_time']
  time_start_elapsed_s = (tacode_cfg['time_start'] - target_time_day) * 86400.0
  time_end_elapsed_s = (tacode_cfg['time_end'] - target_time_day) * 86400.0

  # Interpolate best-case altitude onto the reference time grid (for residual plot)
  mask_ref = (ref_time_elapsed >= time_start_elapsed_s) & (ref_time_elapsed <= time_end_elapsed_s)
  best_on_ref_grid = np.interp(ref_time_elapsed[mask_ref], time_s, altitude_km)
  residual = best_on_ref_grid - ref_mean[mask_ref]

  # ------------------------------------------------------------------
  # Plot
  # ------------------------------------------------------------------
  fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True,
                                  gridspec_kw={'height_ratios': [3, 1]})

  ax1.fill_between(ref_time_elapsed, ref_mean - 2 * ref_std, ref_mean + 2 * ref_std,
                    color='0.7', alpha=0.5, label='Reference 95% CI (GPR)')
  ax1.plot(ref_time_elapsed, ref_mean, color='black', lw=1.2, label='Reference (GPR mean)')
  ax1.plot(time_s, altitude_km, color='tab:blue', lw=1.5,
            label=f'Best solution (case{str(best_id).zfill(step_digit)}, obj={best_obj:.4g})')
  ax1.axvspan(time_start_elapsed_s, time_end_elapsed_s, color='tab:orange', alpha=0.08,
              label='Evaluation window')

  ax1.set_ylabel('Altitude, km')
  ax1.set_title('ISS density estimation: best PSO solution vs. reference trajectory')
  ax1.legend(loc='best', fontsize=9)
  ax1.grid(True, linewidth=0.4, alpha=0.5)

  ax2.axhline(0.0, color='black', lw=0.8)
  ax2.plot(ref_time_elapsed[mask_ref], residual, color='tab:red', lw=1.2)
  ax2.set_xlabel('Elapsed time, s')
  ax2.set_ylabel('Best - Ref, km')
  ax2.grid(True, linewidth=0.4, alpha=0.5)

  x_margin = 0.05 * (time_end_elapsed_s - time_start_elapsed_s)
  ax1.set_xlim(time_start_elapsed_s - x_margin, time_end_elapsed_s + x_margin)

  fig.tight_layout()

  out_path = os.path.join(pso_cfg['result_dir'], 'comparison_altitude.png')
  fig.savefig(out_path, dpi=150)
  print(f'Saved figure to: {out_path}')
  print(f'RMS residual (best - reference) over evaluation window: '
        f'{np.sqrt(np.mean(residual**2)):.4f} km')


if __name__ == '__main__':
  main()
