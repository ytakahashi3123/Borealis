# orbital（全アダプタ・手法の基底のクラス）の道具のテスト
import numpy as np
import pytest

from orbital.orbital import orbital


@pytest.fixture(scope="module")
def orbit():
    return orbital()


def test_timeunit(orbit):
    # day は恒星日、hour は 3600 秒（以前は 1436.07 になっていた。既知の問題 3）
    assert orbit.set_timeunit("day") == pytest.approx(86164.0989, abs=1e-3)
    assert orbit.set_timeunit("hour") == 3600.0
    assert orbit.set_timeunit("min") == 60.0
    assert orbit.set_timeunit("sec") == 1.0
    with pytest.raises(ValueError):
        orbit.set_timeunit("week")


def test_directory_path(orbit, tmp_path):
    # default は src/orbital/ からの相対パス（以前は区切りなしで連結していた。既知の問題 26）
    path = orbit.get_directory_path("default", "../../testcase", "unused")
    assert path.endswith("testcase") and "orbital.." not in path
    assert orbit.get_directory_path("manual", "unused", str(tmp_path)) == str(tmp_path)
    with pytest.raises(ValueError):
        orbit.get_directory_path("typo", "x", "y")


def _bracket_loop(x_ref, x):
    # 以前のアダプタの対応点の探索（x_ref[m] >= x となる最初の m）
    for m in range(len(x_ref)):
        if x_ref[m] >= x:
            return m
    return None


def test_find_bracket_index_matches_loop(orbit):
    # 範囲の内側では、以前のループと同じ m を返す（m = 0 の端は除く。以前はそこで配列の末尾へ回り込んだ）
    rng = np.random.default_rng(0)
    x_ref = np.sort(rng.uniform(0.0, 10.0, 200))
    x = rng.uniform(x_ref[0], x_ref[-1], 1000)
    m, valid = orbit.find_bracket_index(x_ref, x)
    assert valid.all()
    expected = np.array([_bracket_loop(x_ref, xi) for xi in x])
    inner = expected > 0
    assert np.array_equal(m[inner], expected[inner])
    # 端の点は m = 1 で、内挿の重みは 0（= x_ref[0] の値）
    m0, valid0 = orbit.find_bracket_index(x_ref, x_ref[0])
    assert valid0[0] and m0[0] == 1


def test_find_bracket_index_outside(orbit):
    # 範囲の外は valid = False（以前は末尾の点や前の点と黙って比べていた。既知の問題 6）
    x_ref = np.array([0.0, 1.0, 2.0, 3.0])
    m, valid = orbit.find_bracket_index(x_ref, np.array([-0.1, 0.0, 1.5, 3.0, 3.1]))
    assert valid.tolist() == [False, True, True, True, False]
    assert m.min() >= 1 and m.max() <= len(x_ref) - 1


def test_geodetic_round_trip(orbit):
    # 直交座標 → 測地座標の分岐は要素ごとに選ぶ（以前は 1 つでも正なら全要素を同じ分岐で計算した。既知の問題 14）
    radius, ellipticity = 6378137.0, 1.0/298.257223563
    lon = np.radians(np.array([10.0, -120.0, 45.0, 170.0]))
    lat = np.radians(np.array([35.0, -60.0, 0.5, -0.5]))
    alt = np.array([400.0e3, 200.0e3, 1.0e3, 10.0e3])
    cart = orbit.convert_geodetic_cartesian(radius, ellipticity, [lon, lat, alt])
    lon2, lat2, alt2 = orbit.convert_cartesian_geodetic(radius, ellipticity, cart)
    assert np.allclose(lon2, lon, atol=1e-9)
    assert np.allclose(lat2, lat, atol=1e-9)
    assert np.allclose(alt2, alt, atol=1e-3)


def test_sanitize_score(orbit):
    # NaN・無限大は置き換え、長さの食い違いは止める（既知の問題 2）
    score = orbit.sanitize_score(np.array([np.nan, 1.0]), 2, 1.0e30, "TEST")
    assert score.tolist() == [1.0e30, 1.0]
    assert orbit.sanitize_score(np.inf, 1, 5.0, "TEST").tolist() == [5.0]
    with pytest.raises(ValueError):
        orbit.sanitize_score(np.array([1.0, 2.0]), 1, 1.0e30, "TEST")


class _AdapterWithoutSign:
    def objective_function(self, x, *args):
        return np.atleast_1d(0.0)


class _AdapterWithSign(_AdapterWithoutSign):
    flag_apply_sign = True


def test_check_maximize_supported(orbit):
    # 符号を掛けないアダプタで maximize を指定したら止める（以前は黙って最小化を続けた。既知の問題 1）
    orbit.check_maximize_supported(_AdapterWithoutSign().objective_function, False, "TEST")
    orbit.check_maximize_supported(_AdapterWithSign().objective_function, [True, False], "TEST")
    with pytest.raises(SystemExit):
        orbit.check_maximize_supported(_AdapterWithoutSign().objective_function, True, "TEST")


def test_run_external_code(orbit, tmp_path):
    # 終了ステータスと結果ファイルを見る。古い結果ファイルは起動の前に消す（既知の問題 7）
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\necho ok > result.dat\n")
    script.chmod(0o755)
    (tmp_path / "result.dat").write_text("stale\n")
    assert orbit.run_external_code("./run.sh", str(tmp_path), "result.dat")
    assert (tmp_path / "result.dat").read_text() == "ok\n"
    script.write_text("#!/bin/sh\nexit 3\n")
    assert not orbit.run_external_code("./run.sh", str(tmp_path), "result.dat")
    assert not (tmp_path / "result.dat").exists()


def test_run_external_code_hides_mpi_environment(orbit, tmp_path):
    # mpi4py を読むと C の側に OMPI_*/PMIX_* が足される。子に継がせない（既知の問題 19）
    pytest.importorskip("mpi4py")
    from mpi4py import MPI  # noqa: F401  (シングルトンの MPI_Init)
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\nenv > env.txt\n")
    script.chmod(0o755)
    assert orbit.run_external_code("./run.sh", str(tmp_path), "env.txt")
    names = [line.split("=", 1)[0] for line in (tmp_path / "env.txt").read_text().splitlines()]
    assert not [n for n in names if n.startswith(("OMPI_MCA_ess", "PMIX_RANK", "PMIX_NAMESPACE"))]
