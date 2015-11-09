#!/usr/bin/python

from __future__ import print_function
import argparse
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import requests
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
  parser = argparse.ArgumentParser(description='To deploy an app to Marathon framework.')
  parser.add_argument('app_name', metavar='app_name',
    help="Application to be built. Example: 'agora' or 'grafana'")
  parser.add_argument('-e', '--env', metavar='env',
    help="Environment to deploy to. Example: 'dev' or 'prod'")
  parser.add_argument('directory', metavar='directory',
    help="Working directory where the pulled in repo exists. Template file is under this repo dir. Example: '/home/vagrant/work_dir'")
  parser.add_argument('image_name', metavar='image_name',
    help="Image name that includes version to be used in docker push. Example: 'roger-collectd-v0.20' or 'elasticsearch-v0.07'")
  parser.add_argument('config_file', metavar='config_file',
    help="Configuration file to be used for the project. Example: 'content.json' or 'kwe.json'")
  parser.add_argument('--skip-push', '-s', help="Don't push. Only generate components. Defaults to false.", action="store_true")
  return parser

def loadSecretsJson(environment, jsonFileName):
  path = 'secretenvs/' + environment + '/' + jsonFileName
  try:
    with open(path) as f:
      return json.load(f)
  except IOError:
    print("Couldn't load secrets file environment %s\n" % path, file=sys.stderr)
    return {}

def mergeSecrets(jsonStr, secretsObj):
  '''Given a JSON stirng and an object of secret environment variables, replaces
  parses the JSON and merges ['env'] with the secret variables. Returns back
  a JSON string. Raises an error if there are any SECRET env variables still.'''
  outputObj = json.loads(jsonStr)
  if secretsObj:
    outputObj['env'].update(secretsObj)
    jsonStr = json.dumps(outputObj, indent=4)
  for k, v in outputObj['env'].iteritems():
    if v == 'SECRET':
      raise StandardError('env[%s] is still SECRET -- does your secretenvs file have all secret environment variables?' % k)
  return jsonStr

def renderTemplate(template, environment, image, app_data, config):
    output = ''
    variables = {}
    variables['environment'] = environment
    variables['image'] = image

    #Adding Global and environment variables for all apps
    if 'vars' in config:
      if 'global' in config['vars']:
        for global_var in config['vars']['global']:
          variables[global_var] = config['vars']['global'][global_var]

      if 'environment' in config['vars']:
        if environment in config['vars']['environment']:
          for env_var in config['vars']['environment'][environment]:
            variables[env_var] = config['vars']['environment'][environment][env_var]

    #Adding Global and environment variables for specific app.
    #If the same variable is already present in "variables" dictonary,it will get overriden
    if 'vars' in app_data:
      if 'global' in app_data['vars']:
        for global_var in app_data['vars']['global']:
          variables[global_var] = app_data['vars']['global'][global_var]

      if 'environment' in app_data['vars']:
        if environment in app_data['vars']['environment']:
          for env_var in app_data['vars']['environment'][environment]:
            variables[env_var] = app_data['vars']['environment'][environment][env_var]

    output = template.render(variables)
    return output

def main():
  parser = parse_args()
  args = parser.parse_args()
  config_dir = ''
  if "ROGER_CONFIG_DIR" in os.environ:
    config_dir = os.environ.get('ROGER_CONFIG_DIR')
  if config_dir.strip() == '':
    sys.exit("Environment variable $ROGER_CONFIG_DIR is not set")
  config_dir = os.path.abspath(config_dir)
  
  cur_file_path = os.path.dirname(os.path.realpath(__file__))
  with open('{0}/{1}'.format(config_dir, args.config_file)) as config:
    config = json.load(config)

  with open('{0}/roger-env.json'.format(config_dir)) as roger_env:
    roger_env = json.load(roger_env)

  if 'registry' not in roger_env.keys():
    sys.exit('Registry not found in roger-env.json file.')

  if args.app_name not in config['apps'].keys():
    sys.exit('Application specified not found.')

  environment = roger_env.get('default', '')
  if args.env is None:
    if "ROGER_ENV" in os.environ:
      env_var = os.environ.get('ROGER_ENV')
      if env_var.strip() == '':
        print("Environment variable $ROGER_ENV is not set. Using the default set from roger-env.json file")
      else:
        print("Using value {} from environment variable $ROGER_ENV".format(env_var))
        environment = env_var
  else:
    environment = args.env

  if environment not in roger_env['environments']:
    sys.exit('Environment not found in roger-env.json file.')

  environmentObj = roger_env['environments'][environment]
  common_repo = config.get('repo', '')
  data = config['apps'][args.app_name]
  framework = "marathon"  #Default framework is Marathon
  if 'framework' in data:
    framework = data['framework']

  repo = ''
  if common_repo != '':
    repo = data.get('repo', common_repo)
  else:
    repo = data.get('repo', args.app_name)

  comp_dir = ''
  if "ROGER_COMPONENTS_DIR" in os.environ:
    comp_dir = os.environ.get('ROGER_COMPONENTS_DIR')
  if comp_dir.strip() == '':
    sys.exit("Environment variable $ROGER_COMPONENTS_DIR is not set")
  comp_dir = os.path.abspath(comp_dir)

  templ_dir = ''
  if "ROGER_TEMPLATES_DIR" in os.environ:
    templ_dir = os.environ.get('ROGER_TEMPLATES_DIR')
  if templ_dir.strip() == '':
    sys.exit("Environment variable $ROGER_TEMPLATES_DIR is not set")

  secrets_dir = ''
  if "ROGER_SECRETS_DIR" in os.environ:
    secrets_dir = os.environ.get('ROGER_SECRETS_DIR')
  if secrets_dir.strip() == '':
    sys.exit("Environment variable $ROGER_SECRETS_DIR is not set")
  secrets_dir = os.path.abspath(secrets_dir)

  # template marathon files
  for container in data['containers']:
    containerConfig = "{0}-{1}.json".format(config['name'], container)
    template = ''
    os.chdir(cur_file_path)	#Required for when work_dir,component_dir,template_dir or secret_env_dir is something like '.' or './temp"
    if 'template_path' not in data:
      env = Environment(loader=FileSystemLoader("{}".format(templ_dir)))
    else:
      app_path = "{0}/{1}/{2}".format(os.path.abspath(args.directory), repo, data['template_path'])
      env = Environment(loader=FileSystemLoader("{}".format(app_path)))

    template = env.get_template(containerConfig)
    image_path = "{0}/{1}".format(roger_env['registry'], args.image_name)
    output = renderTemplate(template, environment, image_path, data, config)
    #Adding check so that not all apps try to mergeSecrets
    outputObj = json.loads(output)
    if 'env' in outputObj:
      if "SECRET" in outputObj['env']:
        output = mergeSecrets(output, loadSecretsJson(environment, containerConfig))

    try:
      comp_exists = os.path.exists("{0}".format(comp_dir))
      if comp_exists == False:
        os.mkdir("{0}".format(comp_dir))
      comp_env_exists = os.path.exists("{0}/{1}".format(comp_dir, environment))
      if comp_env_exists == False:
        os.mkdir("{0}/{1}".format(comp_dir, environment))
    except:
      pass
    with open("{0}/{1}/{2}".format(comp_dir, environment, containerConfig), 'wb') as fh:
      fh.write(output)

  if args.skip_push:
      print("Skipping push to {} framework. The rendered config file(s) are under {}/{}".format(framework, comp_dir, environment))
  else:
      # push to roger framework
      for container in data['containers']:
        containerConfig = "{0}-{1}.json".format(config['name'], container)
        config_file_path = "{0}/{1}/{2}".format(comp_dir, environment, containerConfig)
        data = open(config_file_path).read()

        print("TRIGGERING {0} APPLICATION UPDATE FOR: {1}".format(framework.upper(), container))
        appName = ''
        if framework.lower() == "marathon":
          appName = json.loads(data)['id']
        
        #Default endpoint and deploy_url uses Marathon framework
        endpoint = environmentObj['marathon_endpoint']
        deploy_url = "{}/v2/apps/{}".format(endpoint, appName)

        if framework.lower() == "chronos":
          endpoint = environmentObj['chronos_endpoint']
          deploy_url = "{}/scheduler/iso8601".format(endpoint)
        resp = ""
        if 'groups' in data:
          resp = requests.put(
            "{}/v2/groups/{}".format(environmentObj['marathon_endpoint'], appName),
            data=data,
            headers = {'Content-type': 'application/json'})
          print("curl -X PUT -H 'Content-type: application/json' --data-binary @{}/{}/{} {}/v2/groups/{}".format(comp_dir, environment, containerConfig, environmentObj['marathon_endpoint'], appName))
        else:
          resp = requests.put(
            deploy_url,
            data=data,
            headers = {'Content-type': 'application/json'})
          print("curl -X PUT -H 'Content-type: application/json' --data-binary @{}/{}/{} {}".format(comp_dir, environment, containerConfig, deploy_url))
        marathon_message = "{0}: {1}".format(appName, resp)
        print(marathon_message)

if __name__ == "__main__":
  main()