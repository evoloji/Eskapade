"""Project: Eskapade - A python-based package for data analysis.

Created: 2017/08/08

Description:
    setup script.

Authors:
    KPMG Big Data team, Amstelveen, The Netherlands

Redistribution and use in source and binary forms, with or without
modification, are permitted according to the terms listed in the file
LICENSE.
"""

import logging
import sys

from setuptools import find_packages
from setuptools import setup
from setuptools.command.test import test as TestCommand

from setup_cxx import CMakeExtension, CMakeBuild

NAME = 'Eskapade'

MAJOR = 0
REVISION = 7
PATCH = 0
DEV = False

VERSION = '{major}.{revision}.{patch}'.format(major=MAJOR, revision=REVISION, patch=PATCH)
FULL_VERSION = VERSION
if DEV:
    FULL_VERSION += '.dev'

REQUIREMENTS = [
    'pendulum==1.2.5',
    'jupyter==1.0.0',
    'matplotlib==2.0.2',
    'numpy==1.12.1',
    'scipy==0.19.0',
    'scikit-learn==0.18.1',
    'statsmodels==0.8.0',
    'pandas==0.20.1',
    'tabulate==0.8.2',
    'sortedcontainers==1.5.7',
    'histogrammar==1.0.9',
    'names==0.3.0',
    'fastnumbers==2.0.2',
    'pytest==3.0.7',
    'pytest-pylint==0.7.1'
]
CMD_CLASS = dict()
COMMAND_OPTIONS = dict()

logging.basicConfig()
logger = logging.getLogger(__file__)


def write_version_py(filename: str = 'python/eskapade/version.py') -> None:
    """Write package version to version.py.

    This will ensure that the version in version.py is in sync with us.

    :param filename: The version.py to write too.
    :type filename: str
    :return:
    :rtype: None
    """
    # Do not modify the indentation of version_str!
    version_str = """\"\"\"THIS FILE IS AUTO-GENERATED BY ESKAPADE SETUP.PY.\"\"\"

name = '{name!s}'
version = '{version!s}'
full_version = '{full_version!s}'
release = {is_release!s}
"""

    version_file = open(filename, 'w')
    try:
        version_file.write(version_str.format(name=NAME.lower(),
                                              version=VERSION,
                                              full_version=FULL_VERSION,
                                              is_release=not DEV))
    finally:
        version_file.close()


# Determine if ROOT analysis modules will be installed.
# If ROOT is not set up, ROOT analysis modules are excluded.
EXCLUDE_PACKAGES = []
EXTERNAL_MODULES = []
try:
    import ROOT
    import ROOT.RooFit
    import ROOT.RooStats

    EXTERNAL_MODULES.append(CMakeExtension('eskapade.lib.esroofit', 'cxx/esroofit'))
    CMD_CLASS['build_ext'] = CMakeBuild
    REQUIREMENTS.append('root_numpy==4.7.3')
except ImportError:
    logger.fatal('PyROOT and RooFit are missing! Not going to install ROOT analysis modules!')
    EXCLUDE_PACKAGES.append('*root_analysis*')

# This is for auto-generating documentation.
# One can generate documentation by executing:
# python setup.py build_sphinx -i
HAVE_SPHINX = True
try:
    from sphinx.setup_command import BuildDoc

    cmd_string = 'build_sphinx'

    CMD_CLASS[cmd_string] = BuildDoc
    COMMAND_OPTIONS[cmd_string] = {
        'project': ('setup.py', NAME),
        'version': ('setup.py', VERSION),
        'release': ('setup.py', FULL_VERSION)
    }
except ImportError:
    logger.fatal('Missing Sphinx packages!')
    HAVE_SPHINX = False


class PyTest(TestCommand):
    """A pytest runner helper."""

    user_options = [('pytest-args=', 'a', 'Arguments to pass to pytest')]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = ''

    def run_tests(self):
        import shlex
        # We only install this when needed.
        import pytest
        errno = pytest.main(shlex.split(self.pytest_args))
        sys.exit(errno)


CMD_CLASS['test'] = PyTest


def setup_package() -> None:
    """The main setup method.

    It is responsible for setting up and installing the package.

    It also provides commands for generating docs and running tests.

    To generate sphinx docs execute:

    >>> python setup.py build_sphinx -i

    in the project folder.

    To run tests execute:

    >>> python setup test -a "some pytest test arguments"

    in the project folder.

    :return:
    :rtype: None
    """
    write_version_py()

    # from pkg_resources import Requirement, resource_filename
    # logger.info("Requiremeant = {}".format(resource_filename(Requirement.parse(NAME), 'cxx')))

    setup(name=NAME,
          version=VERSION,
          url='http://eskapade.kave.io',
          license='',
          author='KPMG N.V. The Netherlands',
          author_email='kave@kpmg.com',
          description='Eskapade modular analytics',
          python_requires='>=3.5',
          package_dir={'': 'python'},
          packages=find_packages(where='python', exclude=EXCLUDE_PACKAGES),
          # Setuptools requires that package data are located inside the package.
          # This is a feature and not a bug, see
          # http://setuptools.readthedocs.io/en/latest/setuptools.html#non-package-data-files
          package_data={
              NAME.lower(): ['config/*', 'templates/*', 'data/*', 'tutorials/*.sh']
          },
          install_requires=REQUIREMENTS,
          tests_require=['pytest==3.2.2'],
          ext_modules=EXTERNAL_MODULES,
          cmdclass=CMD_CLASS,
          command_options=COMMAND_OPTIONS,
          # The following 'creates' executable scripts for *nix and Windows.
          # As an added the bonus the Windows scripts will auto-magically
          # get a .exe extension.
          #
          # eskapade: main/app application entry point.
          # eskapade_trial: test entry point.
          entry_points={
              'console_scripts': [
                  'eskapade_ignite = eskapade.entry_points:eskapade_ignite',
                  'eskapade_run = eskapade.entry_points:eskapade_run',
                  'eskapade_trial = eskapade.entry_points:eskapade_trial',
                  'eskapade_generate_link = eskapade.entry_points:eskapade_generate_link',
                  'eskapade_generate_macro = eskapade.entry_points:eskapade_generate_macro',
                  'eskapade_generate_notebook = eskapade.entry_points:eskapade_generate_notebook',
                  'eskapade_bootstrap = eskapade.entry_points:eskapade_bootstrap'
              ]
          }
          )


if __name__ == '__main__':
    setup_package()
