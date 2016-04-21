[![Build Status](https://travis-ci.com/seomoz/roger-mesos-tools.svg?token=6DpHsyxZF1vHyofoTmq1&branch=master)](https://travis-ci.com/seomoz/roger-mesos-tools)

# roger-mesos-tools

Tools to connect to and work with [RogerOS](https://github.com/seomoz/roger-mesos), Moz's cluster OS based on mesos.

### Build
`$ python setup.py build`

### Run tests
`$ python setup.py test`

### Generate source distribution
`$ python setup.py sdist`

### Install
`$ python setup.py install`
OR
`pip install -e .`

### Use
* `roger -h`
* `roger <command> -h`

### With virtualenv
```
virtualenv venv
source venv/bin/activate
pip install -e .
# run roger commands
deactivate
```

### Uninstall
`pip uninstall roger_mesos_tools`
