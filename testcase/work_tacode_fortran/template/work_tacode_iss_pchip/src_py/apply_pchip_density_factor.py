#!/usr/bin/env python3
"""
apply_pchip_density_factor.py

tacode本体を実行する直前に呼ばれる前処理スクリプト。
orbit.ctl の「Lower bound of altitude」(制御点の高度)と「Density factor opimized」
(各制御点での係数、PSOが最適化する値)を読み取り、それらをPCHIP
(scipy.interpolate.PchipInterpolator, 区分3次エルミート補間)で高度に対して
滑らかに補間した係数プロファイルを作る。これをベースライン大気モデル
テーブル(atmospheremodel_raw.txt, factor=1.0の生データ)に高度ごとに掛け合わせ、
tacodeが実際に読み込む database/atmospheremodel_baseline/atmospheremodel.txt
として書き出す。

これにより、work_tacode_iss(CTL入力, 階段関数的に区分ごとに一定の係数)とは異なり、
係数が制御点間で滑らかに(C1連続に)変化する大気密度プロファイルが得られる。
tacode本体のorbit.ctlは Density factor model=1 (Uniform, factor=1.0固定) にして
あるので、tacode自身はこのスクリプトが焼き込んだ値をそのまま使うだけになる。

制御点範囲外(altitude < bounds[0] または > bounds[-1])は外挿すると発散しうるため、
最寄りの制御点係数でクランプする。

実行方法(run_tacode.shから呼ばれる想定。カレントディレクトリはケースディレクトリ):
  python3 src_py/apply_pchip_density_factor.py
"""

import re
import numpy as np
from scipy.interpolate import PchipInterpolator

ORBIT_CTL = 'orbit.ctl'
RAW_TABLE = 'database/atmospheremodel_baseline/atmospheremodel_raw.txt'
OUT_TABLE = 'database/atmospheremodel_baseline/atmospheremodel.txt'
HEADER_LINES = 21

# atmospheremodel.txt の列(0始まり): 0=Height, 1=O, 2=N2, 3=O2, 4=Mass_density,
# 5=Temperature_neutral, 6=N。tacode本体(atmosphere_variables.f90)で
# density_factorを掛けるのは密度系の列のみで、Height/Temperatureは対象外。
DENSITY_COLUMNS = [1, 2, 3, 4, 6]


def parse_numbers(line):
  line_nocomment = line.split('#')[0]
  return [float(s) for s in re.split(r'[,\s]+', line_nocomment.strip()) if s]


def read_control_points(filename):
  with open(filename) as f:
    lines = f.readlines()
  lines_strip = [l.strip() for l in lines]
  i_bound = next(i for i, l in enumerate(lines_strip) if 'Lower bound of altitude' in l)
  i_factor = next(i for i, l in enumerate(lines_strip) if 'Density factor opimized' in l)
  bounds = np.array(parse_numbers(lines_strip[i_bound]))
  factors = np.array(parse_numbers(lines_strip[i_factor]))
  return bounds, factors


def main():
  bounds, factors = read_control_points(ORBIT_CTL)
  print(f'PCHIP control points -- altitude[km]: {bounds}')
  print(f'PCHIP control points -- density_factor: {factors}')

  pchip = PchipInterpolator(bounds, factors)

  with open(RAW_TABLE) as f:
    header_lines = [next(f) for _ in range(HEADER_LINES)]
  data = np.loadtxt(RAW_TABLE, skiprows=HEADER_LINES)

  altitude_km = data[:, 0]
  altitude_clamped = np.clip(altitude_km, bounds[0], bounds[-1])
  factor_profile = pchip(altitude_clamped)

  for col in DENSITY_COLUMNS:
    data[:, col] = data[:, col] * factor_profile

  with open(OUT_TABLE, 'w') as f:
    f.writelines(header_lines)
    np.savetxt(f, data, fmt='%.6E')

  print(f'Wrote PCHIP-corrected atmosphere table to: {OUT_TABLE}')
  print(f'factor_profile range: {factor_profile.min():.4f} - {factor_profile.max():.4f}')


if __name__ == '__main__':
  main()
