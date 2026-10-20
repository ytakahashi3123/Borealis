#!/bin/bash

source $HOME/venvs/myenv/bin/activate
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_su2
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_borealis

PYTHON=python3
LD_DIR=$HOME_BORE/src_helper
LOG=log_postprocess

# Delete files
LD_DEL=$LD_DIR/delete_nonoptimal_solution/delete_nonoptimal_solution.py
$PYTHON $LD_DEL > $LOG

# Make image optimal solution
LD_IMAGE=$LD_DIR/pickup_optimal_result/pickup_optimal_result.py
$PYTHON $LD_IMAGE >> $LOG
