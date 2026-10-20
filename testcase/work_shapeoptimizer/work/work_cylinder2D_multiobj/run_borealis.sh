#!/bin/bash

source $HOME/venvs/myenv/bin/activate
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_su2
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_borealis

PYTHON=python3
filename_jobrequests="job_requests"

# Optimizer
# Initial settings
LD_BORE=$HOME_BORE/src/borealis.py
LOG_BORE=log_borealis
MPIP_BORE=mpirun.openmpi
num_process_bore=6

# Delete old files
if [ -f "$filename_jobrequests" ]; then
  rm "$filename_jobrequests"
  if [ $? -eq 0 ]; then
    echo "$filename_jobrequests has been deleted."
  else
    echo "Failed to delete $filename_jobrequests." >&2
    exit 1
  fi
else
  echo "$filename_jobrequests does not exist."
fi

# Run Borealis
parallel_bore=true
if $parallel_bore ; then
  $MPIP_BORE -n $num_process_bore $PYTHON $LD_BORE > $LOG_BORE &
else
  $PYTHON $LD_BORE > $LOG_BORE &
fi

./run_SU2-OPT.sh
