#!/bin/bash

source $HOME/venvs/myenv/bin/activate
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_su2
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_borealis

PYTHON=python3

# Optimizer
# Initial settings
LD_BORE=$HOME_BORE/src/borealis.py
LOG_BORE=log_borealis

# Run Borealis
# Borealis自身はmpirunで起動しない(MPI起動したプロセスからはSU2のmpirunを起動できないため)。
# ケースの同時実行数はborealis.ymlのPSO.num_parallel、ケースあたりのコア数はshapeoptimizer.num_cpu_per_caseで指定する。
# (以前のjob_requests+run_SU2-OPT.sh監視方式は不要)
$PYTHON $LD_BORE > $LOG_BORE 2>&1
