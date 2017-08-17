import os
import shutil
import unittest

from eskapade import ConfigObject
from eskapade import process_manager
from eskapade.core import execution, definitions, persistence


class IntegrationTest(unittest.TestCase):
    """Base class for Eskapade integration tests"""

    def setUp(self):
        """Set up test"""

        execution.reset_eskapade()
        proc_mgr = process_manager
        settings = proc_mgr.service(ConfigObject)
        settings['analysisName'] = self.__class__.__name__
        settings['logLevel'] = definitions.LOG_LEVELS['DEBUG']
        settings['batchMode'] = True

    def tearDown(self):
        """Tear down test"""

        # remove persisted results for this test
        path = persistence.io_dir('ana_results', process_manager.service(ConfigObject).io_conf())
        if os.path.exists(path):
            shutil.rmtree(path)

        # reset run process
        execution.reset_eskapade()


class TutorialMacrosTest(IntegrationTest):
    """Integration tests based on tutorial macros"""

    maxDiff = None

    def eskapade_run(self, macro, return_status=definitions.StatusCode.Success):
        """Run Eskapade"""

        proc_mgr = process_manager
        settings = proc_mgr.service(ConfigObject)
        settings['macro'] = macro
        status = execution.run_eskapade(settings)
        self.assertTrue(status == return_status)
