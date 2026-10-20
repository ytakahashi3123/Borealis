#!/usr/bin/env python3
"""
plot_density_profile.py

PSOベスト解の大気密度プロファイル(高度 vs 密度)と、補正前(density_factor=1.0)の
ベースライン大気モデル(NRLMSISE-00テーブル)を比較プロットするスクリプト。

比較する3本の線:
  1. ベースライン (補正なし, factor=1.0)          : template/<case>/database/atmospheremodel_baseline/
                                                       atmospheremodel.txt をtacodeと同じ線形補間+
                                                       上限クランプで評価した値。
  2. 理論値 (baseline x density_factor)            : ベストケースのorbit.ctlに書き込まれた実際の
                                                       density_factor(高度区分ごと)をベースラインに
                                                       掛け合わせた値。tacodeのCTL入力ロジック
                                                       (atmosphere_variables.f90:set_atmosphere_property,
                                                       DENSITY_FACTOR_CTLINPUT)を再現したもの。
  3. 実測値 (ベストケースのtrajectory.dat)          : tacodeが実際に計算した density[kg/m3] を
                                                       altitude[km] に対してプロットしたもの。

★重要な既知の制約(このスクリプトで発見): atmosphere_variables.f90:set_atmosphere_property は、
問い合わせ高度がベーステーブルの範囲外(本ケースでは400km超、ISSの通過高度は常にこれに該当)の場合、
density_factorを掛けずにテーブル最終行の生の値をそのまま返す(else節、452-455行目)。density_factorの
乗算(398-401行目)はテーブル範囲内(flag_atmosphere_inrange)の場合にしか行われないため、ISSケースでは
density_factorが実質的に完全に無視される。実際、trajectory.datのdensity列は全区間で
1.938e-12 kg/m3(テーブル最終行の生値)と完全に一定であり、PSOが探索したdensity_factorの値
(-1.31や-0.49等、境界[0.5,1.5]を大きく逸脱していても)は結果に一切影響していなかった。
上記「理論値」の線はこの実挙動(テーブル範囲外ではfactor=1.0扱い)を反映しており、テーブル範囲内(0-400km)
でのみdensity_factorが効くことを示す。本格的な密度推定を行うには、atmospheremodel.txtを
ISSの通過高度帯(400-450km程度)までカバーするように拡張する必要がある。

ワーキングディレクトリ(borealis.yml があるディレクトリ)の1階層下の src_py/ に
置くことを想定している。plot_best_vs_reference.py と同様、実行時にこのファイルの
場所からワーキングディレクトリへ自動的に移動する。

実行方法:
  python3 testcase/work_tacode_fortran/work/work_tacode_iss/src_py/plot_density_profile.py

出力:
  result_PSO/comparison_density.png
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


def read_baseline_atmosphere(filename):
  """atmospheremodel.txt (NRLMSISE-00, 21行ヘッダ) を読み込み、Height[km]とMass_density[kg/m3]を返す。"""
  data = np.loadtxt(filename, skiprows=21)
  height_km = data[:, 0]
  mass_density_kgm3 = data[:, 4] * 1000.0  # g/cm-3 -> kg/m3
  return height_km, mass_density_kgm3


def lookup_baseline_density(height_km, mass_density_kgm3, altitude_query_km):
  """tacodeのDENSITY_FACTOR無し部分(atmosphere_variables.f90の線形補間+上下限クランプ)を再現する。"""
  result = np.empty_like(altitude_query_km, dtype=float)
  for i, alt in enumerate(altitude_query_km):
    if alt <= height_km[0]:
      result[i] = mass_density_kgm3[0]
    elif alt >= height_km[-1]:
      result[i] = mass_density_kgm3[-1]
    else:
      result[i] = np.interp(alt, height_km, mass_density_kgm3)
  return result


def read_density_factor_from_ctl(filename):
  """ベストケースのorbit.ctlから、density_factorの高度区分と実際に使われた係数を読み取る。"""
  with open(filename) as f:
    lines = f.readlines()
  lines_strip = [l.strip() for l in lines]

  i_bound = next(i for i, l in enumerate(lines_strip) if 'Lower bound of altitude' in l)
  i_factor = next(i for i, l in enumerate(lines_strip) if 'Density factor opimized' in l)

  def parse_numbers(line):
    line_nocomment = line.split('#')[0]
    return [float(s) for s in re.split(r'[,\s]+', line_nocomment.strip()) if s]

  bounds = parse_numbers(lines_strip[i_bound])
  factors = parse_numbers(lines_strip[i_factor])
  return np.array(bounds), np.array(factors)


def apply_density_factor(altitude_query_km, baseline_density, bounds, factors, table_max_km):
  """tacodeのDENSITY_FACTOR_CTLINPUTロジックを再現する。

  atmosphere_variables.f90:set_atmosphere_property のうち、density_factorの乗算
  (398-401行目)は「ベーステーブルの範囲内(flag_atmosphere_inrange)」の場合にしか
  適用されない。範囲外(altitude > table_max、本ケースでは常に成立)では、else節
  (452-455行目)が var_atmosphere_tmp(5,n_count_atmosphere) を係数を掛けずにそのまま
  返すため、density_factorは完全に無視される。
  """
  factor_applied = np.ones_like(altitude_query_km, dtype=float)  # table範囲外はfactorなし(=1.0)
  in_table_range = altitude_query_km <= table_max_km
  for n in range(len(bounds) - 1):
    mask = in_table_range & (altitude_query_km >= bounds[n]) & (altitude_query_km <= bounds[n + 1])
    factor_applied[mask] = factors[n]
  return baseline_density * factor_applied


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

  # 1. Actual tacode density along the best trajectory
  altitude_best_km, density_best = read_tacode_trajectory(os.path.join(case_dir, tacode_cfg['filename_result']))
  order = np.argsort(altitude_best_km)
  altitude_best_km_sorted = altitude_best_km[order]
  density_best_sorted = density_best[order]

  # 2. Baseline (uncorrected) atmosphere table
  filename_baseline = os.path.join(case_dir, 'database', 'atmospheremodel_baseline', 'atmospheremodel.txt')
  print(f'Reading baseline atmosphere table...: {filename_baseline}')
  height_km, mass_density_kgm3 = read_baseline_atmosphere(filename_baseline)

  # 3. density_factor bins/values actually used for the best case
  filename_ctl = os.path.join(case_dir, tacode_cfg['filename_control'])
  bounds, factors = read_density_factor_from_ctl(filename_ctl)
  print(f'Density factor altitude bounds [km]: {bounds}')
  print(f'Density factor values (best case)  : {factors}')

  # Query grid covering the table + the observed trajectory altitude range
  alt_min = min(height_km.min(), altitude_best_km.min())
  alt_max = max(height_km.max(), altitude_best_km.max()) + 10.0
  alt_query = np.linspace(alt_min, alt_max, 2000)

  table_max_km = height_km[-1]
  baseline_query = lookup_baseline_density(height_km, mass_density_kgm3, alt_query)
  theoretical_query = apply_density_factor(alt_query, baseline_query, bounds, factors, table_max_km)

  # ------------------------------------------------------------------
  # Plot: full altitude range (context, log-y) and zoom on the ISS-relevant
  # altitude band (linear-y, so the theoretical negative-factor excursions
  # are visible -- a log scale would just silently drop them) are saved as
  # two separate figures/files.
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

    ax.plot(alt_query, baseline_query, color='0.5', lw=1.5, ls='--',
            label='Baseline atmosphere (factor=1.0, NRLMSISE-00)')
    ax.plot(alt_query, theoretical_query, color='tab:orange', lw=1.5,
            label='Baseline x density_factor (theoretical, tacode logic reproduced)')
    ax.plot(altitude_best_km_sorted, density_best_sorted, color='tab:blue', lw=1.5,
            label=f'Actual tacode density (best solution, case{str(best_id).zfill(step_digit)})')
    for b in bounds:
      ax.axvline(b, color='0.85', lw=0.8, zorder=0)
    ax.axvspan(table_max_km, alt_query.max(), color='0.9', alpha=0.4, zorder=0,
               label=f'Out of baseline table range (>{table_max_km:.0f}km):\ndensity_factor has NO effect here')
    ax.set_xlabel('Altitude, km')
    ax.set_ylabel('Density, kg/m$^3$')
    ax.grid(True, which='both', linewidth=0.4, alpha=0.5)
    ax.set_title('ISS density estimation: best-fit density profile vs. baseline atmosphere model\n' + title)
    if log_y:
      ax.set_yscale('log')
      ax.set_xlim(alt_query.min(), alt_query.max())
    else:
      ax.axhline(0.0, color='black', lw=0.8)
      ax.set_xlim(zoom_lo, zoom_hi)
      mask_zoom = (alt_query >= zoom_lo) & (alt_query <= zoom_hi)
      y_all = np.concatenate([baseline_query[mask_zoom], theoretical_query[mask_zoom], density_best_sorted])
      pad = 0.1 * (y_all.max() - y_all.min() + 1e-30)
      ax.set_ylim(y_all.min() - pad, y_all.max() + pad)
    ax.legend(loc='best', fontsize=7.5)

    fig.tight_layout()

    out_path = os.path.join(pso_cfg['result_dir'], out_name)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f'Saved figure to: {out_path}')


if __name__ == '__main__':
  main()
