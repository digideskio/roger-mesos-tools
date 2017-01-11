# -*- encoding: utf-8 -*-

"""
Provides a class and script. See bin/roger.py for a reference of how the script
is called.

Promote moves containers between dev, stage, prod environments


:Classes:

RogerPromote: Provides application promotion between environments for the
supported Mesos frameworks.

:Exceptions:

RogerPromoteError: Generic exception for errors in RogerPromote
"""

# ~
# stdlib
import argparse
import tempfile
import os
import os.path
import shutil
import sys
import subprocess

# ~
# core
from cli.settings import Settings
from cli.appconfig import AppConfig
from cli.frameworkUtils import FrameworkUtils
from cli.marathon import Marathon
from cli.chronos import Chronos


def describe():
    return 'Enables application promotion between environments'


class RogerPromoteError(Exception):
    pass


class RogerPromote(object):
    """
    Enable application promotion between environments

    :Params:
    :app_config [cli.appconfig.AppConfig]: Default: cli.appconfig.AppConfig
    :settings [cli.settings.Settings]: Default: cli.settings.Settings
    :framework_utils [cli.framework_utils.FrameworkUtils]:
        Default: cli.framework_utils.FrameworkUtils
    :framework [cli.framework.Framework]: Subclass of Framework
        Default: cli.marathon.Marathon
    """

    def __init__(
        self,
        app_config=AppConfig(),
        settings=Settings(),
        framework_utils=FrameworkUtils(),
        framework=Marathon()
    ):
        self._app_config = app_config
        self._settings = settings
        self._framework_utils = framework_utils
        self._framework = framework
        self._config_dir = None
        self._roger_env = None
        self._temp_dir = None

    @classmethod
    def promote(cls, instance=None):
        """
        :Params:
        :instance [cli.roger_promote.RogerPromote]: Avalailable for test

        :Raises:
        :cli.roger_utils.RogerPromoteError:

        :Return [bool]: True if successful, False if otherwise
        """
        # Get instance
        if instance:  # if the instance is not None,
            rp = instance  # re will equal that instance
        else:
            rp = cls()  # if instance is none then rp with be the class

        # Get Namespace obj
        args = rp.arg_parse().parse_args()

        # Set framework based on app config
        rp._set_framework(args.config, args.app_name)

        # Get deployed version in source environment (should be the image name)
        # image = rp._image_name(args.from_env, args.app_name)

        # Get repo name
        repo = rp._config_resolver('repo', args.app_name, args.config)
        if not repo:
            raise RogerPromoteError('Repo not found')

        # Clone the repo
        rp._clone_repo(repo)

        # Locate roger_push.py
        roger_push = rp._roger_push_script()

        app_data = rp._app_config(self.config_dir, args.config, args.app_name)
        image_refs = app_data['containers']
        failed_images = []
        for image_ref in image_refs:
            template_path = self._get_template_path(
                image_ref,
                self.config_dir,
                args,
                args.app_name
            )

            image_name = rp._image_name(
                args.from_env,
                args.config,
                template_path
            )

            # Execute the script
            cmd = [
                roger_push,
                '--env', args.to_env,
                args.app_name, rp._temp_dir, image_name, args.config
            ]
            string_cmd = ' '.join(cmd)

            ret_val = None
            x = 0
            while x < 3:
                x += 1
                ret_val = os.system(string_cmd)
                if ret_val == 0:
                    break

            if ret_val != 0:
                print("Roger failed to deploy {image} to {env}".format(
                    image_name, args.to
                ))
                failed_images.append(image_name)

        # CleanUp
        shutil.rmtree(rp._temp_dir)
        print("Images that failed")
        if len(failed_images) > 0:
            for failed_image in failed_images:
                print(failed_image)
            return False
        return True

    def arg_parse(self):
        """
        Returns a argparse.NameSpace instance holding argument data
        """
        parser = argparse.ArgumentParser(
            prog='roger promote',
            description=describe()
        )

        env_choices = ['local', 'dev', 'stage', 'prod']

        parser.add_argument(
            'from_env', choices=env_choices, help='The source environment'
        )
        parser.add_argument(
            'to_env', choices=env_choices, help='The destination environment'
        )
        parser.add_argument('config', help='The name of the config file')
        parser.add_argument('app_name', help='The name of the application')

        return parser

    @property
    def framework(self):
        return self._framework

    @property
    def config_dir(self):
        """
        Property that returns the config dir, typically /vagrant/config

        :Return [str]: Path to the configuration directory
        """
        if self._config_dir is None:
            self._config_dir = self._settings.getConfigDir()
        return self._config_dir

    @property
    def roger_env(self):
        """
        Property that returns the dict loaded from
        /vagrant/config/roger-mesos-tools.config

        :Return [dict]: roger-mesos-tools.config loaded into a dict
        """
        if self._roger_env is None:
            self._rover_env = self._app_config.getRogerEnv(self.config_dir)

        return self._rover_env

    def _set_framework(self, config_file, app_name):
        """
        Set the _framework instance variable based on the application config

        :Params:
        :config_file [str]: Name of the configuration file
        :app_name [str]: Name of the application
        """
        app_data = self._app_config.getAppData(
            self.config_dir, config_file, app_name
        )
        self._framework = self._framework_utils.getFramework(app_data)

    def _image_name(self, environment, config_file, template_file):
        """
        Returns the image name as a str

        :Params:
        :roger_env [dict]: Data loaded from roger-mesos-tools.config
        :environment [str]: Environment as found in roger-mesos-tools.config
        :application [str]: application as defined in the appropriate yml or
                            json file under config/

        :Return [str]: image name with version
        """
        username = os.environ['ROGER_USER']
        if environment == 'dev':
            password = os.environ['ROGER_USER_PASS_DEV']
        elif environment == 'stage':
            password = os.environ['ROGER_USER_PASS_STAGE']
        elif environment == 'prod':
            password = os.environ['ROGER_USER_PASS_PROD']

        app_id = self._framework.app_id(template_file)

        image = self._framework.image_name(
            username,
            password,
            environment,
            app_id,
            config_file,
            self.config_dir
        )
        return image

    def _config_resolver(self, key, application, config_file):
        """
        Returns the value for the desired key within the application's
        configuration.

        :Params:
        :key [str]: The key containing the desired value we wish to return
        :application [str]: The application being promoted
        :config_file [str] path to the yml or json file, typically found under
                           /vagrant/config/

        :Return [str]: Returns string if found, otherwise None
        """
        config_data = self._app_config.getConfig(self.config_dir, config_file)
        found = None
        if key in config_data:
            found = config_data[key]
        for name, data in config_data['apps'].items():
            if data['name'] == application:
                if key in data:
                    found = data[key]
                    break
        return found

    def _clone_repo(self, repo):
        """
        Clone the repo

        :Params:
        :repo [str] The name of the repo

        :Raises:
        :subprocess.CalledProcessError:

        :Return: None
        """
        repo_url = self._app_config.getRepoUrl(repo)
        self._temp_dir = tempfile.mkdtemp()
        subprocess.check_call(['git', 'clone', repo_url], cwd=self._temp_dir)

    def _roger_push_script(self):
        """
        Returns path [str] to the roger_push.py executable

        :Return [str]: Path to the script
        """
        code_dir = os.path.abspath(os.path.dirname(__file__))
        return os.path.join(code_dir, 'roger_push.py')

    def _get_template_path(
        self,
        container_name,
        config_dir,
        args,
        app_name,
        app_object=AppConfig(),
        settings_object=Settings()
    ):

        """
        Returns the template path for a given container_name

        Each framework requires an template_path for the app_id method

        :Params:
        :config_dir [str]: path to the config directory
        :args [argparse.NameSpace]: how to get acceses to the values passed
        :app_name [str]: name of app
        :app_object [cli.appconfig.AppConfig]: instance of AppConfig
        :settings_object [cli.settings.Settings]: instance of Settings

        """

        data = app_object.getConfig(config_dir, args.config_file)
        repo = self._config_resolver('repo', app_name, args.config)
        template_path = self._config_resolver(
            'template_path', app_name, args.config)
        if 'template_path' in data:
            app_path = os.path.join(self._temp_dir, repo, template_path)
        else:
            app_path = settings_object.getTemplatesDir()

        file_name = "{0}-{1}.json".format(
                data['name'], container_name)

        return os.path.join(app_path, file_name)


if __name__ == '__main__':
    if not RogerPromote.promote():
        sys.exit(1)
