# Borealis

A framework for inverse problems and optimization: it searches the input parameters of an external
computer code, or of a simple function, so that the output comes close to reference data.

**Version 1.7.0.** On top of the PSO, ABC and Bayesian optimizers and their distributed runs with `mpi4py`,
it implements a **genetic algorithm** (NSGA-II for several objectives) and adds the **concurrent evaluation** of candidates for external codes that themselves run under MPI
(`PSO.num_parallel`): Borealis runs as a single process, starts each case with its own set of cores and waits
for them in threads, because a code started with `mpirun` cannot itself start `mpirun`. It also fixes the problems
that silently corrupted the answer -- `maximize` ignored by most adapters, NaN objectives taking over the leader,
the factor of `timeunit: hour`, the time matching that wrapped round to the end of the reference data, unchecked
failures of the external code, the broken default path -- and adds a check of the configuration keys, a random seed
(`optimizer.seed`), unit and end-to-end tests (`tests/`) and continuous integration on GitHub Actions.
What is still open is tracked as numbered known issues in a list kept outside the repository, and the documents
refer to them by number ("known issue 7"). The changes are listed in `CHANGELOG.md`.

**This file is the overview.** The detail -- what each method computes, how the parallel runs work, what it
was measured to do and where it stops -- is in the report under `report/` (PDF, English and Japanese), and
every key of the configuration file is listed in `report/borealis_config_ja.pdf` (in Japanese).

![Optimization process for estimating input heat flux in heat conduction analysis.](figure/optimization_heatcond_erf.gif)

- [What it is](#what-it-is)
- [What it can do](#what-it-can-do)
- [Install](#install)
- [Run a case](#run-a-case)
- [Output and tools](#output-and-tools)
- [Verification](#verification)
- [Documents](#documents)


# What it is

`Borealis` treats the code to be fitted as a black box. An **adapter** runs it: it copies a template case,
writes the parameters into the control file, starts the code, reads its output and returns the difference
from the reference data as the objective function. An **optimizer** proposes the parameters and calls the
adapter. The two are independent, and one YAML file, `borealis.yml`, selects the combination:

```yaml
adapter:
  kind_adapter: tacode          # which code is driven
optimizer:
  kind_optimizer: PSO           # PSO, ABC, GA or Bayesian_optimization
parameter_optimized:
  boundary:                     # the parameters and their bounds
    - name: '# Initial velocity'          # the line of the control file to rewrite
      component:
        - {type: longitude, bound_min: 4240, bound_max: 4280}
        - {type: latitude,  bound_min: 5990, bound_max: 6030}
        - {type: altitude,  bound_min: -14,  bound_max: -10}
    - name: '# Density factor opimized'
      component:
        - {type: lower_bound_0,   bound_min: 0.5, bound_max: 1.5}
        - {type: lower_bound_405, bound_min: 0.5, bound_max: 1.5}
        # ...
PSO:
  num_particle: 20
  num_optiter: 50
  ...
tacode:                         # settings of the adapter: template, control file, run script, ...
  ...
```


# What it can do

| | what is there | detail |
|---|---|---|
| **Optimizers** | particle swarm optimization (PSO), with an archive of non-dominated solutions for several objectives; artificial bee colony (ABC); a real-coded genetic algorithm (GA: SBX crossover, polynomial mutation and the survivor selection of NSGA-II, so it is NSGA-II for several objectives); Bayesian optimization (Gaussian process with EI, PI or UCB) through bayesian-optimization | report, "Optimization methods" |
| **Parallel** | PSO, ABC and GA share the candidates among MPI processes (`mpirun -n N`) for serial external codes; PSO, GA and ABC evaluate candidates concurrently in threads (`num_parallel`) for external codes that run under MPI, each case bound to its own cores | report, "Parallelization" |
| **Adapters** | Tacode (trajectory, Python and Fortran versions), heat conduction, SU2 + preCICE shape optimization, cage, an analytic test function, a template for any external code, a slot for your own | table below |
| **Constraints** | a penalty outside the bounds; for shape optimization a penalty on the change of surface area and on failed runs | `report/borealis_config_ja.pdf` |
| **Output** | Tecplot ASCII histories of all candidates and of the best (the archive), with an ID that points to the case directory of every evaluation | report, "Output" |

Adapters (`adapter.kind_adapter`):

| `kind_adapter` | module | description |
| --- | --- | --- |
| `simple_function` | `src/adapter_template/adapter_simple_function.py` | analytic test function (shifted sphere functions); minimal template |
| `example_externalcode` | `src/adapter_template/adapter_example_externalcode.py` | complete template for driving an external program |
| `tacode` | `src/adapter_tacode/` | trajectory code `Tacode` (atmospheric density from orbit data) |
| `heatcond` | `src/adapter_heatcond/` | heat conduction (heat flux from temperature histories) |
| `shapeoptimizer` | `src/adapter_shapeoptimizer/` | shape optimization with SU2 and preCICE (`src_interface/`) |
| `cage` | `src/adapter_cage/` | cage analysis |
| `user` | `src/hidden_adapter_user/adapter_user.py` | slot for a user-defined adapter |

To add an adapter, copy a template in `src/adapter_template/`, implement `__init__`, `initial_settings`,
`reference_data_setting` and `objective_function`, and add its name to the dispatch in `src/borealis.py`.


# Install

```console
git clone https://github.com/ytakahashi3123/borealis.git
```

Requires Python (>= 3.9) with numpy (>= 1.22.3), PyYAML (>= 5.3.1) and mpi4py (>= 3.0.3);
[bayesian-optimization](https://github.com/bayesian-optimization/BayesianOptimization) (>= 3.0) only for
Bayesian optimization. `mpi4py` is imported in every run, also serial ones.

```console
python3 -m pip install numpy pyyaml mpi4py bayesian-optimization
```

Up to 1.6 Bayesian optimization used GPyOpt, which is no longer maintained and does not install with numpy 2.
The settings keep their names (`acquisition_type`, `initial_design_numdata`, `num_optiter`, ...); the GPyOpt-only
options (other surrogate models, the MCMC acquisitions, the acquisition plot) are gone.


# Run a case

`Borealis` reads `borealis.yml` from the working directory, so a case is run from inside its directory:

```console
cd testcase/work_simple_function
python3 <repository>/src/borealis.py
```

A file elsewhere is given with `-file path/to/borealis.yml`. Each case in `testcase/` has a `run_borealis.sh`
that wraps the command. The cases recommended for a first run are `testcase/work_simple_function`
(no external code) and `testcase/work_example_externalcode/work/work_curve` (a minimal external program).

**Choose the parallel mode by the external code:**

- the external code is **serial** -- start Borealis with MPI; each rank runs its share of the candidates,
  and the code it starts inherits that rank's core (PSO, ABC and GA):

  ```console
  mpirun -n 8 python3 <repository>/src/borealis.py
  ```

- the external code **runs under MPI itself** -- start Borealis **without** `mpirun` and set
  `PSO.num_parallel`; each case gets `num_cpu_per_case` cores, passed to its run script as
  `BOREALIS_CPU_SET` for `mpirun --cpu-set` (now PSO with `shapeoptimizer`). The run script must not return
  before the computation ends.

**`<optimizer>.result_dir` and `<adapter>.work_dir` are removed and recreated at start-up.** Do not point them at
results you want to keep. Give the template and the reference data with `directory_path_specify: manual` and
`manual_path`.

Unknown or obsolete keys in `borealis.yml` are reported as warnings at start-up (they do not stop the run, so
read the warnings); `report/borealis_config_ja.pdf` lists every key that is read. `optimizer.seed` fixes the
random numbers, so that a serial run gives the same answer every time. `maximize: True` works only with adapters
that apply the sign themselves (`shapeoptimizer`, `simple_function`); with an adapter
that returns an error to be minimized it stops the run. When the external code fails (a non-zero exit status or
no result file), the evaluation gets the value `parameter_optimized.value_nonfinite` (default 1e30).


# Output and tools

The results are written as Tecplot ASCII into `<optimizer>.result_dir`: `filename_output` holds every candidate
at every step, `filename_global` the archive (PSO) or the best (ABC) of every step. The case directory of every
evaluation stays under `<adapter>.work_dir`. Utilities independent of the optimization loop are in `src_helper/`,
each driven by its own YAML file in the working directory:

| tool | what it does |
| --- | --- |
| `pickup_optimal_result` | extracts the optimal solution from the history |
| `delete_nonoptimal_solution` | deletes the case directories of non-optimal solutions |
| `make_history_animation` | animation of the optimization history |
| `make_image_optimal_result` | images of the optimal result |
| `align_data_regular_intervals` | resamples data at regular intervals |
| `extract_referencedata_from_files` | builds reference data from a set of files |
| `calculate_time_difference` | time differences between data sets |
| `set_template_path` | rewrites template paths in configuration files |


# Tests and verification

```console
python3 -m pytest tests          # unit and end-to-end tests (about 15 s; the MPI tests need mpirun)
cd report
make verify                      # the verification cases of the report, with a fixed random seed (seconds)
make figure                      # the figures of the report
make                             # the PDFs
```

`python3 -m pytest tests` runs 42 tests; those of Bayesian optimization are skipped where bayesian-optimization
is not installed. `tests/` checks the tools shared by all adapters (time units, paths, the time matching, starting an external code),
the configuration check, PSO, ABC, GA and Bayesian optimization end to end (convergence, reproducibility, concurrent
evaluation, maximization, two objectives), the distributed runs under MPI and the concurrent evaluation of `shapeoptimizer` with a dummy
external code. GitHub Actions (`.github/workflows/ci.yml`) runs the syntax check, the tests and the verification
cases with Python 3.9 and 3.12 on every push and pull request.

`report/verification/` holds cases on the shifted sphere function in five dimensions, whose solution is known:
PSO with one objective (exact minimum 0), PSO with two objectives (exact Pareto front
`sqrt(f1) + sqrt(f2) = 2 sqrt(5)`), GA with one and two objectives, ABC and Bayesian optimization. With the same seed they give the same answer bit for bit. The report
shows the results with figures, together with the measured speed of the concurrent evaluation with a dummy MPI
program and with SU2 + preCICE.


# Documents

| file | contents |
|---|---|
| `report/borealis_report_en.pdf`, `borealis_report_ja.pdf` | the detailed report: problem setting, structure, the equations of the methods as written in the source, parallelization, verification against exact solutions with figures, an application (English and Japanese, the same document) |
| `report/borealis_config_ja.pdf` | every key of the configuration file, with defaults and the keys that are not read (in Japanese) |
| `report/README.md` | how the report and its figures are rebuilt (in Japanese) |
| `CHANGELOG.md` | what changed |
| `notes/` | the code review of 2026-08-30 and other notes (in Japanese) |


# Contact

Yusuke Takahashi, Hokkaido University

ytakahashi@eng.hokudai.ac.jp


# References

- Yusuke Takahashi, Masahiro Saito, Nobuyuki Oshima, and Kazuhiko Yamada, "Trajectory Reconstruction for Nanosatellite in Very Low Earth Orbit Using Machine Learning," Acta Astronautica 194: 301–308, 2022. https://doi.org/10.1016/j.actaastro.2022.02.010
- Tomoki Sakai and Yusuke Takahashi, "Atmospheric density estimation in very low Earth orbit based on nanosatellite measurement data using machine learning," Aerospace Science and Technology, Volume 153, 2024. https://doi.org/10.1016/j.ast.2024.109418
