# Analysis condition ----------------------------
.true.     # Initial:".true.", Restart:".false."
1          # Number of node (MPI) for parallel
1          # Number of thread (OpenMP) for parallel
2          # Atmosphere model (1: Direct input, 2: File input)
1          # Density factor model (1: Direct input, 2: File input) -- PCHIP補間はtacode実行前のPythonスクリプトで大気テーブルに焼き込み済みなのでUniform(factor=1.0)固定
2          # Aerodynamic model (1: Direct input, 2: File input)
1          # External force model (1: Direct input, 2: File input)
2          # Time integration (1:Euler, 2:Runge-Kutta)
# Satellite parameter -------------------------- (ISS approx., ref: tacode work/iss_orbit/orbit.ctl)
4.20e5             # Mass, kg (ISS approx., ~420 t)
2.2e0              # Drag coefficient
1200.e0            # Characteristic aream, m2
20.0e0             # Characteristic length, m
1                  # Coordinate system model (1:Geodetic, 2:Cartesian)
-179.1208113957, 0.0000170734, 417156.541931       # Initial coordinate, 1:Long.(deg) 2: Lat.(deg), 3:Alt.(m)
4258.762704, 6009.832762, -12.211875 # Initial velocity, m/s, (Direction--> 1:Long, 2:Lati, 3:Alti; SGP4速度をECEF/ENU変換した厳密値)
200000              # Number of memory array
# Physical constants (Planet) ----------------------
6.67408e-11         # Gravitational constant, M.m2/kg2
5.9723662e+24 #5.9722e+24          # Planet mass (Earth), kg
6.3781370e+6        # Planet radius on Equator, m
3.35281066474e-3       # Ellipticity
7.292115e-5         # rotation rate, rad/s
1.082629e-3         # dynamic form factor (J2) for potential calculation
-2.5356e-6            # J3
-1.62336e-6            # J4
# Atmosphere model (constant) ----------------------
1.0e-9               # Density, kg
300.e0               # Temperature, K
1.0                  # Factor for atmospheric density
5                    # Number of density factor case (PCHIP補間の制御点数。apply_pchip_density_factor.pyが読む)
0, 405, 420, 435, 450          # Lower bound of altitude, km (PCHIP補間の制御点。ISS pass altitude range: 414.7-440.8km)
1, 1, 1, 1, 1             # Density factor opimized (PCHIP補間の制御点における係数値。PSOが最適化)
25000               # Number of memory array
7                   # Number of parameter
"Height", "km"      # Parameters
"O", "cm-3"
"N2", "cm-3"
"O2", "cm-3"
"Mass_density", "g/cm-3"
"Temperature_neutral", "K"
"N", "cm-3"
# External force model ----------------------------
0.e0, 0.e0, 0.e0     # Delta V, m/s (Long., Lat., and Height)
25000                # Number of memory array
# Calculation properties --------------------------
1.0e0                # Time step for time integration
8.64e3                # Maximum time,s
1.e0                 # Relaxation parameter (not used here)
10000                 # Maximum iteration number
10000                 # Every iteration number to display calculation state
10000                 # Every iteration number to output data
# File names --------------------------------------
'./database/atmospheremodel_baseline/atmospheremodel'   # Atmosphere file
'./database/density_factor/density_factor'   # Density factor file
'./database/aerodynamic_dsmc/aerodynamic'               # Aerodynamic file
'./database/externalforce'               # External-force file
'restart'            # Restart file
'trajectory'         # Result file for data process
'none'            # Tecplot file
'none'         # FVP file
'none'           # geodetic system file (GPX)
