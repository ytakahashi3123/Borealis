#!/bin/bash

source $HOME/venvs/myenv/bin/activate
source $HOME/.dir_opt_bashrc/.bashrc_borealis
source $HOME/.dir_opt_bashrc/.bashrc_intel

parallel_mpi=true

PYTHON=python
LD=$HOME_BORE/src/borealis.py
LOG=log_borealis

MPIP=mpirun.openmpi
num_process=8

touch timestamp_start_$(date "+%Y%m%d-%H%M%S")
if $parallel_mpi ; then
  $MPIP -n $num_process $PYTHON $LD > $LOG
else
  $PYTHON $LD > $LOG
fi
touch timestamp_end_$(date "+%Y%m%d-%H%M%S")
