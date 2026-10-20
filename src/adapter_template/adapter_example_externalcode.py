#!/usr/bin/env python3

import numpy as np
import os as os
import shutil as shutil
import subprocess as subprocess
from orbital.orbital import orbital


class adapter_example_externalcode(orbital):

  def __init__(self,mpi_instance):

    print("Constructing class: adapter_example_externalcode")

    self.mpi_instance = mpi_instance

    return

  
  def initial_settings(self, config):

    self.work_dir   = config['example_externalcode']['work_dir']
    self.case_dir   = config['example_externalcode']['case_dir']
    self.step_digit = config['example_externalcode']['step_digit']

    # Make directory
    if self.mpi_instance.rank == 0:
      super().make_directory_rm(self.work_dir)

    # Template case 
    path_specify = config['example_externalcode']['directory_path_specify']
    default_path = '../../example_externalcode/curve' 
    manual_path  = config['example_externalcode']['manual_path']
    self.template_path = self.get_directory_path(path_specify, default_path, manual_path)
  
    self.work_dir_template = self.work_dir+'/'+self.case_dir+'_template'
    if self.mpi_instance.rank == 0:
      shutil.copytree(self.template_path, self.work_dir_template)

    # Control file and computed result file
    self.filename_control_code = config['example_externalcode']['filename_control']
    self.filename_result_code  = config['example_externalcode']['filename_result']

    # Execution file
    self.cmd_code = config['example_externalcode']['cmd_externalcode']
    self.root_dir = os.getcwd()
    self.cmd_home = os.path.dirname(os.path.realpath(__file__)) + '/..'

    # Target parameter (corresponding to the parameter boundary)
    self.parameter_target = config['parameter_optimized']['boundary']

    # Result file: Make directory
    if self.mpi_instance.rank == 0:
      super().make_directory_rm(config['example_externalcode']['result_dir'])

    # Control file 
    self.config = config

    # Counter
    self.iter = 1
     
    # Variables of result file
    self.str_x = 'x'
    self.str_y = 'y'

    self.result_var = [ self.str_x, self.str_y ]
 
    # For trajectory data reading
    self.headerline_variables = 1
    self.num_skiprows = 3

    # 同期をとる
    if self.mpi_instance.flag_mpi:
      self.mpi_instance.comm.Barrier()

    return


  def reference_data_setting(self, config):

    # File directory and name setting
    path_specify = config['reference']['directory_path_specify']
    default_path = '../../example_externalcode/curve_reference'
    manual_path  = config['reference']['manual_path']
    reference_path = self.get_directory_path(path_specify, default_path, manual_path)
    filename  = config['reference']['filename_input']

    # Reading reference data
    filename_tmp = reference_path+'/'+filename
    print('Reading reference data...',':', filename_tmp)
    data_input = np.loadtxt(filename_tmp,comments=('#'),delimiter=None,skiprows=2)
    self.x_ref = data_input[:,0]
    self.y_ref = data_input[:,1]

    return


  @orbital.time_measurement_decorated
  def rewrite_control_file_code(self, parameter_opt):
    
    # 何度もファイル開閉をするのは問題かもしれない

    print('--Modify control file')

    filename = self.work_dir_case+'/'+self.filename_control_code

    count = 0
    parameter_target = self.parameter_target
    for n in range(0, len(parameter_target ) ):
      parameter_name = parameter_target[n]['name'].rsplit('.', 1)
      parameter_component = parameter_target[n]['component']

      var_root_ctl = parameter_name[0]
      var_name_ctl = parameter_name[1]

      txt_indentified = var_name_ctl
      ele_indentified = len(parameter_component)
      txt_replaced = []
      for m in range(0, len(parameter_component) ):
        txt_replaced.append( str( parameter_opt[0,count] ) )
        count = count + 1
      print('--Variable:',var_name_ctl,'in',var_root_ctl, ', Parameters:',txt_replaced)

      # File operation
      for m in range(0,ele_indentified):
        # Reading control file
        with open(filename) as f:
          lines = f.readlines()

        # リストとして取得 
        lines_strip = [line.strip() for line in lines]

        # 置換する行を特定する
        line_both        = [(i, line) for i, line in enumerate(lines_strip) if txt_indentified in line]
        i_line, str_line = list(zip(*line_both))

        # 抽出した行をスペース・タブで分割する。そのele_indentified列目を置換し、line_replacedというstr型に戻す。
        words = lines_strip[i_line[0]+m+1].split()
        # Replace (words[0]に該当する'-'は置換しない、その次のwords[1]を置換する)
        words[1] = txt_replaced[m]
        # インデントを考慮して新しい行を構築
        line_replaced  = ' '.join(words)

        # 行を置換
        # lines_newはリストになることに注意。そのため、'',joinでstr型に戻す
        lines_updated = [item.replace( lines_strip[i_line[0]+m+1], line_replaced ) for item in lines]

        str_lines_new = ''.join(lines_updated)

        # Update the file
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

    x_min    = self.config['example_externalcode']['x_min']
    x_max    = self.config['example_externalcode']['x_max']
    x_offset = self.config['example_externalcode']['x_offset']

    x_res = result_dict[ self.str_x ] + x_offset
    y_res = result_dict[ self.str_y ]

    _, i_start = super().closest_value_index(x_res, x_min)
    _, i_end   = super().closest_value_index(x_res, x_max)

    # Penalty
    penalty = 0.0
    if self.config['parameter_optimized']['flag_penalty']:
      boundary = self.config['parameter_optimized']['boundary']
      huge_tmp = self.config['parameter_optimized']['penalty_value']
      penalty = super().get_penalty_term(parameter_opt, boundary, huge_tmp)

    # 誤差評価の計算
    error = 0.0
    count = 0
    # 基準データの x の範囲の外にある点は比べない（以前は配列の末尾へ回り込んでいた。既知の問題 6）
    m_opt_list, flag_valid = super().find_bracket_index(self.x_ref, x_res[i_start:i_end])
    if not np.all(flag_valid):
      print(f'Warning: {int(np.sum(~flag_valid))} of {len(flag_valid)} points lie outside the reference data and are not compared')
    for n, m_opt, flag in zip(range(i_start, i_end), m_opt_list, flag_valid):
      if not flag:
        continue
      count = count+1
      grad_fact = ( x_res[n] - self.x_ref[m_opt-1] )/( self.x_ref[m_opt] - self.x_ref[m_opt-1] )
      y_ref_cor = ( self.y_ref[m_opt]  - self.y_ref[m_opt-1]  )*grad_fact + self.y_ref[m_opt-1]
      error = error + ( y_res[n] - y_ref_cor )**2 

    if count == 0:
      print('Warning: no computed point lies within the reference data')
      return np.inf
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
    with open(filename) as f:
      lines = f.readlines()
    # リストとして取得
    lines_strip = [line.strip() for line in lines]
    # ”Variables ="を削除した上で、カンマとスペースを削除
    variables_line = lines_strip[self.headerline_variables].replace('Variables =', '')
    variables_line = variables_line.replace(',', ' ').replace('"', ' ')
    # 空白文字で分割して単語のリストを取得
    words = variables_line.split()

    # set variables
    result_var   = self.result_var
    result_index = []
    for i in range( 0,len(result_var) ):
      for n in range( 0,len(words) ):
        if result_var[i] == words[n] :
          result_index.append(n)
          #print( result_var[i], words[n], i, n)
          break

    # Read data
    data_input = np.loadtxt(filename,comments=('#'),delimiter=None,skiprows=self.num_skiprows)

    # Store data as dictionary
    result_dict = {}
    for n in range( 0,len(result_var) ):
      result_dict[ result_var[n] ] = data_input[:,result_index[n]]

    return result_dict


  @orbital.time_measurement_decorated
  def write_result_data(self, result_dict):

    if( self.config['example_externalcode']['flag_output'] ):
      x_offset = self.config['example_externalcode']['x_offset']
      x_res = result_dict[ self.str_x ] + x_offset
      y_res = result_dict[ self.str_y ]

      result_dir        = self.config['example_externalcode']['result_dir']
      filename_tecplot  = self.config['example_externalcode']['filename_output']
      number_padded     = str(self.iter).zfill(self.step_digit)
      filename_tmp      = super().insert_suffix(result_dir+'/'+filename_tecplot,'_case'+number_padded,'.')
      print('--Writing output file...:',filename_tmp)

      result_var_tmp = self.result_var
      header_tmp = "Variables = "
      for n in range(0,len(result_var_tmp)):
        header_tmp = header_tmp + result_var_tmp[n] + ','
      header_tmp = header_tmp.rstrip(",") 
    
      delimiter_tmp     = '\t'
      comments_tmp      = ''
      output_tmp        = np.c_[x_res, y_res]
      np.savetxt(filename_tmp, output_tmp, header=header_tmp, delimiter=delimiter_tmp, comments=comments_tmp )

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
