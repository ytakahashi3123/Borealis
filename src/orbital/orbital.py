#!/usr/bin/env python3

import numpy as np
import os as os
import sys as sys
import subprocess as subprocess
import time as time
from functools import wraps
from general.general import general

class orbital(general):

# Constants
  unit_covert_km2m  = 1.e+3
  duration_sec2min  = 60.0
  duration_min2hour = 60.0
  duration_hour2day = 23.9344719177
  duration_sec2day  = duration_sec2min*duration_min2hour*duration_hour2day
  unit_covert_day2sec = duration_sec2min*duration_min2hour*duration_hour2day #86164.09053083288
  unit_covert_sec2day = 1.0/unit_covert_day2sec

  file_control_default = "borealis.yml"

  
  def __init__(self):
    print("Calling class: orbital")


  def get_directory_path(self, path_specify, default_path, manual_path):
    # default/auto: src/orbital/ からの相対パス。以前は区切りなしで連結していたため存在しないパスになっていた（既知の問題 26）
    script_directory = os.path.dirname(os.path.realpath(__file__))
    if path_specify == 'auto' or path_specify == 'default':
      directory_path = os.path.normpath( os.path.join(script_directory, default_path) )
    elif path_specify == 'manual':
      directory_path = manual_path
    else :
      raise ValueError(f"directory_path_specify must be 'manual', 'default' or 'auto': {path_specify}")
    return directory_path


  def read_inputdata(self, filename):
      
    print("Reading GPS data...",":", filename)
    
    data_input = np.loadtxt(filename,comments=('#'),delimiter=None,skiprows=2)
    count      = data_input[:, 0]
    len_array  = len(count)
  
    time_sec   = data_input[:, 1]
    time_min   = data_input[:, 2]
    time_hour  = data_input[:, 3]
    time_day   = data_input[:, 4]
  
    time_gps_hour = data_input[:, 5]
    time_gps_sec  = data_input[:, 6]
  
    clock_jst_year  = data_input[:, 7]
    clock_jst_month = data_input[:, 8]
    clock_jst_day   = data_input[:, 9]
    clock_jst_hour  = data_input[:,10]
    clock_jst_min   = data_input[:,11]
    clock_jst_sec   = data_input[:,12]
  
    latitude            = data_input[:,13] # Degree 
    longitude           = data_input[:,14] # Degree
    altitude_ellipspoid = data_input[:,15] # km
    altitude_sealevel   = data_input[:,16] # km
  
    num_sat = data_input[:,17]
  
    altitude = altitude_ellipspoid
  #  altitude = altitude_sealevel

    return time_sec, longitude, latitude, altitude
  

  def set_timeunit( self, timeunit_system ):
  
    print(timeunit_system )
    if ( timeunit_system == 'day'):
      unit_covert_timeunit = self.unit_covert_day2sec
    elif ( timeunit_system == 'hour'):
      # 1 時間の秒数。以前は duration_min2hour*duration_hour2day (= 1436.07) になっていた（既知の問題 3）
      unit_covert_timeunit = self.duration_sec2min*self.duration_min2hour
    elif ( timeunit_system == 'min'):
      unit_covert_timeunit = self.duration_min2hour
    elif( timeunit_system == 'sec'):
      unit_covert_timeunit = 1.0
    else:
      raise ValueError(f"reference.timeunit must be day, hour, min or sec: {timeunit_system}")
  
    return unit_covert_timeunit
  
    
  def convert_cartesian_geodetic(self, radius_equat_planet, ellipticity_planet, cartesian_coord):
      #
      # Cartesian Coordinate --> Longitude, Latitude, Altitude coordinate (WGS84)
      #
      # carcoord_x,y,z: meter
      # Longitude: Radius
      # Latitude: Radius
      # Altitude: meter
      carcoord_x = cartesian_coord[0]
      carcoord_y = cartesian_coord[1]
      carcoord_z = cartesian_coord[2]
  
      radius_proj = np.sqrt( carcoord_x**2 + carcoord_y**2 )
      B_geo_tmp   = np.sign( carcoord_z ) * radius_equat_planet * (1.0 - ellipticity_planet)
      E_geo_tmp   = ( (carcoord_z + B_geo_tmp)*B_geo_tmp/radius_equat_planet - radius_equat_planet )/radius_proj
      F_geo_tmp   = ( (carcoord_z - B_geo_tmp)*B_geo_tmp/radius_equat_planet + radius_equat_planet )/radius_proj
  
      P_geo_tmp   = 4.0*(E_geo_tmp*F_geo_tmp + 1.0)/3.0
      Q_geo_tmp   = 2.0*(E_geo_tmp**2 - F_geo_tmp**2)
      D_geo_tmp   = P_geo_tmp**3 + Q_geo_tmp**2
  
  #    print(np.sign(D_geo_tmp))
  
      # D >= 0 と D < 0 で式が分かれる。要素ごとに選ぶ（以前は「1 つでも正なら全要素を前者で」計算していた。既知の問題 14）
      with np.errstate(invalid='ignore', divide='ignore'):
        S_geo_tmp = np.sqrt(D_geo_tmp) + Q_geo_tmp
        S_geo_tmp = np.sign(S_geo_tmp) * np.exp( np.log( np.abs(S_geo_tmp))/3.0 )
        V_geo_pos = - ( 2.0*Q_geo_tmp + (P_geo_tmp/S_geo_tmp - S_geo_tmp)**3 )/(3.0*P_geo_tmp)
        V_geo_neg = 2.0 * np.sqrt( -P_geo_tmp ) * np.cos( np.arccos(Q_geo_tmp/np.sqrt( - P_geo_tmp**3 )) / 3.0)
      V_geo_tmp = np.where( D_geo_tmp >= 0.0, V_geo_pos, V_geo_neg )
  
      G_geo_tmp = 0.5*( E_geo_tmp + np.sqrt(E_geo_tmp**2 + V_geo_tmp) )
      T_geo_tmp = np.sqrt( G_geo_tmp**2 + (F_geo_tmp - V_geo_tmp*G_geo_tmp)/(2.0*G_geo_tmp - E_geo_tmp )) - G_geo_tmp
  
  # Longitude
      longitude = np.sign(carcoord_y) * np.arccos( carcoord_x / np.sqrt( carcoord_x**2 + carcoord_y**2 ) )
  # Latitude
      latitude  = np.arctan( (1.0 - T_geo_tmp**2)*radius_equat_planet / (2.0 * B_geo_tmp * T_geo_tmp))
  # Altitude
      altitude  = (radius_proj - radius_equat_planet * T_geo_tmp) * np.cos(latitude) + (carcoord_z - B_geo_tmp) * np.sin(latitude)
  
      geodetic_coord = [longitude, latitude, altitude]
  
      return geodetic_coord
  
  
  def convert_geodetic_cartesian(self, radius_equat_planet, ellipticity_planet, geodetic_coord):
      #
      # Longitude, Latitude, Altitude coordinate (WGS84) --> Cartesian Coordinate
      #
      # Longitude: Radius
      # Latitude: Radius
      # Altitude: meter
      # carcoord_x,y,z: meter
      #
      longitude = geodetic_coord[0]
      latitude  = geodetic_coord[1]
      altitude  = geodetic_coord[2]
  
      eccentricity2  = ellipticity_planet*(2.0-ellipticity_planet)
      altitude_geoid = radius_equat_planet / np.sqrt( 1.0 - eccentricity2 * np.sin( latitude )**2 )
  
      carcoord_x = ( altitude_geoid + altitude ) * np.cos( latitude ) * np.cos( longitude )
      carcoord_y = ( altitude_geoid + altitude ) * np.cos( latitude ) * np.sin( longitude )
      carcoord_z = ( altitude_geoid * (1.0 - eccentricity2 ) + altitude ) * np.sin( latitude )
  
      cartesian_coord = [carcoord_x, carcoord_y, carcoord_z]
      return cartesian_coord
  
  
  def set_angle_polar(self, coord):
    #
    # 直交座標系（回転座標系）から極座標における経度(alpha)・緯度(beta)を計算する。WGSの経度・緯度とは厳密にことなるので注意
    #
    radius      = np.sqrt( coord[0]**2 + coord[1]**2 + coord[2]**2 ) 
    angle_beta  = np.arcsin( coord[2]/np.sqrt( coord[0]**2 + coord[1]**2 + coord[2]**2 ) )
    angle_alpha = np.arccos( coord[0]/np.sqrt( coord[0]**2 + coord[1]**2 )  ) * np.sign( coord[1] )
  
    return radius, angle_beta, angle_alpha


  def convert_carteasian_polar(self, vec_input,longitude,latitude):
    # 
    # 直交座標上の３次元ベクトルを極座標に変換
    #
    def convert_coordinate_rxyz(vec,angle_rot,axis):
      #
      # Coordinate rotation
      # angle_rot: degree
      # axis: x or y or z
      #
      vec_x = vec[0]
      vec_y = vec[1]
      vec_z = vec[2]
  
      if (axis == 'x') :
        vec_conv_x = np.array(vec_x)
        vec_conv_y = np.array(vec_y)*np.cos(angle_rot) + np.array(vec_z)*np.sin(angle_rot)
        vec_conv_z =-np.array(vec_y)*np.sin(angle_rot) + np.array(vec_z)*np.cos(angle_rot)
      elif (axis == 'y') :
        vec_conv_x = np.array(vec_x)*np.cos(angle_rot) - np.array(vec_z)*np.sin(angle_rot)
        vec_conv_y = np.array(vec_y)
        vec_conv_z = np.array(vec_x)*np.sin(angle_rot) + np.array(vec_z)*np.cos(angle_rot)
      elif (axis == 'z') :
        vec_conv_x =  np.array(vec_x)*np.cos(angle_rot) + np.array(vec_y)*np.sin(angle_rot)
        vec_conv_y = -np.array(vec_x)*np.sin(angle_rot) + np.array(vec_y)*np.cos(angle_rot)
        vec_conv_z =  np.array(vec_z)
      else :
        raise ValueError(f'Axis is not correct: {axis}')
      return [vec_conv_x,vec_conv_y,vec_conv_z]
  
  
    def exchanege_axis_xyz2zxy(vec_input):
      vec_conv_1 = vec_input[2]
      vec_conv_2 = vec_input[0]
      vec_conv_3 = vec_input[1]
      return [vec_conv_1,vec_conv_2,vec_conv_3]
  
  
    def exchanege_axis_zxy2xyz(vec_input):
      vec_conv_1 = vec_input[1]
      vec_conv_2 = vec_input[2]
      vec_conv_3 = vec_input[0]
      return [vec_conv_1,vec_conv_2,vec_conv_3]
  
  
    vec_tmp = convert_coordinate_rxyz(vec_input, longitude,'z')
    vec_tmp = convert_coordinate_rxyz(vec_tmp  ,-latitude,'y')
    # この座標回転で1,2,3成分が[高度、経度、緯度]の順番で出るので[経度、緯度、高度]に補正する
    vec_res = exchanege_axis_zxy2xyz(vec_tmp)
  
    return vec_res


  def read_header_tecplot(self, filename, headerline, headername, var_list):
    # Set header
    with open(filename) as f:
      lines = f.readlines()
    # リストとして取得
    lines_strip = [line.strip() for line in lines]
    # ”Variables ="を削除した上で、カンマとスペースを削除
    variables_line = lines_strip[headerline].replace(headername, '')
    variables_line = variables_line.replace(',', ' ').replace('"', ' ')
    # 空白文字で分割して単語のリストを取得
    words = variables_line.split()

    # set variables
    result_var   = var_list
    result_index = []
    for i in range( 0,len(result_var) ):
      for n in range( 0,len(words) ):
        if result_var[i] == words[n] :
          result_index.append(n)
          break

    return result_index

  def store_data_as_dictionary(self, var_list, var_index, var_data):
    reference_dict = {}
    if var_data.ndim == 1:
      for n in range( 0,len(var_list) ):
        reference_dict[ var_list[n] ] = var_data[var_index[n]]
    else:
      for n in range( 0,len(var_list) ):
        reference_dict[ var_list[n] ] = var_data[:,var_index[n]]
    return reference_dict


  def write_tecplotdata( self, filename, print_message, header, delimiter, comments, output_data ):
    
    print(print_message,':',filename)
    np.savetxt(filename, output_data, header=header, delimiter=delimiter, comments=comments )

    return


  def get_penalty_term(self, parameter_opt, boundary, penalty_value):
    #  parameter_opt が boundary の範囲外だったときにペナルティ項 penalty_value を与える
#    penalty = 0.0
#    count_tmp = 0
#    for n in range(0, len(boundary) ):
#      parameter_component = boundary[n]['component']
#      for m in range(0, len(parameter_component)):
#        if not ( parameter_opt[0,count_tmp] >= parameter_component[m]['bound_min'] 
#           and   parameter_opt[0,count_tmp] <= parameter_component[m]['bound_max'] ) :
#          penalty = penalty_value
#        count_tmp += 1
#    return penalty
    count_tmp = 0
    for n, param in enumerate(boundary):
      for m, component in enumerate(param['component']):
        param_value = parameter_opt[0, count_tmp]
        if not (component['bound_min'] <= param_value <= component['bound_max']):
          return penalty_value
        count_tmp += 1
    return 0.0

  def get_penalty_flag(self, parameter_opt, boundary):
    count_tmp = 0
    for n, param in enumerate(boundary):
      for m, component in enumerate(param['component']):
        param_value = parameter_opt[0, count_tmp]
        if not (component['bound_min'] <= param_value <= component['bound_max']):
          return True
        count_tmp += 1
    return False

  def find_bracket_index(self, x_ref, x):
    # 昇順の x_ref の中で x_ref[m-1] <= x <= x_ref[m] となる m と、x が x_ref の範囲の内側かどうかを返す。
    # 範囲の内側では、従来の「x_ref[m] >= x となる最初の m」と同じ m になる。範囲の外は valid = False で、
    # 以前のように負の添字で配列の末尾を参照することはない（既知の問題 6）
    x_ref = np.asarray(x_ref)
    x = np.atleast_1d(x)
    valid = (x >= x_ref[0]) & (x <= x_ref[-1])
    m = np.clip( np.searchsorted(x_ref, x, side='left'), 1, len(x_ref)-1 )
    return m, valid


  def run_external_code(self, cmd_code, work_dir_case, filename_result=None):
    # 外部コードを work_dir_case の中で起動し、終了を待つ。成功なら True を返す。
    # - 子プロセスには dict(os.environ) を渡す。mpi4py の import (MPI_Init) で C 側に足される OMPI_*/PMIX_* を
    #   継がせると、外部コードの mpirun が失敗するため（既知の問題 19）
    # - os.chdir を使わず cwd で作業ディレクトリを渡す（プロセス全体に効くため）
    # - テンプレートから写した古い結果ファイルを読まないよう、起動の前に消す（既知の問題 7）
    if filename_result is not None:
      filename_tmp = os.path.join(work_dir_case, filename_result)
      if os.path.exists(filename_tmp):
        os.remove(filename_tmp)
    returncode = subprocess.call( [cmd_code], cwd=work_dir_case, env=dict(os.environ) )
    flag_success = (returncode == 0)
    if not flag_success:
      print(f'Warning: external code returned exit status {returncode}: {work_dir_case}')
    if filename_result is not None and not os.path.exists(os.path.join(work_dir_case, filename_result)):
      print(f'Warning: result file was not written: {os.path.join(work_dir_case, filename_result)}')
      flag_success = False
    return flag_success


  def stop_program(self, message, mpi_instance=None):
    # 設定の誤りなどで止める。MPI 実行中は全ランクを止める（exit() では 1 ランクだけが抜け、他が待ち続けた。既知の問題 8）
    print(message)
    print('Program stopped.')
    sys.stdout.flush()
    if mpi_instance is not None and getattr(mpi_instance, 'flag_mpi', False):
      mpi_instance.comm.Abort(1)
    sys.exit(1)


  def check_maximize_supported(self, objective_function, flag_maximize, label, mpi_instance=None):
    # PSO・ABC は最大化の符号を目的関数に渡し、掛けるのはアダプタの側である。
    # 符号を掛けないアダプタで maximize を指定すると、黙って最小化を続けていた（既知の問題 1）ので止める
    adapter_instance = getattr(objective_function, '__self__', None)
    if np.any(flag_maximize) and not getattr(adapter_instance, 'flag_apply_sign', False):
      self.stop_program(f'[{label}-Borealis] Error: maximize is not supported by the selected adapter '
                        f'({type(adapter_instance).__name__}); it returns an error to be minimized.', mpi_instance)
    return


  def sanitize_score(self, score, num_objectives, value_nonfinite, label):
    # 目的関数の値を検査する。長さが目的の数と違えば止め、NaN・無限大は value_nonfinite に置き換える
    # （NaN が np.argmin でアーカイブを乗っ取っていた。既知の問題 2）
    score = np.atleast_1d( np.asarray(score, dtype=float) ).copy()
    if score.size != num_objectives:
      raise ValueError(f'[{label}-Borealis] The objective function returned {score.size} values, '
                       f'but objectives.num_objectives is {num_objectives}')
    flag_nonfinite = ~np.isfinite(score)
    if np.any(flag_nonfinite):
      print(f'[{label}-Borealis] Warning: non-finite objective value {score} is replaced by {value_nonfinite}')
      score[flag_nonfinite] = value_nonfinite
    return score


  # 多目的の道具（GA・ABC で共有する。目的関数はすべて最小化の向き）
  def dominates(self, a, b):
    return np.all(a <= b) and np.any(a < b)


  def non_dominated_sort(self, scores):
    # 非劣解の順位（0 が第 1 フロント）。高速な非劣解ソート (Deb et al., 2002)
    num = len(scores)
    dominated_by = [ [] for _ in range(num) ]
    count_dominating = np.zeros(num, dtype=int)
    rank = np.zeros(num, dtype=int)
    front = []
    for p in range(num):
      for q in range(num):
        if p == q:
          continue
        if self.dominates(scores[p], scores[q]):
          dominated_by[p].append(q)
        elif self.dominates(scores[q], scores[p]):
          count_dominating[p] += 1
      if count_dominating[p] == 0:
        front.append(p)
    level = 0
    while front:
      next_front = []
      for p in front:
        rank[p] = level
        for q in dominated_by[p]:
          count_dominating[q] -= 1
          if count_dominating[q] == 0:
            next_front.append(q)
      level += 1
      front = next_front
    return rank


  def non_dominated_mask(self, scores):
    # 第 1 フロント（どれにも支配されない点）なら True。non_dominated_sort の順位 0 と同じものを、配列の演算で求める
    scores = np.asarray(scores, dtype=float)
    less_equal = np.all( scores[:, None, :] <= scores[None, :, :], axis=2 )   # [j, i]: j がすべての目的で i 以下
    less       = np.any( scores[:, None, :] <  scores[None, :, :], axis=2 )   # [j, i]: j がどれかの目的で i より小さい
    return ~np.any( less_equal & less, axis=0 )


  def crowding_distance(self, scores, rank):
    # 同じフロントの中での混雑距離。端の個体は無限大
    scores = np.asarray(scores)
    distance = np.zeros(len(scores))
    for level in np.unique(rank):
      index = np.where(rank == level)[0]
      if len(index) <= 2:
        distance[index] = np.inf
        continue
      for m in range(scores.shape[1]):
        order = index[ np.argsort(scores[index, m], kind='stable') ]
        distance[order[0]] = np.inf
        distance[order[-1]] = np.inf
        f_range = scores[order[-1], m] - scores[order[0], m]
        if f_range < 1.0e-15:
          continue
        distance[order[1:-1]] += (scores[order[2:], m] - scores[order[:-2], m]) / f_range
    return distance


  # Decorator for time measurement
  def time_measurement_decorated(func):
    @wraps(func)
    def wrapper(*args, **kargs) :
      #text_blue = '\033[94m'
      #text_green = '\033[92m'
      text_yellow = '\033[93m'
      text_end = '\033[0m'
      flag_time_measurement = False
      if flag_time_measurement :
        start_time = time.time()
        result = func(*args,**kargs)
        elapsed_time = time.time() - start_time
        print('Elapsed time of '+str(func.__name__)+str(':'),text_yellow + str(elapsed_time) + text_end,'s')
      else :
        result = func(*args,**kargs)
      return result 
    return wrapper
