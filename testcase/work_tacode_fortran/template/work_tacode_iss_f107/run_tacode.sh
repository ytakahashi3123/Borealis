#!/bin/bash

# NRLMSISE-00 (F10.7ベースで大気モデルテーブルを動的生成する)
NRLMSISE_HOME=$HOME/source/tacode/nrlmsise/NRLMSISE-00/tacode_work
LD_MSIS=$NRLMSISE_HOME/NRLMSISE-00_readctl_2fequal_global.exe
LOG_MSIS=log_msis
$LD_MSIS > $LOG_MSIS

# Tacode
TACODE_HOME=$HOME/source/tacode/tacode-v1.2.1/bin
LD=$TACODE_HOME/tacode
LOG=log_tacode
$LD > $LOG
