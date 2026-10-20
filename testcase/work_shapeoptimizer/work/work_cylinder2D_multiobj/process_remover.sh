#!/bin/bash

#pgrep -f /shapeoptimizer_preCICE_pilot.py | xargs
#pgrep -f /SU2_preCICE_FSI.py | xargs
#xargs echo <<< "$(pgrep -f /shapeoptimizer_preCICE_pilot.py) $(pgrep -f /SU2_preCICE_FSI.py)"

kill $(pgrep -f /shapeoptimizer_preCICE.py) $(pgrep -f /SU2_preCICE_OPT.py) $(pgrep -f borealis.py)
#kill $(pgrep -f borealis.py)
exit


