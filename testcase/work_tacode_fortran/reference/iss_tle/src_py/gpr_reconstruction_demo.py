"""
gpr_reconstruction_demo.py

ブログ紹介記事向けの説明図を作るためのデモスクリプトです。
論文中で使われている実データ（EGGのGNSSデータ等）は一切使用せず、
公開されているTLE（二行軌道要素）から

  1. SGP4によって「真の」連続軌道（高度の時系列）を計算し、
  2. そこから間欠的（歯抜け）にサンプリングして「模擬GNSSデータ」を作り、
  3. ガウス過程回帰（GPR）でそれを連続軌道に再構成する

という一連の流れを再現します。論文Fig.2（EGGの軌道再構成）のイメージを
ダミーデータで説明するための図を出力することが目的です。

必要ライブラリ:
    pip install skyfield scikit-learn matplotlib numpy --break-system-packages

TLEについて:
    ここではデモ用に古いISSのTLEを1つ埋め込んでいます。
    実際に使う場合は Celestrak (https://celestrak.org/) などから
    好きな衛星の最新TLEを取得し、TLE_LINE1 / TLE_LINE2 を差し替えてください。
    （本スクリプトはあくまで「歯抜けデータ→GPR再構成」の流れを説明するための
    ものなので、対象衛星やTLEの新旧は問いません。）
"""

import numpy as np
import matplotlib.pyplot as plt
from skyfield.api import EarthSatellite, load, wgs84
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel as C

# ----------------------------------------------------------------------
# 0. 設定パラメータ
# ----------------------------------------------------------------------
RANDOM_SEED = 42

DURATION_HOURS = 6.0          # 何時間ぶんの軌道を扱うか
DT_TRUTH_S = 10.0             # 「真の」高分解能軌道のサンプリング間隔 [s]

BURST_DURATION_S = 90         # 1回のデータ取得バーストの長さ [s]
GAP_DURATION_S = 900          # データが取れない空白期間の長さ [s]
SAMPLE_INTERVAL_S = 20        # バースト内でのサンプリング間隔 [s]
GNSS_NOISE_STD_KM = 0.15      # GNSS測位誤差を模した標準偏差 [km]

# デモ用TLE（ISS, あくまで一例。実データではなくSGP4伝播による模擬軌道として使用）
TLE_NAME = "ISS (ZARYA)"
TLE_LINE1 = "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9994"
TLE_LINE2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.49309239429866"


def propagate_truth(satellite, ts, duration_hours, dt_seconds):
    """SGP4により「真の」高度の連続時系列を計算する。"""
    epoch = satellite.epoch
    n_points = int(duration_hours * 3600 / dt_seconds)
    t_seconds = np.arange(n_points) * dt_seconds
    times = ts.tt_jd(epoch.tt + t_seconds / 86400.0)

    geocentric = satellite.at(times)
    subpoint = wgs84.subpoint(geocentric)
    altitude_km = subpoint.elevation.km

    return t_seconds, altitude_km


def make_intermittent_samples(t_seconds, altitude_km_true, rng,
                               burst_duration_s, gap_duration_s,
                               sample_interval_s, noise_std_km):
    """間欠的（歯抜け）な模擬GNSSデータを生成する。

    通信リンクの制約でデータがバースト的にしか得られない状況
    （例えばIridium衛星通信経由の衛星など）を模したサンプリングパターン。
    """
    gnss_time_list = []
    t = 0.0
    take_burst = True
    t_max = t_seconds[-1]

    while t < t_max:
        if take_burst:
            burst_times = np.arange(t, min(t + burst_duration_s, t_max), sample_interval_s)
            if burst_times.size > 0:
                gnss_time_list.append(burst_times)
            t += burst_duration_s
        else:
            t += gap_duration_s
        take_burst = not take_burst

    gnss_time = np.concatenate(gnss_time_list)

    # 真値を線形補間し、観測ノイズを付加する
    altitude_true_interp = np.interp(gnss_time, t_seconds, altitude_km_true)
    gnss_alt = altitude_true_interp + rng.normal(0.0, noise_std_km, size=gnss_time.shape)

    return gnss_time, gnss_alt


def fit_gpr(gnss_time, gnss_alt, t_pred, noise_std_km):
    """ガウス過程回帰で連続軌道を再構成する。"""
    X_train = gnss_time.reshape(-1, 1)
    y_train = gnss_alt

    kernel = (
        C(1.0, (1e-2, 1e3))
        * RBF(length_scale=300.0, length_scale_bounds=(10.0, 5000.0))
        + WhiteKernel(noise_level=noise_std_km**2, noise_level_bounds=(1e-4, 1.0))
    )

    gpr = GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=5)
    gpr.fit(X_train, y_train)

    X_pred = t_pred.reshape(-1, 1)
    alt_pred, alt_std = gpr.predict(X_pred, return_std=True)

    return alt_pred, alt_std, gpr


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    ts = load.timescale()
    satellite = EarthSatellite(TLE_LINE1, TLE_LINE2, TLE_NAME, ts)

    # 1. 真の連続軌道（高度）
    t_seconds, altitude_km_true = propagate_truth(
        satellite, ts, DURATION_HOURS, DT_TRUTH_S
    )

    # 2. 間欠的な模擬GNSSデータ
    gnss_time, gnss_alt = make_intermittent_samples(
        t_seconds, altitude_km_true, rng,
        BURST_DURATION_S, GAP_DURATION_S, SAMPLE_INTERVAL_S, GNSS_NOISE_STD_KM,
    )

    # 3. GPRによる連続軌道の再構成
    alt_pred, alt_std, _ = fit_gpr(gnss_time, gnss_alt, t_seconds, GNSS_NOISE_STD_KM)

    # 4. 可視化
    fig, ax = plt.subplots(figsize=(9, 5))

    t_min = t_seconds / 60.0
    gnss_min = gnss_time / 60.0

    ax.plot(t_min, altitude_km_true, color="gray", lw=1.0,
            label="Ground truth (SGP4 propagation, dummy satellite)")
    ax.scatter(gnss_min, gnss_alt, color="black", s=12, zorder=5,
               label="Simulated intermittent GNSS-like samples")
    ax.plot(t_min, alt_pred, color="tab:blue", lw=1.5,
            label="GPR reconstruction")
    ax.fill_between(t_min, alt_pred - 2 * alt_std, alt_pred + 2 * alt_std,
                     color="tab:blue", alpha=0.2, label="95% confidence interval")

    ax.set_xlabel("Time [min]")
    ax.set_ylabel("Altitude [km]")
    ax.set_title("Dummy example: intermittent GNSS-like data & GPR reconstruction")
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()

    out_path = "gpr_reconstruction_demo.png"
    fig.savefig(out_path, dpi=200)
    print(f"Saved figure to: {out_path}")
    print(f"Ground truth points : {len(t_seconds)}")
    print(f"Simulated GNSS points: {len(gnss_time)}")


if __name__ == "__main__":
    main()
