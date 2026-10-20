#!/bin/bash

PYTHON=python3.8
HOME_BORE=/opt/Borealis/borealis-v1.2.0
#HOME_BORE=$HOME/source/borealis/borealis-v1.2.0
LD_DIR=$HOME_BORE/src_helper
LOG=log_postprocess

# Delete files
LD_DEL=$LD_DIR/delete_nonoptimal_solution/delete_nonoptimal_solution.py
$PYTHON $LD_DEL > $LOG

# Make image optimal solution
LD_IMAGE=$LD_DIR/pickup_optimal_result/pickup_optimal_result.py
$PYTHON $LD_IMAGE >> $LOG
