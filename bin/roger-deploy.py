#!/usr/bin/python

from __future__ import print_function
from tempfile import mkdtemp
import argparse
from decimal import *
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import subprocess
import json
import os
import requests
import sys
import re
import shutil

import contextlib

@contextlib.contextmanager
def chdir(dirname):
  '''Withable chdir function that restores directory'''
  curdir = os.getcwd()
  try:
    os.chdir(dirname)
    yield
  finally: os.chdir(curdir)

#To remove a temporary directory created by roger-deploy if this script exits
def tempDirCheck(rm_work_dir, work_dir):
  if rm_work_dir == True:
    exists = os.path.exists(os.path.abspath(work_dir))
    if exists:
      shutil.rmtree(work_dir)
      print("Deleting temporary dir:{0}".format(work_dir))

class Slack:
  def __init__(self, config, token_file):
    self.disabled = True
    try:
      from slackclient import SlackClient
    except:
      print("Warning: SlackClient library not found, not using slack\n", file=sys.stderr)
      return

    try:
      self.channel = config['channel']
      self.method = config['method']
      self.username = config['username']
      self.emoji = config['emoji']
    except (TypeError, KeyError) as e:
      print("Warning: slack not setup in config (error: %s). Not using slack.\n" % e, file=sys.stderr)
      return

    try:
      with open(token_file) as stoken:
        r = stoken.readlines()
      slack_token = ''.join(r).strip()
      self.client = SlackClient(slack_token)
    except IOError:
      print("Warning: slack token file %s not found/readable. Not using slack.\n" % token_file, file=sys.stderr)
      return

    self.disabled = False

  def api_call(self, text):
    if not self.disabled:
      self.client.api_call(self.method, channel=self.channel, username=self.username, icon_emoji=self.emoji, text=text)


# Author: cwhitten
# Purpose: Initial plumbing for a standardized deployment
#          process into the ClusterOS
#
# Keys off of a master config file in APP_ROOT/config/
#   with the naming convention APP_NAME.json
# Container-specific Marathon files live in APP_ROOT/templates/ with the
#   naming convention APP_NAME-SERVICE_NAME.json
#
# See README for details and intended use.
#
# Attempts to get a version from an existing image on marathon (formatting rules apply)

# Expected format:
#   <host>:<port>/moz-content-agora-7da406eb9e8937875e0548ae1149/v0.46
def getNextVersion(config, roger_env, application, branch, work_dir, repo, args):
  sha = getGitSha(work_dir, repo, branch)
  docker_search = subprocess.check_output("docker search {0}/{1}-{2}".format(roger_env['registry'], config['name'], application), shell=True)
  image_version_list = []
  version = ''
  envs = ['prod', 'stage', 'dev', 'test']
  for line in docker_search.split('\n'):
    image = line.split(' ')[0]
    matchObj = re.match("^{0}-{1}-.*/v.*".format(config['name'], application), image)
    if matchObj and matchObj.group().startswith(config['name'] + '-' + application):
      skip_image = False
      for env in envs:
        if matchObj.group().startswith("{0}-{1}-{2}".format(config['name'], application, env)):
          skip_image = True
          break
      if skip_image == False:
        image_version_list.append(matchObj.group().split('/v')[1])

  if len(image_version_list) == 0:	#Create initial version
    version = "{0}/v0.1.0".format(sha)
    print("No version currently exist in the Docker Registry.Deploying version:{0}".format(version))
  else:
    version = incrementVersion(sha, image_version_list, args)
  return version

def incrementVersion(sha, image_version_list, args):
  latest = max(image_version_list, key=splitVersion)
  ver_tuple = splitVersion(latest)
  latest_version = ''
  if args.incr_major:
    latest_version = "{0}/v{1}.0.0".format(sha, (int(ver_tuple[0])+1))
    return latest_version
  if args.incr_patch:
    latest_version = "{0}/v{1}.{2}.{3}".format(sha, int(ver_tuple[0]), int(ver_tuple[1]), (int(ver_tuple[2])+1))
    return latest_version
    
  latest_version = "{0}/v{1}.{2}.0".format(sha, int(ver_tuple[0]), (int(ver_tuple[1])+1))
  return latest_version

def splitVersion(version):
  major, _, rest = version.partition('.')
  minor, _, rest = rest.partition('.')
  patch, _, rest = rest.partition('.')
  return int(major), int(minor) if minor else 0, int(patch) if patch else 0

# Expected format:
#   <host>:<port>/moz-<project>-<service>-<sha>/v0.46
def getCurrentMarathonVersion(roger_env, environment, application):
  data = getMarathonState(roger_env, environment)
  for app in data['apps']:
    if app['container'] != None:
      docker_image = app['container']['docker']['image']
      if application in docker_image:
        if len(docker_image.split('/v')) == 2:
          #Image format expected moz-content-kairos-7da406eb9e8937875e0548ae1149/v0.46
          return extractFullShaAndVersion(docker_image)
        else:	
          #Docker images of the format: grafana/grafana:2.1.3 or postgres:9.4.1 
          return docker_image

# Expected format:
#   moz-content-kairos-7da406eb9e8937875e0548ae1149/v0.46
def extractFullShaAndVersion(image):
  return image.split('-')[3]

# Expected format:
#   moz-content-kairos-7da406eb9e8937875e0548ae1149/v0.46
def extractShaFromImage(image):
  sha = image.split('/')
  if sha != None and sha[1] != None:
    sha = sha[1].split('-')
    if sha[3] != None:
      return sha[3]
  return ''

def getCurrentChronosVersion(roger_env, environment, application):
  data = getChronosState(roger_env, environment)
  for app in data:
    if 'name' in app:
      if application in app['name'] and 'container' in app:
        docker_image = app['container']['image']
        if len(docker_image.split('/v')) == 2:
          #Image format expected moz-content-kairos-7da406eb9e8937875e0548ae1149/v0.46
          return extractFullShaAndVersion(docker_image)
        else:
          #Docker images of the format: grafana/grafana:2.1.3 or postgres:9.4.1
          return docker_image 

def getMarathonState(roger_env, environment):
  url = roger_env['environments'][environment]['marathon_endpoint']+"/v2/apps"
  resp = requests.get(url)
  return resp.json()

def getChronosState(roger_env, environment):
  url = roger_env['environments'][environment]['chronos_endpoint']+"/scheduler/jobs"
  resp = requests.get(url)
  return resp.json()

def getGitSha(work_dir, repo, branch):
  with chdir("{0}/{1}".format(work_dir, repo)):
    proc = subprocess.Popen(
        ["git rev-parse origin/{} --verify HEAD".format(branch)],
        stdout=subprocess.PIPE, shell=True)

    out = proc.communicate()
    return out[0].split('\n')[0]

def parseArgs():
  parser = argparse.ArgumentParser(description='Pulls code from repo, builds and then deploys into Roger.')
  parser.add_argument('-e', '--environment', metavar='env',
    help="Environment to deploy to. example: 'dev' or 'stage'")
  parser.add_argument('application', metavar='application',
    help="Application to be deployed. example: 'all' or 'kairos'")
  parser.add_argument('-b', '--branch', metavar='branch',
    help="Branch to be deployed.Defaults to master. example: 'production' or 'master'")
  parser.add_argument('-s', '--skip-build', action="store_true",
    help="Flag that skips roger-build when set to true. Defaults to false.'")
  parser.add_argument('config_file', metavar='config_file',
    help="Configuration file to be used for the project. example: 'content.json' or 'kwe.json'")
  parser.add_argument('-M', '--incr-major', action="store_true",
    help="Increment major in version. Defaults to false.'")
  parser.add_argument('-p', '--incr-patch', action="store_true",
    help="Increment patch in version. Defaults to false.'") 
  return parser

def main():
  config_dir = ''
  if "ROGER_CONFIG_DIR" in os.environ:
    config_dir = os.environ.get('ROGER_CONFIG_DIR')
  if config_dir.strip() == '':
    sys.exit("Environment variable $ROGER_CONFIG_DIR is not set")
  config_dir = os.path.abspath(config_dir)

  parser = parseArgs()
  args = parser.parse_args()

  with open('{0}/roger-env.json'.format(config_dir)) as roger_env:
    roger_env = json.load(roger_env)

  with open('{0}/{1}'.format(config_dir, args.config_file)) as config:
    config = json.load(config)

  if args.application not in config['apps']:
    sys.exit('Application specified not found.')

  if 'registry' not in roger_env:
    sys.exit('Registry not found in roger-env.json file.')

  #Setup for Slack-Client, token, and git user
  slack = Slack(config['notifications'], '.slack_token')

  if args.application == 'all':
    apps = config['apps'].keys()
  else:
    apps = [args.application]

  common_repo = config.get('repo', '')
  environment = roger_env.get('default', '')

  work_dir = ''
  rm_work_dir = False
  if "ROGER_DEPLOY_SOURCE_DIR" in os.environ:
    work_dir = os.environ.get('ROGER_DEPLOY_SOURCE_DIR')
  if work_dir.strip() == '':
    work_dir = mkdtemp()
    rm_work_dir = True
    print("Environment variable $ROGER_DEPLOY_SOURCE_DIR is not set. Created a temporary dir: {0}".format(work_dir))

  if args.environment is None:
    if "ROGER_ENV" in os.environ:
      env_var = os.environ.get('ROGER_ENV')
      if env_var.strip() == '':
        print("Environment variable $ROGER_ENV is not set. Using the default set from roger-env.json file")
      else:
        print("Using value {} from environment variable $ROGER_ENV".format(env_var))
        environment = env_var
  else:
    environment = args.environment

  if environment not in roger_env['environments']:
    tempDirCheck(rm_work_dir, work_dir)
    sys.exit('Environment not found in roger-env.json file.')

  branch = "master"     #master by default
  if not args.branch is None:
    branch = args.branch

  for app in apps:
    deployApp(args, config, roger_env, work_dir, rm_work_dir, environment, app, branch, slack, args.config_file, common_repo)

def deployApp(args, config, roger_env, work_dir, rm_work_dir, environment, app, branch, slack, config_file, common_repo):
  startTime = datetime.now()
  environmentObj = roger_env['environments'][environment]
  data = config['apps'][app]
  framework = "marathon"  #Default framework is Marathon
  if 'framework' in data:
    framework = data['framework']

  repo = ''
  if common_repo != '':
    repo = data.get('repo', common_repo)
  else:
    repo = data.get('repo', args.application)

  image_name = ''
  image = ''

  # get/update target source(s)
  try:
    exit_code = os.system("roger-git-pull.py {0} {1} {2} --branch {3}".format(app, os.path.abspath(work_dir), config_file, branch))
    if exit_code != 0:
      tempDirCheck(rm_work_dir, work_dir)
      sys.exit('Exiting')
  except (IOError) as e:
    print("The folowing error occurred.(Error: %s).\n" % e, file=sys.stderr)
    tempDirCheck(rm_work_dir, work_dir)
    sys.exit('Exiting')

  skip_build = False
  if not args.skip_build is None:
    skip_build = args.skip_build

  #Set initial version
  image_git_sha = getGitSha(work_dir, repo, branch)
  image_name = "{0}-{1}-{2}/v0.1.0".format(config['name'], app, image_git_sha)
  
  if skip_build == True:
    curr_image_ver = getCurrentMarathonVersion(roger_env, environment, app)
    if framework.lower() == "chronos":
      curr_image_ver = getCurrentChronosVersion(roger_env, environment, app)
    print("Current image version deployed on {0} is :{1}".format(framework, curr_image_ver))
    if not curr_image_ver is None:
      image_name = "{0}-{1}-{2}".format(config['name'], app, curr_image_ver)
      print("Image current version from {0} endpoint is:{1}".format(framework, image_name))
    else:
      print("Using base version for image:{0}".format(image_name))
  else:
    #Docker build,tag and push
    image_name = getNextVersion(config, roger_env, app, branch, work_dir, repo, args)
    image_name = "{0}-{1}-{2}".format(config['name'], app, image_name)
    print("Bumped up image to version:{0}".format(image_name))
    try:
      exit_code = os.system("roger-build.py --push {0} {1} {2} {3}".format(app, os.path.abspath(work_dir), image_name, config_file))
      if exit_code != 0:
        tempDirCheck(rm_work_dir, work_dir)
        sys.exit('Exiting')
    except (IOError) as e:
      print("The folowing error occurred.(Error: %s).\n" % e, file=sys.stderr)
      tempDirCheck(rm_work_dir, work_dir)
      sys.exit('Exiting')
  print("Version is:"+image_name)

  #Deploying the app to marathon
  try:
    exit_code = os.system("roger-push.py {0} {1} \"{2}\" {3} --env {4}".format(app, os.path.abspath(work_dir), image_name, config_file, environment))
    if exit_code != 0:
      tempDirCheck(rm_work_dir, work_dir)
      sys.exit('Exiting')
  except (IOError) as e:
    print("The folowing error occurred.(Error: %s).\n" % e, file=sys.stderr)
    tempDirCheck(rm_work_dir, work_dir)
    sys.exit('Exiting')

  if rm_work_dir == True:
    exists = os.path.exists(os.path.abspath(work_dir))
    if exists:
      shutil.rmtree(work_dir) 
      print("Deleting temporary dir:{0}".format(work_dir))

  deployTime = datetime.now() - startTime
  git_username = subprocess.check_output("git config user.name", shell=True)
  deployMessage = "{0}'s deploy for {1} / {2} / {3} ({5}) completed in {4} seconds.".format(
    git_username.rstrip(), app, environment, branch, deployTime.total_seconds(), image_name)
  slack.api_call(deployMessage)
  print(deployMessage)


if __name__ == "__main__":
  main()