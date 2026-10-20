#!/usr/bin/env python3

import numpy as np
import os as os
import shutil as shutil
import subprocess as subprocess
from orbital.orbital import orbital


class adapter_heatcond(orbital):

  def __init__(self,mpi_instance):

    print("Constructing class: adapter_heatcond")

    self.mpi_instance = mpi_instance

    return

  
  def initial_settings(self, config):

    self.work_dir   = config['heatcond']['work_dir']
    self.case_dir   = config['heatcond']['case_dir']
    self.step_digit = config['heatcond']['step_digit']

    # Make directory
    if self.mpi_instance.rank == 0:
      super().make_directory_rm(self.work_dir)

    # Template case 
    path_specify = config['heatcond']['directory_path_specify']
    default_path = '../../heatcond'
    manual_path  = config['heatcond']['manual_path']
    self.template_path = self.get_directory_path(path_specify, default_path, manual_path)
  
    self.work_dir_template = self.work_dir+'/'+self.case_dir+'_template'
    if self.mpi_instance.rank == 0:
      shutil.copytree(self.template_path, self.work_dir_template)

    # Control file and computed result file
    self.filename_control_code = config['heatcond']['filename_control']
    self.filename_result_code  = config['heatcond']['filename_result']

    # Execution file
    self.cmd_code = config['heatcond']['cmd_code']
    self.root_dir = os.getcwd()
    self.cmd_home = os.path.dirname(os.path.realpath(__file__)) + '/..'

    # Target parameter (corresponding to the parameter boundary)
    self.parameter_target = config['parameter_optimized']['boundary']

    # Result file: Make directory
    if self.mpi_instance.rank == 0:
      super().make_directory_rm(config['heatcond']['result_dir'])

    # Control file 
    self.config = config

    # Counter
    self.iter = 1
     
    # Variables of result file 
    self.str_time_sec    = 'Time[s]'
    self.str_temperature = 'T[K]'
    self.str_altitude    = 'Alt.[km]'
    self.str_density     = 'Dens[kg/m3]'
    self.str_tempback    = 'Tback[K]'
    self.str_tempatms    = 'Tatm[K]'
    self.str_htcoef      = 'Htcoef'
    self.str_reynolds    = 'Re'
    self.str_solar       = 'Solar[W/m2]'
    self.str_heatflux    = 'Heatflux[W/m2]'

    self.str_time_day    = 'Time[day]'

    self.result_var = [ self.str_time_sec, self.str_temperature, self.str_altitude, \
                        self.str_density, self.str_tempback, self.str_tempatms, \
                        self.str_htcoef, self.str_reynolds, self.str_solar, self.str_heatflux ]

    # For result data reading
    self.headerline_variables = 1
    self.num_skiprows = 2

    # 同期をとる
    if self.mpi_instance.flag_mpi:
      self.mpi_instance.comm.Barrier()

    return


  def reference_data_setting(self, config):

    # File directory and name setting
    path_specify = config['reference']['directory_path_specify']
    default_path = '../../reference_egg'
    manual_path  = config['reference']['manual_path']
    reference_path = self.get_directory_path(path_specify, default_path, manual_path)
    filename  = config['reference']['filename_input']

    # Reading reference data
    filename_tmp = reference_path+'/'+filename
    print('Reading reference data...',':', filename_tmp)
    data_input = np.loadtxt(filename_tmp,comments=('#'),delimiter=None,skiprows=self.num_skiprows)

    # Terget variables in reference
    var_x = config['reference']['var_x'] 
    var_y = config['reference']['var_y']
    var_list = [var_x, var_y]
    headername_tmp = 'Variables ='
    var_index = super().read_header_tecplot(filename_tmp, self.headerline_variables, headername_tmp, var_list)

    # Store data as dictionary
    self.reference_dict = {}
    for n in range( 0,len(var_list) ):
      self.reference_dict[ var_list[n] ] = data_input[:,var_index[n]]

    return


  @orbital.time_measurement_decorated
  def rewrite_control_file_code(self, parameter_opt):
    
    # 何度もファイル開閉をするのは問題かもしれない

    print('--Modify control file')

    filename = self.work_dir_case+'/'+self.filename_control_code

    count = 0
    parameter_target = self.parameter_target
    for n in range(0, len(parameter_target ) ):
      parameter_name = parameter_target[n]['name']
      parameter_component = parameter_target[n]['component']

      #var_root_ctl = parameter_name[0]
      var_name_ctl = parameter_name

      txt_indentified = var_name_ctl
      ele_indentified = len(parameter_component)
      txt_replaced = []
      for m in range(0, len(parameter_component) ):
        txt_replaced.append( str( parameter_opt[0,count] ) + ',' )
        count = count + 1
      txt_replaced[-1] = txt_replaced[-1].rstrip(',')
      print('--Variable:',var_name_ctl, ', Parameters:',txt_replaced)

      # File operation
      with open(filename) as f:
        lines = f.readlines()

      # リストとして取得 
      lines_strip = [line.strip() for line in lines]

      # 置換する行を特定する
      line_both        = [(i, line) for i, line in enumerate(lines_strip) if txt_indentified in line]
      i_line, str_line = list(zip(*line_both))
      # 抽出した行をスペース・タブで分割する。そのele_indentified+1番目を置換し、line_replacedというstr型に戻す。
      words = lines_strip[i_line[0]].split()
      for n in range(0, ele_indentified ):
        words[n] = txt_replaced[n]
      line_replaced  = ' '.join(words)

      # lines_newはリストになることに注意。そのため、'',joinでstr型に戻す
      lines_new     = [item.replace( lines_strip[i_line[0]], line_replaced ) for item in lines]
      str_lines_new = ''.join(lines_new)

      # 同じファイル名で保存
      with open(filename, mode="w") as f:
        f.write(str_lines_new)
    
    return


  @orbital.time_measurement_decorated
  def run_code(self):
    
    print('--Run external code')

    # 終了ステータスと結果ファイルを確かめる（既知の問題 7）。子には MPI の環境変数を渡さない（既知の問題 19）
    return super().run_external_code( self.cmd_code, self.work_dir_case, self.filename_result_code )


  @orbital.time_measurement_decorated
  def evaluate_error(self, parameter_opt, result_dict):

    # 外部コード結果とReferenceの誤差を評価する

    print('--Evaluating error between computed result and reference data')

    # Result data
    x_min    = self.config['heatcond']['x_min']
    x_max    = self.config['heatcond']['x_max']
    x_offset = self.config['heatcond']['x_offset']

    x_res = result_dict[ self.str_time_sec ] + x_offset
    y_res = result_dict[ self.str_temperature ]

    _, i_start = super().closest_value_index(x_res, x_min)
    _, i_end   = super().closest_value_index(x_res, x_max)

    # Reference data
    var_x = self.config['reference']['var_x'] 
    var_y = self.config['reference']['var_y']
    x_ref = self.reference_dict[ var_x ] 
    y_ref = self.reference_dict[ var_y ] 

    # Penalty
    penalty = 0.0
    if self.config['parameter_optimized']['flag_penalty']:
      boundary = self.config['parameter_optimized']['boundary']
      huge_tmp = self.config['parameter_optimized']['penalty_value']
      penalty = super().get_penalty_term(parameter_opt, boundary, huge_tmp)

    # 誤差評価の計算
    #error = 0.0
    #count = 0
    #for n in range(i_start, i_end):
    #  count = count+1
    #  for m in range(0,len(x_ref)):
    #    if (x_ref[m] >= x_res[n] ):
    #      m_opt = m
    #      break
    #  if self.mpi_instance.rank ==0: print(n,m_opt)
    #  grad_fact = ( x_res[n] - x_ref[m_opt-1] )/( x_ref[m_opt] - x_ref[m_opt-1] )
    #  y_ref_cor = ( y_ref[m_opt]  - y_ref[m_opt-1]  )*grad_fact + y_ref[m_opt-1]
    #  error = error + ( y_res[n] - y_ref_cor )**2
    #error = np.sqrt( error/float(count) )

    error = 0.0
    count = 0
    # x_resの各要素に対して、対応するy_resとy_ref_corを計算
    for n in range(i_start, i_end):
      count += 1
      # x_res[n]より大きい最初の要素のインデックスを見つける
      m_opt = np.argmax(x_ref >= x_res[n])
      if m_opt == 0:
        grad_fact = 0.0
      else:
        grad_fact = (x_res[n] - x_ref[m_opt - 1]) / (x_ref[m_opt] - x_ref[m_opt - 1])
      y_ref_cor = (y_ref[m_opt] - y_ref[m_opt - 1]) * grad_fact + y_ref[m_opt - 1]
      # 誤差を計算し、errorに加算
      error += (y_res[n] - y_ref_cor) ** 2
    error = np.sqrt( error )/float( count ) + penalty

    # Green color
    print('--Error:','\033[92m'+str(error)+'\033[0m', 'in Epoch',str(self.iter) )

    return error


  @orbital.time_measurement_decorated
  def read_result_data(self):
    
    # Resultデータの読み込み
    filename = self.work_dir_case+'/'+self.filename_result_code

    print("--Reading computed results by code...:",filename)

    # Set header
    result_var = self.result_var
    headername_tmp = 'Variables ='
    result_index = super().read_header_tecplot(filename, self.headerline_variables, headername_tmp, result_var)

    # Read data
    data_input = np.loadtxt(filename,comments=('#'),delimiter=None,skiprows=self.num_skiprows)

    # Store data as dictionary
    result_dict = {}
    for n in range( 0,len(result_var) ):
      result_dict[ result_var[n] ] = data_input[:,result_index[n]]

    return result_dict


  @orbital.time_measurement_decorated
  def write_result_data(self, result_dict):

    if( self.config['heatcond']['flag_output'] ):
      var_output = self.config['heatcond']['variables_output']
      result_dir        = self.config['heatcond']['result_dir']
      filename_tecplot  = self.config['heatcond']['filename_output']
      number_padded     = str(self.iter).zfill(self.step_digit)
      filename_tmp      = super().insert_suffix(result_dir+'/'+filename_tecplot,'_case'+number_padded,'.')
      print('--Writing output file...:',filename_tmp)

      # Open file
      file_output = open( filename_tmp , 'w')

      header_tmp = "Variables = "
      for n in range(0,len(var_output)):
        header_tmp = header_tmp + var_output[n] + ','
      header_tmp = header_tmp.rstrip(',') + '\n'
      file_output.write( header_tmp )

      num_step = len( result_dict[var_output[0]] )
      text_tmp = ''
      for n in range(0, num_step):
        for m in range(0, len(var_output)):
          text_tmp = text_tmp  + str( result_dict[var_output[m]][n] ) + ', '
        text_tmp = text_tmp.rstrip(',')  + '\n'

      file_output.write( text_tmp )
      file_output.close()

    return


  @orbital.time_measurement_decorated
  def objective_function(self, parameter_opt, *args):

    # コントロールファイルを適切に修正して、tacodeを実行する。

    if args:
      self.iter = args[0]

    print('Iteration: ', self.iter)

    # Caseディレクトリの作成
    self.work_dir_case = self.work_dir + '/' + self.case_dir + str(self.iter).zfill(self.step_digit)
    print('--Make case directory: ', self.work_dir_case)
    shutil.copytree(self.work_dir_template, self.work_dir_case)

    # コントロールファイルの書き換え 
    self.rewrite_control_file_code(parameter_opt)

    # Run Tacode
    flag_success = self.run_code()
    if not flag_success:
      if not args:
        self.iter += 1
      return np.atleast_1d(np.inf)

    # Read result for evaluating error
    result_dict = self.read_result_data()

    # Write result data
    self.write_result_data(result_dict)

    # Evaluate error
    error = self.evaluate_error(parameter_opt, result_dict)

    # カウンタの更新
    if not args:
      self.iter += 1

    return np.atleast_1d(error).astype(float)
