#!/bin/bash

current_dir=$(pwd)
cd ${current_dir}

source ${HOME}/venvs/myenv/bin/activate
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_su2
#source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_python
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_borealis

parallel=true
fluid=false

# Common
DIR_FLUID=./fluid
DIR_OPT=./optimization

# Parallel
MPIP=mpirun.openmpi
# BOREALIS_NUM_CPU/BOREALIS_CPU_SET: Borealis(adapter_shapeoptimizer)から渡されるケースごとのコア数・コア番号
ncpu_f=${BOREALIS_NUM_CPU:-2}
ncpu_o=1
if [ -n "${BOREALIS_CPU_SET}" ]; then
  CPU_SET_OPT="--cpu-set ${BOREALIS_CPU_SET}"
else
  CPU_SET_OPT="--map-by core"
fi

# Fluid
if ! $fluid ; then # Coupled
  #LD_F=${SU2_ADAPTER_HOME}/run/SU2_preCICE_FSI.py
  #LD_F=${HOME_BORE}/src_helper/src_tmp/SU2_preCICE_FSI.py
  LD_F=${HOME_BORE}/src_interface/interface-SU2-OPT/SU2_preCICE_OPT.py
  LOG_F=log_su2
  INP_F=sphere.cfg
else
  LD_F=${SU2_HOME}/bin/SU2_CFD
  LOG_F=log_su2.fluid
  INP_F=sphere.fluid.cfg
fi

# Optimization
PYTHON=python3
LD_O=${HOME_BORE}/src_interface/interface-shapeoptimizer/shapeoptimizer_preCICE.py
LOG_O=log_shapeoptimization


# Start coupling routines
#touch timestamp_start_$(date "+%Y%m%d-%H%M%S")

# --Fluid
# Make directory
cd ${DIR_FLUID}
DIR_OUTPUT=("output_restart" "output_flow" "output_surface_flow")
for (( i = 0; i < ${#DIR_OUTPUT[*]}; i++ ))
{
   if [[ ! -e $DIR_OUTPUT[i] ]]; then
     mkdir ${DIR_OUTPUT[i]}
   fi
}

if ! $fluid ; then # Coupled
  if $parallel ; then
    $MPIP -np $ncpu_f --report-bindings --bind-to core ${CPU_SET_OPT} ${PYTHON} ${LD_F} -f ${INP_F} --parallel > $LOG_F 2>&1 &
  else
    ${LD_F} -f ${INP_F} -p SU2_CFD --parallel > $LOG_F 2>&1 &
  fi
else # Uncoupled
  if $parallel ; then
    $MPIP -np $ncpu_f --bind-to core ${CPU_SET_OPT} ${LD_F} ${INP_F} > $LOG_F 2>&1 &
  else
    ${LD_F} ${INP_F} > $LOG_F 2>&1 &
  fi
fi
PIDParticipant1=$!
cd ${current_dir}


# --Optimization
cd ${DIR_OPT}
if ! $fluid ; then
  if $parallel ; then
    export OMP_NUM_THREADS=$ncpu_o
  else
    export OMP_NUM_THREADS=1
  fi
  $PYTHON $LD_O > $LOG_O 2>&1 &
  PIDParticipant2=$!
fi
cd ${current_dir}


# Wait...
if $fluid ; then
  echo "Waiting for the participants to exit..., PIDs: ${PIDParticipant1}"
else
  echo "Waiting for the participants to exit..., PIDs: ${PIDParticipant1} ${PIDParticipant2}"
fi
echo "(you may run 'tail -f ${Participant1}.log' in another terminal to check the progress)"

# Borealisはこのスクリプトの終了を計算終了とみなすため、バックグラウンドにせず待つ
wait

#touch timestamp_end_$(date "+%Y%m%d-%H%M%S")
