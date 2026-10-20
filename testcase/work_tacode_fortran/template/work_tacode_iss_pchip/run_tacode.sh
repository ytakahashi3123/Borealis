#!/bin/bash

# PCHIP補間で密度係数プロファイルを大気モデルテーブルに焼き込む(numpy/scipyが入っているvenvを明示指定)
PYTHON=$HOME/venvs/myenv/bin/python3
$PYTHON src_py/apply_pchip_density_factor.py > log_pchip

# Tacode
TACODE_HOME=$HOME/source/tacode/tacode-v1.2.1/bin
LD=$TACODE_HOME/tacode
LOG=log_tacode
$LD > $LOG
