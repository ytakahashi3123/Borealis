#!/usr/bin/env python3
"""
plot_density_profile.py (PCHIP版)

PSOベスト解の大気密度プロファイルと、補正なしベースライン(factor=1.0)を
高度に対して比較プロットする。work_tacode_iss(階段関数)と異なり、このケースは
apply_pchip_density_factor.py が density_factor の制御点(高度0,405,420,435,450km)
を PchipInterpolator で滑らかに補間してから大気モデルテーブルに焼き込んでいるため、
区分境界での不連続なジャンプは生じない。

比較する3本の線:
  1. ベースライン (補正なし, factor=1.0)     : atmospheremodel_raw.txt をそのまま読む。
  2. ベスト解の大気密度テーブル              : ベストケースのdatabase/atmospheremodel_baseline/
                                                atmospheremodel.txt (PCHIP補間済み)をそのまま読む。
  3. 実測値 (ベストケースのtrajectory.dat)    : tacodeが実際に計算した density[kg/m3] を
                                                altitude[km] に対してプロットしたもの
                                                (1と2が正しく一致しているかの確認用)。

ワーキングディレクトリ(borealis.yml があるディレクトリ)の1階層下の src_py/ に
置くことを想定している。実行時にこのファイルの場所からワーキングディレクトリへ
自動的に移動する。

実行方法:
  python3 testcase/work_tacode_fortran/work/work_tacode_iss_pchip/src_py/plot_density_profile.py

出力:
  result_PSO/comparison_density_full.png
  result_PSO/comparison_density_zoom.png
"""

import os
import re
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import yaml

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def read_config_yaml(file_control):
  with open(file_control) as f:
    return yaml.safe_load(f)


def find_best_case(filename_global):
  with open(filename_global) as f:
    lines = f.readlines()
  best_id, best_obj = None, None
  for line in lines[1:]:
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
      best_obj, best_id = obj, pareto_id
  if best_id is None:
    raise RuntimeError(f'No valid (non-NaN) objective found in {filename_global}')
  return best_id, best_obj


def read_tacode_trajectory(filename):
  with open(filename) as f:
    lines = f.readlines()
  words = lines[0].replace('variables=', '').strip().split(',')
  col = {name: i for i, name in enumerate(words)}
  data = np.loadtxt(filename, comments=None, skiprows=2)
  altitude_km = data[:, col['altitude[km]']]
  density = data[:, col['density[kg/m3]']]
  return altitude_km, density


def read_atmospheremodel(filename, header_lines=21):
  data = np.loadtxt(filename, skiprows=header_lines)
  height_km = data[:, 0]
  mass_density_kgm3 = data[:, 4] * 1000.0  # g/cm3 -> kg/m3
  return height_km, mass_density_kgm3


def parse_numbers(line):
  line_nocomment = line.split('#')[0]
  return [float(s) for s in re.split(r'[,\s]+', line_nocomment.strip()) if s]


def read_control_points(filename):
  with open(filename) as f:
    lines = f.readlines()
  lines_strip = [l.strip() for l in lines]
  i_bound = next(i for i, l in enumerate(lines_strip) if 'Lower bound of altitude' in l)
  i_factor = next(i for i, l in enumerate(lines_strip) if 'Density factor opimized' in l)
  bounds = parse_numbers(lines_strip[i_bound])
  factors = parse_numbers(lines_strip[i_factor])
  return bounds, factors


def main():
  file_control = sys.argv[1] if len(sys.argv) > 1 else 'borealis.yml'
  config = read_config_yaml(file_control)

  pso_cfg = config['PSO']
  filename_global = os.path.join(pso_cfg['result_dir'], pso_cfg['filename_global'])
  best_id, best_obj = find_best_case(filename_global)
  print(f'Best case: Pareto_ID={best_id}, Objective={best_obj}')

  tacode_cfg = config['tacode']
  step_digit = tacode_cfg['step_digit']
  case_dir = os.path.join(tacode_cfg['work_dir'], tacode_cfg['case_dir'] + str(best_id).zfill(step_digit))

  # 1. Actual tacode density along the best trajectory (consistency check)
  altitude_best_km, density_best = read_tacode_trajectory(os.path.join(case_dir, tacode_cfg['filename_result']))
  order = np.argsort(altitude_best_km)
  altitude_best_km_sorted = altitude_best_km[order]
  density_best_sorted = density_best[order]

  # 2. Best case's PCHIP-corrected atmosphere table (already written by
  #    apply_pchip_density_factor.py before tacode ran)
  filename_best_atm = os.path.join(case_dir, 'database', 'atmospheremodel_baseline', 'atmospheremodel.txt')
  print(f'Reading best-case (PCHIP-corrected) atmosphere table...: {filename_best_atm}')
  height_best_km, density_best_table = read_atmospheremodel(filename_best_atm)

  # 3. Baseline (uncorrected, factor=1.0) atmosphere table
  filename_raw = os.path.join(case_dir, 'database', 'atmospheremodel_baseline', 'atmospheremodel_raw.txt')
  print(f'Reading baseline atmosphere table...: {filename_raw}')
  height_raw_km, density_raw_table = read_atmospheremodel(filename_raw)

  bounds, factors = read_control_points(os.path.join(case_dir, tacode_cfg['filename_control']))
  print(f'PCHIP control points -- altitude[km]: {bounds}')
  print(f'PCHIP control points -- density_factor: {factors}')

  # ------------------------------------------------------------------
  # Plot: full altitude range (context, log-y) and zoom on the ISS-relevant
  # altitude band are saved as two separate figures/files.
  # ------------------------------------------------------------------
  zoom_lo = min(390.0, altitude_best_km.min() - 5.0)
  zoom_hi = altitude_best_km.max() + 5.0

  plots = [
      ('full', True, 'Full atmosphere table range', 'comparison_density_full.png'),
      ('zoom', False, f'Zoom: ISS pass altitude range ({altitude_best_km.min():.1f}-{altitude_best_km.max():.1f}km)',
       'comparison_density_zoom.png'),
  ]

  for _, log_y, title, out_name in plots:
    fig, ax = plt.subplots(figsize=(8, 6))

    ax.plot(height_raw_km, density_raw_table, color='0.5', lw=1.5, ls='--',
            label='Baseline atmosphere (factor=1.0, NRLMSISE-00)')
    ax.plot(height_best_km, density_best_table, color='tab:orange', lw=1.5,
            label='Best-fit atmosphere table (PCHIP-interpolated density_factor)')
    ax.plot(altitude_best_km_sorted, density_best_sorted, color='tab:blue', lw=1.5, ls=':',
            label=f'Actual tacode density (best solution, case{str(best_id).zfill(step_digit)})')
    for b in bounds:
      ax.axvline(b, color='0.85', lw=0.8, zorder=0)
    ax.set_xlabel('Altitude, km')
    ax.set_ylabel('Density, kg/m$^3$')
    ax.grid(True, which='both', linewidth=0.4, alpha=0.5)
    ax.set_title('ISS density estimation (PCHIP-interpolated density_factor): best-fit vs. baseline\n' + title)
    if log_y:
      ax.set_yscale('log')
      ax.set_xlim(0, max(height_raw_km.max(), height_best_km.max()))
    else:
      ax.set_xlim(zoom_lo, zoom_hi)
      mask_lo = (height_raw_km >= zoom_lo) & (height_raw_km <= zoom_hi)
      y_all = np.concatenate([density_raw_table[mask_lo], density_best_sorted])
      pad = 0.1 * (y_all.max() - y_all.min() + 1e-30)
      ax.set_ylim(y_all.min() - pad, y_all.max() + pad)
    ax.legend(loc='best', fontsize=8)

    fig.tight_layout()

    out_path = os.path.join(pso_cfg['result_dir'], out_name)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f'Saved figure to: {out_path}')


if __name__ == '__main__':
  main()
