#!/usr/bin/env python3
"""
plot_density_profile.py (F10.7版)

PSOベスト解が実際に使った大気密度プロファイル(NRLMSISE-00の全球平均、F10.7Aで
駆動)と、デフォルトのF10.7A(テンプレートの初期値, DEFAULT_F107Aで指定)で生成した
プロファイルを高度に対して比較プロットする。

work_tacode_iss(density_factor CTL方式)の同名スクリプトとは仕組みが異なる点に注意:
  - あちらは「静的なベーステーブル x 高度区分ごとの係数」を比較していた。
  - こちらはdensity_factorを使わず(Uniform, factor=1.0固定)、F10.7Aという単一の
    物理パラメータでNRLMSISE-00モデルそのものが計算する密度プロファイルを
    直接比較する。

比較する3本の線:
  1. デフォルト(F10.7A=DEFAULT_F107A)   : NRLMSISEドライバをこの値で単独実行して生成。
  2. ベスト解(F10.7A=PSOが見つけた値)    : ベストケースの
                                            database/atmospheremodel_baseline/atmospheremodel.txt
                                            (そのケース用に実際に生成されたテーブル)をそのまま読む。
  3. 実測値(ベストケースのtrajectory.dat): tacodeが実際に計算した density[kg/m3] を
                                            altitude[km]に対してプロットしたもの
                                            (1と2が正しく一致しているかの確認用)。

ワーキングディレクトリ(borealis.yml があるディレクトリ)の1階層下の src_py/ に
置くことを想定している。plot_best_vs_reference.py と同様、実行時にこのファイルの
場所からワーキングディレクトリへ自動的に移動する。

実行方法:
  python3 testcase/work_tacode_fortran/work/work_tacode_iss_f107/src_py/plot_density_profile.py

出力:
  result_PSO/comparison_density.png
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import yaml

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

NRLMSISE_EXE = os.path.expanduser(
    '~/source/tacode/nrlmsise/NRLMSISE-00/tacode_work/NRLMSISE-00_readctl_2fequal_global.exe')
DEFAULT_F107A = 150.0  # テンプレートorbit.ctlの初期値(最適化前のデフォルト)


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


def read_atmospheremodel(filename):
  """NRLMSISEドライバが生成するatmospheremodel.txt(21行ヘッダ)を読み込む。"""
  with open(filename) as f:
    header_lines = [next(f) for _ in range(21)]
  f107a = None
  for line in header_lines:
    if line.strip().startswith('F107A'):
      f107a = float(line.split()[1])
      break
  data = np.loadtxt(filename, skiprows=21)
  height_km = data[:, 0]
  mass_density_kgm3 = data[:, 4] * 1000.0  # g/cm3 -> kg/m3
  return height_km, mass_density_kgm3, f107a


def generate_atmospheremodel(case_template_dir, f107a):
  """NRLMSISEドライバを指定F10.7Aで単独実行し、生成されたテーブルを読み込んで返す
  (副作用を避けるため一時ディレクトリにケーステンプレートをコピーしてから実行する)。"""
  with tempfile.TemporaryDirectory() as tmp_dir:
    shutil.copytree(case_template_dir, tmp_dir, dirs_exist_ok=True)

    ctl_path = os.path.join(tmp_dir, 'orbit.ctl')
    with open(ctl_path) as f:
      lines = f.readlines()
    for i, line in enumerate(lines):
      if '# fa10.7' in line:
        lines[i] = f'{f107a} # fa10.7\n'
        break
    else:
      raise RuntimeError(f'"# fa10.7" line not found in {ctl_path}')
    with open(ctl_path, 'w') as f:
      f.writelines(lines)

    subprocess.run([NRLMSISE_EXE], cwd=tmp_dir, stdout=subprocess.DEVNULL, check=True)

    atm_path = os.path.join(tmp_dir, 'database', 'atmospheremodel_baseline', 'atmospheremodel.txt')
    height_km, mass_density_kgm3, f107a_used = read_atmospheremodel(atm_path)
  return height_km, mass_density_kgm3, f107a_used


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

  # 2. The best case's own generated atmosphere table (F10.7A found by PSO)
  filename_best_atm = os.path.join(case_dir, 'database', 'atmospheremodel_baseline', 'atmospheremodel.txt')
  print(f'Reading best-case atmosphere table...: {filename_best_atm}')
  height_best_km, density_best_table, f107a_best = read_atmospheremodel(filename_best_atm)
  print(f'Best-fit F10.7A = {f107a_best}')

  # 3. Default (pre-optimization) atmosphere table, regenerated on demand
  print(f'Generating default atmosphere table (F10.7A={DEFAULT_F107A})...')
  height_default_km, density_default_table, _ = generate_atmospheremodel(tacode_cfg['manual_path'], DEFAULT_F107A)

  # ------------------------------------------------------------------
  # Plot: full altitude range (context, log-y) and zoom on the ISS-relevant
  # altitude band are saved as two separate figures/files.
  # ------------------------------------------------------------------
  zoom_lo = min(390.0, altitude_best_km.min() - 5.0)
  zoom_hi = altitude_best_km.max() + 5.0

  plots = [
      ('full', True, 'Full atmosphere table range (global mean)', 'comparison_density_full.png'),
      ('zoom', False, f'Zoom: ISS pass altitude range ({altitude_best_km.min():.1f}-{altitude_best_km.max():.1f}km)',
       'comparison_density_zoom.png'),
  ]

  for _, log_y, title, out_name in plots:
    fig, ax = plt.subplots(figsize=(8, 6))

    ax.plot(height_default_km, density_default_table, color='0.5', lw=1.5, ls='--',
            label=f'Default (F10.7A={DEFAULT_F107A:.0f}, pre-optimization)')
    ax.plot(height_best_km, density_best_table, color='tab:orange', lw=1.5,
            label=f'Best-fit atmosphere table (F10.7A={f107a_best:.1f})')
    ax.plot(altitude_best_km_sorted, density_best_sorted, color='tab:blue', lw=1.5, ls=':',
            label=f'Actual tacode density (best solution, case{str(best_id).zfill(step_digit)})')
    ax.set_xlabel('Altitude, km')
    ax.set_ylabel('Density, kg/m$^3$')
    ax.grid(True, which='both', linewidth=0.4, alpha=0.5)
    ax.set_title('ISS density estimation (F10.7-driven NRLMSISE-00): best-fit vs. default atmosphere\n' + title)
    if log_y:
      ax.set_yscale('log')
      ax.set_xlim(0, max(height_default_km.max(), height_best_km.max()))
    else:
      ax.set_xlim(zoom_lo, zoom_hi)
      mask_lo = (height_default_km >= zoom_lo) & (height_default_km <= zoom_hi)
      y_all = np.concatenate([density_default_table[mask_lo], density_best_sorted])
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
