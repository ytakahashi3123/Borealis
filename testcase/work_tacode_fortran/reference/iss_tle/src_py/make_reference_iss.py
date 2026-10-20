#!/usr/bin/env python3
"""
make_reference_iss.py

Borealis (testcase/work_tacode_fortran) 用のリファレンス軌道データを、
実際のISSのTLE（二行軌道要素）から作成するスクリプト。

処理の流れ:
  1. ISSのTLEをSGP4で伝播し、地心慣性座標(TEME)での位置・速度を得る。
  2. GMST回転でECEF（地球固定座標系）に変換し、WGS84測地座標
     （経度・緯度・高度）に変換する（tacode-Fortranの入出力系に合わせる）。
  3. 得られた「真の」連続軌道から間欠的（歯抜け）にサンプリングし、
     GNSS計測を模したノイズ付きの疎なデータセットを作る。
  4. ガウス過程回帰（GPR）で経度・緯度・高度をそれぞれ時間の関数として
     再構成し、各点の平均・標準偏差を推定する。
  5. Borealisのtacodeアダプタが読み込む形式
     (trajectory_longitude.dat, trajectory_latitude.dat, trajectory_altitude.dat:
      各行 "time[s]  mean  std"、1列目はUTC年初からの経過秒)で出力する。

実行方法:
  $HOME/venvs/myenv/bin/python3 make_reference_iss.py

必要ライブラリ: numpy, scikit-learn, sgp4
  pip install numpy scikit-learn sgp4

TLEの更新:
  以下のTLE_LINE1/TLE_LINE2は https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE
  から取得した実際のISSの軌道要素（取得日: 2026-08-23）。最新のTLEに差し替えて
  再実行すれば、その時点のISS軌道でリファレンスデータを作り直せる。
"""

import os
import numpy as np
from sgp4.api import Satrec, jday
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel as C

# ----------------------------------------------------------------------
# 0. 設定パラメータ
# ----------------------------------------------------------------------
RANDOM_SEED = 42

# ISS (ZARYA) TLE, retrieved from Celestrak on 2026-08-23
TLE_NAME  = "ISS (ZARYA)"
TLE_LINE1 = "1 25544U 98067A   26234.50053383  .00009133  00000+0  17025-3 0  9997"
TLE_LINE2 = "2 25544  51.6331 331.8814 0007668  72.6488 287.5339 15.49570248582031"

DURATION_S   = 5600.0   # 伝播する時間長 [s] (ISSの軌道周期 約92.7分 に相当)
DT_TRUTH_S   = 1.0      # 「真の」高分解能軌道のサンプリング間隔 [s] (tacodeの時間刻みに合わせる)
DT_OUTPUT_S  = 5.0      # リファレンスデータとして出力する間隔 [s]

# GNSS的な間欠観測を模したサンプリングパターン
BURST_DURATION_S   = 90.0    # 1回のデータ取得バーストの長さ [s]
GAP_DURATION_S     = 600.0   # データが取れない空白期間の長さ [s]
SAMPLE_INTERVAL_S  = 20.0    # バースト内でのサンプリング間隔 [s]
NOISE_STD_POS_M    = 150.0   # GNSS測位誤差を模した標準偏差 [m] (水平・高度共通)

# WGS84 定数
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')


# ----------------------------------------------------------------------
# 1. TEME propagation and coordinate conversion
# ----------------------------------------------------------------------
def propagate_teme(tle_line1, tle_line2, duration_s, dt_s):
  """SGP4によりTEME座標系での位置・速度の時系列を計算する。"""
  sat = Satrec.twoline2rv(tle_line1, tle_line2)

  n_points = int(duration_s / dt_s) + 1
  t_seconds = np.arange(n_points) * dt_s

  # Epoch as Julian date (jd + fr)
  jd_epoch, fr_epoch = sat.jdsatepoch, sat.jdsatepochF

  r_teme = np.empty((n_points, 3))
  v_teme = np.empty((n_points, 3))
  for i, dt in enumerate(t_seconds):
    fr = fr_epoch + dt / 86400.0
    e, r, v = sat.sgp4(jd_epoch, fr)
    if e != 0:
      raise RuntimeError(f'SGP4 propagation error code {e} at t={dt}s')
    r_teme[i, :] = r  # km
    v_teme[i, :] = v  # km/s

  jd_ut1 = jd_epoch + fr_epoch + t_seconds / 86400.0

  # 年初(UTC)からの経過日数（day-of-year, 小数）を求める
  day_of_year = jday_to_dayofyear(jd_epoch, fr_epoch) + t_seconds / 86400.0

  return t_seconds, r_teme, v_teme, jd_ut1, day_of_year


def jday_to_dayofyear(jd, fr):
  """Julian date(jd+fr)から、UTC年初(1月1日 00:00 UTC)からの経過日数(小数)を求める。"""
  import datetime
  jd_total = jd + fr
  # Julian day 0 = 4713 BC Jan 1.5. Use Python's proleptic Gregorian calendar via
  # a well known epoch: JD 2440587.5 = 1970-01-01 00:00:00 UTC
  unix_seconds = (jd_total - 2440587.5) * 86400.0
  dt = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=unix_seconds)
  year_start = datetime.datetime(dt.year, 1, 1)
  return (dt - year_start).total_seconds() / 86400.0


def gmst_rad(jd_ut1):
  """GMST(グリニッジ平均恒星時)をラジアンで返す（簡易式、UT1≈UTCとして計算）。"""
  t = (jd_ut1 - 2451545.0) / 36525.0
  gmst_deg = (280.46061837
              + 360.98564736629 * (jd_ut1 - 2451545.0)
              + 0.000387933 * t**2
              - t**3 / 38710000.0)
  gmst_deg = np.mod(gmst_deg, 360.0)
  return np.deg2rad(gmst_deg)


def teme_to_ecef(r_teme, v_teme, jd_ut1):
  """TEME座標をGMST回転でECEF座標に変換する（極運動・章動は無視した簡易変換）。"""
  theta = gmst_rad(jd_ut1)
  cos_t = np.cos(theta)
  sin_t = np.sin(theta)

  x, y, z = r_teme[:, 0], r_teme[:, 1], r_teme[:, 2]
  r_ecef = np.empty_like(r_teme)
  r_ecef[:, 0] = cos_t * x + sin_t * y
  r_ecef[:, 1] = -sin_t * x + cos_t * y
  r_ecef[:, 2] = z

  return r_ecef


EARTH_ROTATION_RATE = 7.292115e-5  # rad/s (tacodeのorbit.ctlと同じ値を使用)


def teme_to_ecef_velocity(r_teme, v_teme, jd_ut1):
  """SGP4が返すTEME速度を、GMST回転を用いてECEF(地球固定系)相対速度に変換する。
  v_ecef = R(theta)*v_teme - omega x r_ecef  (地球自転による見かけの速度分を差し引く)"""
  theta = gmst_rad(jd_ut1)
  cos_t = np.cos(theta)
  sin_t = np.sin(theta)

  r_ecef = teme_to_ecef(r_teme, v_teme, jd_ut1)
  vx, vy, vz = v_teme[:, 0], v_teme[:, 1], v_teme[:, 2]

  v_rot = np.empty_like(v_teme)
  v_rot[:, 0] = cos_t * vx + sin_t * vy
  v_rot[:, 1] = -sin_t * vx + cos_t * vy
  v_rot[:, 2] = vz

  omega_cross_r = np.empty_like(r_ecef)
  omega_cross_r[:, 0] = -EARTH_ROTATION_RATE * r_ecef[:, 1]
  omega_cross_r[:, 1] = EARTH_ROTATION_RATE * r_ecef[:, 0]
  omega_cross_r[:, 2] = 0.0

  return v_rot - omega_cross_r


def ecef_velocity_to_enu(v_ecef, lon_deg, lat_deg):
  """ECEF速度を局所ENU(East, North, Up)成分に分解する（tacodeのInitial velocity, 1:Long,2:Lati,3:Altiに対応）。"""
  lon = np.deg2rad(lon_deg)
  lat = np.deg2rad(lat_deg)
  vx, vy, vz = v_ecef[:, 0], v_ecef[:, 1], v_ecef[:, 2]

  v_east  = -np.sin(lon) * vx + np.cos(lon) * vy
  v_north = -np.sin(lat) * np.cos(lon) * vx - np.sin(lat) * np.sin(lon) * vy + np.cos(lat) * vz
  v_up    =  np.cos(lat) * np.cos(lon) * vx + np.cos(lat) * np.sin(lon) * vy + np.sin(lat) * vz

  return v_east, v_north, v_up


def ecef_to_geodetic(r_ecef_m):
  """ECEF座標[m]からWGS84測地座標(経度[deg], 緯度[deg], 高度[m])へ変換する（反復法）。"""
  x, y, z = r_ecef_m[:, 0], r_ecef_m[:, 1], r_ecef_m[:, 2]
  lon = np.arctan2(y, x)

  p = np.sqrt(x**2 + y**2)
  lat = np.arctan2(z, p * (1.0 - WGS84_E2))
  for _ in range(6):
    sin_lat = np.sin(lat)
    n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sin_lat**2)
    alt = p / np.cos(lat) - n
    lat = np.arctan2(z, p * (1.0 - WGS84_E2 * n / (n + alt)))

  sin_lat = np.sin(lat)
  n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sin_lat**2)
  alt = p / np.cos(lat) - n

  return np.rad2deg(lon), np.rad2deg(lat), alt


def local_enu_velocity(t_seconds, lon_deg, lat_deg, alt_m):
  """測地座標の時系列を中心差分し、East/North/Up方向の物理速度[m/s]を求める。"""
  lat_rad = np.deg2rad(lat_deg)
  sin_lat = np.sin(lat_rad)
  n_radius = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sin_lat**2)          # prime vertical radius of curvature
  m_radius = WGS84_A * (1.0 - WGS84_E2) / (1.0 - WGS84_E2 * sin_lat**2)**1.5  # meridian radius of curvature

  dlon = np.gradient(np.unwrap(np.deg2rad(lon_deg)), t_seconds)
  dlat = np.gradient(lat_rad, t_seconds)
  dalt = np.gradient(alt_m, t_seconds)

  v_east  = (n_radius + alt_m) * np.cos(lat_rad) * dlon
  v_north = (m_radius + alt_m) * dlat
  v_up    = dalt

  return v_east, v_north, v_up


# ----------------------------------------------------------------------
# 2. Intermittent GNSS-like sampling
# ----------------------------------------------------------------------
def make_intermittent_samples(t_seconds, rng, burst_duration_s, gap_duration_s, sample_interval_s):
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
  # 開始・終了点は必ず観測点として含める（境界での外挿を避けるため）
  gnss_time = np.unique(np.concatenate([gnss_time, [t_seconds[0], t_seconds[-1]]]))
  return gnss_time


def fit_gpr(gnss_time, gnss_value, t_pred, noise_std, length_scale=300.0):
  X_train = gnss_time.reshape(-1, 1)
  y_train = gnss_value

  kernel = (
      C(1.0, (1e-3, 1e5))
      * RBF(length_scale=length_scale, length_scale_bounds=(10.0, 5000.0))
      + WhiteKernel(noise_level=max(noise_std**2, 1e-8), noise_level_bounds=(1e-10, 1e2))
  )

  gpr = GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=5, random_state=RANDOM_SEED)
  gpr.fit(X_train, y_train)

  mean, std = gpr.predict(t_pred.reshape(-1, 1), return_std=True)
  return mean, std


# ----------------------------------------------------------------------
# 3. Main
# ----------------------------------------------------------------------
def main():
  rng = np.random.default_rng(RANDOM_SEED)

  print(f'Propagating {TLE_NAME} via SGP4...')
  t_seconds, r_teme, v_teme, jd_ut1, day_of_year = propagate_teme(TLE_LINE1, TLE_LINE2, DURATION_S, DT_TRUTH_S)

  r_ecef_m = teme_to_ecef(r_teme, v_teme, jd_ut1) * 1000.0
  lon_deg, lat_deg, alt_m = ecef_to_geodetic(r_ecef_m)

  # Velocity: SGP4 gives v_teme directly (analytically consistent with r_teme),
  # so convert that to ECEF then to local ENU -- this is more accurate than
  # differentiating the geodetic position time series.
  v_ecef_ms = teme_to_ecef_velocity(r_teme, v_teme, jd_ut1) * 1000.0
  v_east, v_north, v_up = ecef_velocity_to_enu(v_ecef_ms, lon_deg, lat_deg)

  # Cross-check against the finite-difference estimate (diagnostic only)
  v_east_fd, v_north_fd, v_up_fd = local_enu_velocity(t_seconds, lon_deg, lat_deg, alt_m)
  print(f'  Altitude range: {alt_m.min()/1000.0:.3f} - {alt_m.max()/1000.0:.3f} km')
  print(f'  Initial coordinate: lon={lon_deg[0]:.6f} deg, lat={lat_deg[0]:.6f} deg, alt={alt_m[0]:.3f} m')
  print(f'  Initial velocity (SGP4-analytic): v_east={v_east[0]:.6f} m/s, v_north={v_north[0]:.6f} m/s, v_up={v_up[0]:.6f} m/s')
  print(f'  Initial velocity (finite-diff)   : v_east={v_east_fd[0]:.6f} m/s, v_north={v_north_fd[0]:.6f} m/s, v_up={v_up_fd[0]:.6f} m/s')
  print(f'  Difference (analytic - finite-diff): '
        f'{v_east[0]-v_east_fd[0]:+.6f}, {v_north[0]-v_north_fd[0]:+.6f}, {v_up[0]-v_up_fd[0]:+.6f} m/s')
  print(f'  Day-of-year at epoch (start): {day_of_year[0]:.6f}')
  print(f'  Day-of-year at end         : {day_of_year[-1]:.6f}')

  # Absolute time base used in the reference files.
  # IMPORTANT: Borealis's orbital.py defines 1 "day" (timeunit: day) as a SIDEREAL
  # day (duration_hour2day = 23.9344719177h => 86164.0989s), NOT a calendar day
  # (86400s). adapter_tacode divides this file's raw seconds column by that same
  # constant to reconstruct self.time_day_opt, and separately computes tacode's own
  # trajectory time_day_offset = (elapsed real seconds)/86164.0989 + target_time.
  # If this file's seconds column used 86400s/day instead, self.time_day_opt would
  # be offset from time_day_offset by ~0.27% of target_time (here ~0.64 day), which
  # pushes the reference day-of-year value entirely out of tacode's own day-of-year
  # range. evaluate_error's bracket search (`self.time_day_opt[m] >= time_day_offset[n]`)
  # then always matches at m=0 for every n (never finds a real bracket), so
  # `self.time_day_opt[m_opt-1]`/`self.altitude_opt[m_opt-1]` silently wrap around to
  # the *last* element of the array (Python negative-index aliasing) instead of
  # raising an error. The objective ends up interpolating against a bogus, nearly
  # time-invariant reference value instead of the true co-temporal one -- it can look
  # deceptively small (both endpoints happen to sit near the same ~417km altitude)
  # while never actually performing a real time-aligned comparison. Match Borealis's
  # sidereal-day constant here so the reference and tacode's own day-of-year stay
  # on the same footing.
  BOREALIS_DAY2SEC = 60.0 * 60.0 * 23.9344719177  # must match orbital.py:unit_covert_day2sec
  time_abs_sec = day_of_year[0] * BOREALIS_DAY2SEC + t_seconds

  # Intermittent GNSS-like samples
  gnss_time = make_intermittent_samples(t_seconds, rng, BURST_DURATION_S, GAP_DURATION_S, SAMPLE_INTERVAL_S)
  lon_true_i = np.interp(gnss_time, t_seconds, lon_deg)
  lat_true_i = np.interp(gnss_time, t_seconds, lat_deg)
  alt_true_i_km = np.interp(gnss_time, t_seconds, alt_m) / 1000.0

  # Convert position noise [m] to degrees for lon/lat
  lat_rad_i = np.deg2rad(lat_true_i)
  noise_std_lat_deg = np.rad2deg(NOISE_STD_POS_M / WGS84_A)
  noise_std_lon_deg = noise_std_lat_deg / np.maximum(np.cos(lat_rad_i), 1e-3)
  noise_std_alt_km = NOISE_STD_POS_M / 1000.0

  gnss_lon = lon_true_i + rng.normal(0.0, noise_std_lon_deg)
  gnss_lat = lat_true_i + rng.normal(0.0, noise_std_lat_deg)
  # Tacode-Fortran outputs altitude in km ('altitude[km]'), so the reference
  # trajectory_altitude.dat must also be in km to match evaluate_error's comparison.
  gnss_alt_km = alt_true_i_km + rng.normal(0.0, noise_std_alt_km)

  print(f'  Ground-truth points  : {len(t_seconds)}')
  print(f'  Simulated GNSS points: {len(gnss_time)}')

  # Output (prediction) grid
  t_pred = np.arange(t_seconds[0], t_seconds[-1] + 1e-6, DT_OUTPUT_S)
  time_abs_pred = np.interp(t_pred, t_seconds, time_abs_sec)

  # GPR reconstruction per component
  lon_mean, lon_std = fit_gpr(gnss_time, gnss_lon, t_pred, noise_std_lon_deg.mean())
  lat_mean, lat_std = fit_gpr(gnss_time, gnss_lat, t_pred, noise_std_lat_deg)
  alt_mean, alt_std = fit_gpr(gnss_time, gnss_alt_km, t_pred, noise_std_alt_km)

  os.makedirs(OUTPUT_DIR, exist_ok=True)

  def write_trajectory(name, mean, std):
    filename = os.path.join(OUTPUT_DIR, f'trajectory_{name}.dat')
    header = f'Trajectory data of {name}: Time(day), Mean, STD'
    data = np.column_stack([time_abs_pred, mean, std])
    np.savetxt(filename, data, header=header, comments='', delimiter='\t', fmt='%.18e')
    print(f'  Wrote {filename} ({len(mean)} points)')

  write_trajectory('longitude', lon_mean, lon_std)
  write_trajectory('latitude', lat_mean, lat_std)
  write_trajectory('altitude', alt_mean, alt_std)

  # Also save the TLE used, and a summary, for reproducibility / borealis.yml setup
  summary_path = os.path.join(OUTPUT_DIR, 'reference_summary.txt')
  with open(summary_path, 'w') as f:
    f.write(f'{TLE_NAME}\n{TLE_LINE1}\n{TLE_LINE2}\n\n')
    f.write(f'day_of_year_start (target_time) : {day_of_year[0]:.10f}\n')
    f.write(f'day_of_year_end                 : {day_of_year[-1]:.10f}\n')
    f.write(f'time_abs_sec_start              : {time_abs_sec[0]:.6f}\n')
    f.write(f'time_abs_sec_end                : {time_abs_sec[-1]:.6f}\n')
    f.write(f'initial coord_longitude [deg]   : {lon_deg[0]:.10f}\n')
    f.write(f'initial coord_latitude  [deg]   : {lat_deg[0]:.10f}\n')
    f.write(f'initial coord_altitude  [m]     : {alt_m[0]:.6f}\n')
    f.write(f'initial velocity v_east  [m/s]  : {v_east[0]:.6f}\n')
    f.write(f'initial velocity v_north [m/s]  : {v_north[0]:.6f}\n')
    f.write(f'initial velocity v_up    [m/s]  : {v_up[0]:.6f}\n')
    f.write(f'altitude min/max [km]           : {alt_m.min()/1000.0:.6f} / {alt_m.max()/1000.0:.6f}\n')
  print(f'  Wrote {summary_path}')


if __name__ == '__main__':
  main()
