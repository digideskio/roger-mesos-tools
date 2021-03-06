#!/usr/bin/python

from __future__ import print_function
import argparse
import os
import sys
import statsd
from cli.settings import Settings
from cli.appconfig import AppConfig
import hashlib
import time
import json
from pkg_resources import get_distribution


class Utils:

    def __init__(self):
        self.task_id_value = None

    def roger_version(self, root_dir):
        version = "Unknown!"
        try:
            version = get_distribution('roger_mesos_tools').version
        except Exception:
            fname = os.path.join(root_dir, "VERSION")
            if(os.path.isfile(fname)):
                with open(os.path.join(root_dir, "VERSION")) as f:
                    version = f.read().strip()
        return version

    # Expected format:
    #   moz-content-kairos-7da406eb9e8937875e0548ae1149/v0.46
    def extractFullShaAndVersion(self, image):
        if '-' not in image:
            return ''
        tokens = image.split('-')
        if len(tokens) != 0:
            return tokens[-1]
        else:
            return ''

    # Expected format:
    #   moz-content-kairos-7da406eb9e8937875e0548ae1149/v0.46
    def extractShaFromImage(self, image):
        if '/v' not in image:
            return ''
        sha = image.split('/v')
        if len(sha) != 0:
            sha = sha[0].split('-')
            if len(sha) != 0:
                return sha[-1]
        return ''

    def getStatsClient(self):
        settingObj = Settings()
        appObj = AppConfig()
        config_dir = settingObj.getConfigDir()
        roger_env = appObj.getRogerEnv(config_dir)
        statsd_url = ""
        statsd_port = ""
        if 'statsd_endpoint' in roger_env.keys():
            statsd_url = roger_env['statsd_endpoint']
        if 'statsd_port' in roger_env.keys():
            statsd_port = int(roger_env['statsd_port'])
        return statsd.StatsClient(statsd_url, statsd_port)

    def get_identifier(self, config_name, user_name, app_name):
        hash_value = str(int(time.time())) + "-" + str(hashlib.sha224(config_name + "-" + user_name + "-" + app_name).hexdigest())[:8]
        return hash_value

    def extract_app_name(self, value):
        if ':' in value:
            return value.split(":")[0]
        if '[' in value:
            return value.split("[")[0]
        return value

    def append_arguments(self, statsd_message_list, **kwargs):
        modified_message_list = []
        try:
            for item in statsd_message_list:
                input_metric = item[0]
                for key, value in kwargs.iteritems():
                    input_metric += "," + key + "=" + value
                tup = (input_metric, item[1])
                modified_message_list.append(tup)
        except (Exception) as e:
            print("The following error occurred: %s" %
                  e, file=sys.stderr)
        return modified_message_list

    def modify_task_id(self, task_id_list):
        modified_task_id_list = []
        try:
            for task_id in task_id_list:
                if task_id[0] == '/':
                    task_id = task_id[1:]
                task_id = task_id.replace("/", "_")
                modified_task_id_list.append(task_id)
        except (Exception) as e:
            print("The following error occurred: %s" %
                  e, file=sys.stderr)
        return modified_task_id_list

    def generate_task_id_list(self, data):
        task_id_list = []
        try:
            data_json = json.loads(data)
            top_level = ""
            if 'id' in data_json:
                top_level = data_json['id']
                if 'groups' in data_json:
                    for groups in data_json['groups']:
                        group_level = ""
                        if 'id' in groups:
                            group_level = groups['id']
                        if 'apps' in groups:
                            app_level = ""
                            for app in groups['apps']:
                                if type(app) == list:
                                    for item in app:
                                        if 'id' in item:
                                            app_level = item['id']
                                            task_id_list.append(str(top_level + "/" + group_level + "/" + app_level))
                                else:
                                    if 'id' in app:
                                        app_level = app['id']
                                        task_id_list.append(str(top_level + "/" + group_level + "/" + app_level))
                else:
                    task_id_list.append(str(top_level))
        except (Exception) as e:
            print("The following error occurred: %s" %
                  e, file=sys.stderr)
        return task_id_list

    def get_version(self):
        own_dir = os.path.dirname(os.path.realpath(__file__))
        root = os.path.abspath(os.path.join(own_dir, os.pardir))
        return self.roger_version(root)

    def repo_relative_path(self, appConfig, args, repo, path):
        '''Returns a path relative to the repo, assumed to be under [args.directory]/[repo name]'''
        repo_name = appConfig.getRepoName(repo)
        abs_path = os.path.abspath(args.directory)
        if abs_path == args.directory:
            return "{0}/{1}/{2}".format(args.directory, repo_name, path)
        else:
            return "{0}/{1}/{2}/{3}".format(os.environ.get('PWD', ''),
                                            args.directory, repo_name, path)
