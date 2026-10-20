#!/bin/bash

source $HOME/venvs/myenv/bin/activate
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_su2
source ${HOME}/.dir_opt_bashrc/.bashrc_precice-v320_borealis

PYTHON=python3
filename_jobrequests="job_requests"

# Aerodynamic simulations for optimization

# Initial settings
fluid=false
# Common
DIR_FLUID=./fluid
DIR_OPT=./optimization

# Parallel
MPIP=mpirun.openmpi
ncpu_f=2
ncpu_o=1

# Fluid
if ! $fluid ; then # Coupled
  LD_F=${HOME_BORE}/src_interface/interface-SU2-OPT/SU2_preCICE_OPT.py
  LOG_F=log_su2
  INP_F=sphere.cfg
else
  LD_F=${SU2_HOME}/bin/SU2_CFD
  LOG_F=log_su2.fluid
  INP_F=sphere.fluid.cfg
fi

# Optimization
LD_O=${HOME_BORE}/src_interface/interface-shapeoptimizer/shapeoptimizer_preCICE.py
LOG_O=log_shapeoptimization


# File監視&計算実行
echo "Polling $filename_jobrequests for updates..."

last_mtime=0
while true; do
  if [ -f "$filename_jobrequests" ]; then
    current_mtime=$(stat -c %Y "$filename_jobrequests" 2>/dev/null)
    # 更新検知
    if [ "$current_mtime" != "$last_mtime" ]; then
      echo "Detected update in $filename_jobrequests"
      last_mtime=$current_mtime
      count=0
      # ★サブシェル回避版
      while IFS= read -r dir; do
        [ -z "$dir" ] && continue
        (
          cd "$dir" || {
            echo "Failed to enter: $dir" >&2
            exit 1
          }
          echo "Processing directory: $(pwd)"

          current_dir=$(pwd)

          # =====================
          # Fluid
          # =====================
          cd ${DIR_FLUID}

          DIR_OUTPUT=("output_restart" "output_flow" "output_surface_flow")
          for d in "${DIR_OUTPUT[@]}"; do
            [ ! -e "$d" ] && mkdir "$d"
          done

          core_start=$(( ncpu_f * count ))
          core_end=$(( ncpu_f * (count+1) - 1 ))
          cpu_set=$(seq -s, $core_start $core_end)

          echo "CPU set: $cpu_set"

          $MPIP -np $ncpu_f --bind-to core --cpu-set "$cpu_set" ${PYTHON} ${LD_F} -f ${INP_F} --parallel > $LOG_F & #2>&1 &

          PID1=$!

          cd ${current_dir}

          # =====================
          # Optimization
          # =====================
          cd ${DIR_OPT}

          export OMP_NUM_THREADS=$ncpu_o
          $PYTHON $LD_O > $LOG_O & #2>&1 &
          
          PID2=$!

          cd ${current_dir}

          echo "Started processes: $PID1 $PID2"

          wait $PID1
          wait $PID2

        ) &  # ← 並列実行

        count=$((count+1))

      done < <(tail -n +2 "$filename_jobrequests")

      echo "Batch launched."

    fi
  fi

  sleep 2

done
