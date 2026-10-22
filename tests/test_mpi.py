# MPI での分担のテスト（mpirun がある環境だけ）
import os
import shutil

import numpy as np
import pytest

from conftest import read_global, run_borealis, sphere_config

MPIRUN = shutil.which("mpirun") or shutil.which("mpirun.openmpi")
pytestmark = pytest.mark.skipif(MPIRUN is None, reason="mpirun is not available")


def _mpi_prefix(num_process):
    prefix = [MPIRUN, "-n", str(num_process)]
    if "openmpi" in os.path.realpath(MPIRUN) or os.path.basename(MPIRUN).endswith("openmpi"):
        prefix.insert(1, "--oversubscribe")
    return prefix


@pytest.mark.parametrize("kind_optimizer", ["PSO", "ABC", "GA"])
def test_mpi_run_completes(workdir, kind_optimizer):
    # 粒子 13 個を 3 プロセスに分ける（均等でない数。以前の PSO は余りを最後のランクに載せた。既知の問題 9）
    if kind_optimizer == "PSO":
        config = sphere_config("PSO", num_particle=13, num_optiter=20)
    elif kind_optimizer == "GA":
        config = sphere_config("GA", num_population=13, num_generation=20)
    else:
        config = sphere_config("ABC", num_employ_bees=13, num_onlook_bees=7, num_optiter=20)
    rc, out = run_borealis(workdir, config, command_prefix=_mpi_prefix(3))
    assert rc == 0, out
    data = read_global(workdir, f"result_{kind_optimizer}")
    assert len(data) > 0 and np.isfinite(data[:, 2]).all()


def test_mpi_abc_two_objectives(workdir):
    # 多目的 ABC: 各ランクの評価を集めて、全ランクが同じアーカイブを持つ（違えば収束の判定で止まらない）
    config = sphere_config("ABC", num_objectives=2, maximize=[False, False], num_employ_bees=13, num_onlook_bees=7,
                           num_optiter=20, num_archive=10)
    rc, out = run_borealis(workdir, config, command_prefix=_mpi_prefix(3))
    assert rc == 0, out
    data = read_global(workdir, "result_ABC")
    last = data[data[:, 0] == data[:, 0].max()]
    assert 0 < len(last) <= 10 and np.isfinite(last[:, 2:4]).all()
