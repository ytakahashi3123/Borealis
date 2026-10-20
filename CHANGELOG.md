# Changelog

What changed in each release of Borealis, newest first, in the spirit of
[Keep a Changelog](https://keepachangelog.com/). Each release is a git tag (`vX.Y.Z`), and the
version is also in `src/borealis.py`. **Changes that alter the answer of an existing setup are marked
"answers change".** Known issues are referred to by number.

The detailed development log -- how each decision was reached and the measurements behind it --
is kept outside the repository.

## [1.7.0] - 2026-10-20

The previous public release was v1.5.0; the 1.6 series was not released, and its changes are included here.

### Added

- Genetic algorithm (`kind_optimizer: GA`): a real-coded GA with tournament selection, SBX crossover, polynomial
  mutation and the survivor selection of NSGA-II. With one objective it is an elitist GA, with several it is NSGA-II.
- Concurrent evaluation (`num_parallel` of PSO, GA and ABC) for external codes that run under MPI themselves: Borealis
  runs as one process, and `shapeoptimizer` starts each case on its own cores (`num_cpu_per_case`, `cpu_assignment`,
  passed to the run script as `BOREALIS_CPU_SET`). A rank started by `mpirun` cannot start `mpirun` itself
  (known issue 18).
- A check of the configuration keys at start-up: unknown, obsolete and unread keys are reported as warnings.
- `optimizer.seed` for reproducible runs; `parameter_optimized.value_nonfinite` for failed or non-finite evaluations.
- Multi-objective PSO with a Pareto archive (`maximize` as a list, convergence by `windowsize_residual`,
  `tolerance_residual`, `windowsize_archive` and `tolerance_archive`).
- Tests (`tests/`, pytest) and continuous integration on GitHub Actions.
- A detailed report in Japanese and English and a reference of the configuration keys (`report/`), with
  verification cases on functions whose solution is known.
- Example cases: atmospheric density from the orbit of the ISS (`testcase/work_tacode_fortran`) and
  shape optimization of a cylinder with two objectives (`testcase/work_shapeoptimizer`).

### Changed

- Bayesian optimization now uses bayesian-optimization (3.x) instead of GPyOpt, which is no longer maintained.
  The settings keep their names; options only GPyOpt had are gone. **Answers change.**
- `maximize: True` stops the run with an adapter that does not apply the sign (known issue 1); up to 1.6 it was
  silently ignored.
- A failed external code (non-zero exit status or no result file) gives `value_nonfinite` instead of the error of
  an old file (known issue 7).
- PSO divides the particles evenly among MPI processes (known issue 9). **Answers change** under MPI.
- ABC writes the best so far to `output_global.dat` (known issue 16), and its convergence check skips the first
  `windowsize_residual` steps (known issue 5). **Answers change** when the check stopped early.
- `shapeoptimizer` starts the external code itself instead of through a job-request file, and accepts one objective
  (drag) as well as two (drag and moment).
- The configuration keys `ABC.visit_limit` and `ABC.num_onlook_bees` replace the misspelled ones, which are still read.
- The NinjaSat case is no longer tracked.

### Fixed

- `timeunit: hour` used 1436.07 s instead of 3600 s (known issue 3). **Answers change.**
- The time matching of `tacode` and `example_externalcode` wrapped round to the end of the reference data for
  points outside it; such points are no longer compared (known issue 6). **Answers change.**
- A NaN objective could take over the PSO leader (known issue 2).
- `directory_path_specify: default` built a path that did not exist (known issue 26).
- Updates of the onlooker bees of ABC were lost across MPI processes. **Answers change** under MPI.
- `exit()` under MPI left the other ranks waiting (known issue 8); the dispatch of `borealis.py` referred to
  modules that did not exist.
- The reference of the ISS case used calendar days where Borealis expects sidereal days, and the atmosphere table
  did not cover the altitude of the ISS. **Answers change** for that case.

### Removed

- The GPyOpt dependency, the job-request launcher of `shapeoptimizer` and the sequential cylinder template.

Earlier releases are listed on the [releases page](https://github.com/ytakahashi3123/borealis/releases).
