#!/bin/bash

#source ~/.bashrc_intel
#source /opt/intel/oneapi/setvars.sh

#TACODE_HOME=/opt/tacode/tacode-v1.2.1/bin
TACODE_HOME=$HOME/source/tacode/tacode-v1.2.1/bin
LD=$TACODE_HOME/tacode
LOG=log_tacode

$LD > $LOG
