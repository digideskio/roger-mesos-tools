#!/usr/bin/python

from __future__ import print_function
import argparse
import json
import os
import sys

import contextlib

@contextlib.contextmanager
def chdir(dirname):
  '''Withable chdir function that restores directory'''
  curdir = os.getcwd()
  try:
    os.chdir(dirname)
    yield
  finally: os.chdir(curdir)

def parse_args():
  parser = argparse.ArgumentParser(description='Builds the docker application and optionally pushes it to the docker registry.')
  parser.add_argument('app_name', metavar='app_name',
    help="Application name to be built. Example: 'agora' or 'grafana'")
  parser.add_argument('directory', metavar='directory',
    help="The working directory where the repository is checked out. Example: '/home/vagrant/work_dir'")
  parser.add_argument('tag_name', metavar='tag_name',
    help="Image name to be tagged including version (if needed). Example: 'roger-collectd:0.20' or 'grafana-v2.1.3'")
  parser.add_argument('config_file', metavar='config_file',
    help="Configuration file to be used for the project. Example: 'content.json' or 'kwe.json'")
  parser.add_argument('--push', '-p', help="Also push to registry. Defaults to false.", action="store_true")
  return parser

def main():
  parser = parse_args()
  args = parser.parse_args()
  config_dir = ''
  if "ROGER_CONFIG_DIR" in os.environ:
    config_dir = os.environ.get('ROGER_CONFIG_DIR')
  if config_dir.strip() == '':
    sys.exit("Environment variable $ROGER_CONFIG_DIR is not set")
  config_dir = os.path.abspath(config_dir)
  with open('{0}/{1}'.format(config_dir, args.config_file)) as config:
    config = json.load(config)

  with open('{0}/roger-env.json'.format(config_dir)) as roger_env:
    roger_env = json.load(roger_env)

  if 'registry' not in roger_env:
    sys.exit('Registry not found in roger-env.json file.')

  if args.app_name not in config['apps']:
    sys.exit('Application specified not found.')

  common_repo = config.get('repo', '')
  data = config['apps'][args.app_name]
  repo = ''
  if common_repo != '':
    repo = data.get('repo', common_repo)
  else:
    repo = data.get('repo', args.app_name)

  projects = data.get('privateProjects', 'none')
  docker_path = data.get('path', 'none')

  # get/update target source(s)
  file_exists = True
  file_path = ''
  if docker_path != 'none':
    file_path = "{0}/{1}/{2}".format(os.path.abspath(args.directory), repo, docker_path)
  else:
    file_path = "{0}/{1}".format(os.path.abspath(args.directory), repo)

  file_exists = os.path.exists("{0}/Dockerfile".format(file_path))

  if file_exists:
    os.system("docker-build '{0}' '{1}' '{2}' '{3}' '{4}'".format(os.path.abspath(args.directory), repo, projects, docker_path, args.tag_name))
    image = "{0}/{1}".format(roger_env['registry'], args.tag_name)
    os.system("docker tag -f {0} {1}".format(args.tag_name, image))
    build_message = "Image {0} built".format(args.tag_name)
    if(args.push):
        os.system("docker push {0}".format(image))
        build_message += " and pushed to registry {}".format(roger_env['registry'])
    print(build_message)
  else:
    print("Dockerfile does not exist in {0} dir:".format(file_path))

if __name__ == "__main__":
  main()