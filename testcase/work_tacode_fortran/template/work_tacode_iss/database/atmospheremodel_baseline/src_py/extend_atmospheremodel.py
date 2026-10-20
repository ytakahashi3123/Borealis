#!/usr/bin/env python3
"""
extend_atmospheremodel.py

../atmospheremodel.txt (NRLMSISE-00, CCMCのVITMO ModelWeb Browserから取得した
高度0-400kmのテーブル) は、work_tacode_issケースのISS通過高度(414.7-440.8km)を
まったくカバーしていない。tacode本体の大気参照ロジック(atmosphere_variables.f90:
set_atmosphere_property)はテーブル範囲外の高度に対してテーブル最終行の値を
そのままクランプして返す実装になっており、範囲外ではdensity_factorによる補正も
効かない(詳細はCLAUDE.mdの「重要な既知バグ」参照)。

このスクリプトは、元テーブルのヘッダに記載された生成条件
  year=2015, month=1, day=1, hour=1.50 (UT), latitude=55.00, longitude=45.00
を使い、NRLMSISE-00モデル(pip: nrlmsise00, 元データと同じモデル)で
高度401-460kmの行を追加生成し、../atmospheremodel.txt の末尾に追記する
(既存の0-400km行は一切変更しない)。

太陽活動度(F10.7)・磁気活動度(ap)は元テーブルに"not specified"としか
書かれていないため、既存データ(高度0-400km、特に350-400km付近)に対して
最も一致する値をグリッドサーチで校正した上で使用する(F10.7A=F10.7=150,
ap=4で400km点の誤差0.3%程度に収まることを確認済み)。

実行方法:
  python3 extend_atmospheremodel.py
"""

import os
import numpy as np
import nrlmsise00

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TABLE_PATH = os.path.join(SCRIPT_DIR, '..', 'atmospheremodel.txt')

# Generation conditions, matching the header of the original table
YEAR = 2015
DOY = 1
SEC = 1.50 * 3600.0  # hour=1.50 UT
LAT = 55.00
LON = 45.00

# Calibrated to match the existing 0-400km table (F10.7A=F10.7=150, ap=4
# reproduces the 400km row within ~0.3%; see docstring above)
F107A = 150.0
F107 = 150.0
AP = 4.0

EXTEND_START_KM = 401.0
EXTEND_STOP_KM = 460.0
EXTEND_STEP_KM = 1.0


def main():
  lst = SEC / 3600.0 + LON / 15.0

  heights = np.arange(EXTEND_START_KM, EXTEND_STOP_KM + 1e-6, EXTEND_STEP_KM)

  lines = []
  for h in heights:
    d = nrlmsise00.gtd7_flat(YEAR, DOY, SEC, float(h), LAT, LON, lst, F107A, F107, AP)
    o_cm3 = d[1]
    n2_cm3 = d[2]
    o2_cm3 = d[3]
    mass_density_gcm3 = d[5]
    temperature_k = d[10]  # t[1] (temperature at altitude) is index 10 in the flattened 11-element array
    n_cm3 = d[7]
    lines.append(f'  {h:6.1f}  {o_cm3:.3E}  {n2_cm3:.3E}  {o2_cm3:.3E} {mass_density_gcm3:.3E}  {temperature_k:6.1f}  {n_cm3:.3E}\n')

  with open(TABLE_PATH, 'a') as f:
    f.writelines(lines)

  print(f'Appended {len(lines)} rows ({EXTEND_START_KM:.0f}-{EXTEND_STOP_KM:.0f}km) to {TABLE_PATH}')
  print(f'First appended row: {lines[0].strip()}')
  print(f'Last appended row : {lines[-1].strip()}')


if __name__ == '__main__':
  main()
