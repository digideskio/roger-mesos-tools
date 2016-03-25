#!/usr/bin/python

from __future__ import print_function
import unittest
import os
import json
import shutil
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, "cli")))
import roger_gitpull
import argparse
from settings import Settings
from appconfig import AppConfig
from mockito import mock, when, verify
from marathon import Marathon
from gitutils  import GitUtils
from frameworkUtils import FrameworkUtils

#Test basic functionalities of roger-git-pull script
class TestGitPull(unittest.TestCase):

  def setUp(self):
    parser = argparse.ArgumentParser(description='Args for test')
    parser.add_argument('app_name', metavar='app_name',
      help="application for which code is to be pulled. Example: 'agora' or 'grafana'")
    parser.add_argument('directory', metavar='directory',
      help="working directory. The repo has its own directory it this. Example: '/home/vagrant/work_dir'")
    parser.add_argument('-b', '--branch', metavar='branch',
      help="git branch to pull code from. Example: 'production' or 'master'. Defaults to master.")
    parser.add_argument('config_file', metavar='config_file',
      help="configuration file to use. Example: 'content.json' or 'kwe.json'")

    self.settingObj = Settings()
    self.base_dir = self.settingObj.getCliDir()
    self.configs_dir = self.base_dir+"/tests/configs"
    self.work_dir = self.base_dir+"/tests/work_dir"
    self.components_dir = self.base_dir+'/tests/components/dev'
    self.args = parser

    with open(self.configs_dir+'/app.json') as config:
         config = json.load(config)
    with open(self.configs_dir+'/roger-env.json') as roger:
      roger_env = json.load(roger)

    data = config['apps']['grafana_test_app']
    self.roger_env = roger_env
    self.data = data
    self.config = config

    pass

  def test_rogerGitPull(self):
    set_config_dir = ''
    if "ROGER_CONFIG_DIR" in os.environ:
      set_config_dir = os.environ.get('ROGER_CONFIG_DIR')
    os.environ["ROGER_CONFIG_DIR"] = self.configs_dir
    config_file = "app.json"
    work_dir = self.work_dir
    settings = mock(Settings)
    appConfig = mock(AppConfig)
    marathon = mock(Marathon)
    gitObj = mock(GitUtils)
    data = self.data
    config = self.config
    roger_env = self.roger_env
    when(marathon).put(self.components_dir+'/test-roger-grafana.json', roger_env['environments']['dev'], 'grafana_test_app').thenReturn("Response [200]")
    frameworkUtils = mock(FrameworkUtils)
    when(frameworkUtils).getFramework(data).thenReturn(marathon)
    when(settings).getComponentsDir().thenReturn(self.base_dir+"/tests/components")
    when(settings).getSecretsDir().thenReturn(self.base_dir+"/tests/secrets")
    when(settings).getTemplatesDir().thenReturn(self.base_dir+"/tests/templates")
    when(settings).getConfigDir().thenReturn(self.configs_dir)
    when(settings).getCliDir().thenReturn(self.base_dir)
    when(appConfig).getRogerEnv(self.configs_dir).thenReturn(roger_env)
    when(appConfig).getConfig(self.configs_dir, "app.json").thenReturn(config)
    when(appConfig).getAppData(self.configs_dir, "app.json", "grafana_test_app").thenReturn(data)
    args = self.args
    args.app_name = "grafana_test_app"
    args.config_file = config_file
    args.branch = "master"
    args.directory = self.work_dir
    object_list = []
    object_list.append(settings)
    object_list.append(appConfig)
    object_list.append(gitObj)
    roger_gitpull.main(object_list, args)
    with open(self.configs_dir+'/{}'.format(config_file)) as config:
      config = json.load(config)
    exists = os.path.exists(work_dir)
    assert exists == True
    shutil.rmtree(work_dir)
    if set_config_dir.strip() != '':
      os.environ["ROGER_CONFIG_DIR"] = "{}".format(set_config_dir)

  def tearDown(self):
    pass

if __name__ == '__main__':
  unittest.main()
