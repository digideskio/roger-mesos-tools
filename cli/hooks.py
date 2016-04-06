#!/usr/bin/python
from __future__ import print_function
import os
import contextlib

@contextlib.contextmanager
def chdir(dirname):
  '''Withable chdir function that restores directory'''
  curdir = os.getcwd()
  try:
    os.chdir(dirname)
    yield
  finally: os.chdir(curdir)

class Hooks:
  def run_hook(self, hookname, appdata, abs_path):
    exit_code = 0
    if "hooks" in appdata and hookname in appdata["hooks"]:
      with chdir(abs_path):
        print("About to run {} hook...".format(hookname))
        exit_code = os.system(appdata["hooks"][hookname])

    return exit_code
