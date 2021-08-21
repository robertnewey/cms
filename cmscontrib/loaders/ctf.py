#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2017 Kiarash Golezardi <kiarashgolezardi@gmail.com>
# Copyright © 2017 Amir Keivan Mohtashami <akmohtashami97@gmail.com>
# Copyright © 2018 Stefano Maggiolo <s.maggiolo@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import io
import json
import logging
import os
import re
import subprocess
import zipfile

from datetime import timedelta
from tempfile import TemporaryDirectory

from cms.db import Task, Dataset, Manager, Testcase, Attachment, Statement

from .base_loader import TaskLoader

from cmscommon.constants import SCORE_MODE_MAX_SUBTASK


logger = logging.getLogger(__name__)


def make_timedelta(t):
    return timedelta(seconds=t)


class CtfTaskLoader(TaskLoader):
    """Loader for CTF formatted tasks.

    """

    short_name = 'ctf_task'
    description = 'CTF task format'

    @staticmethod
    def detect(path):
        """See docstring in class Loader.

        """
        return os.path.exists(os.path.join(path, "metadata.json"))

    def task_has_changed(self):
        """See docstring in class Loader.

        """
        return True

    def _get_task_type_parameters(self, data, evaluation_param):
        # TODO: Support other task types
        return [
            # TODO: Allow compilation with a grader
            "alone", # Self-sufficient (i.e. not compiled with grader)
            [
                data['input_file'] if 'input_file' in data else '',
                data['output_file'] if 'output_file' in data else '',
            ],
            evaluation_param
        ]

    def get_task(self, get_statement=True):
        """See docstring in class Loader.

        """

        json_src = os.path.join(self.path, 'metadata.json')
        if not os.path.exists(json_src):
            logger.critical('No task found.')
            raise IOError('No task found at path %s' % json_src)

        with io.open(json_src, 'rt', encoding='utf-8') as json_file:
            data = json.load(json_file)
            if 'cms' in data:
                cms_specific_data = data['cms']
                logger.info("%s", str(cms_specific_data))
            else:
                cms_specific_data = {}

        short_name = data['short_name']
        logger.info("Loading parameters for task %s.", short_name)

        ## Args for Task object
        args = {}

        # TODO: We should probably use a friendlier name
        args["name"] = cms_specific_data['name'] if 'name' in cms_specific_data else short_name
        args["title"] = data['problem_name']

        # Statements
        if get_statement:
            statements_dir = os.path.join(self.path, 'statement')
            if os.path.exists(statements_dir):
                statements = [filename for filename in os.listdir(statements_dir) if filename == "statement.pdf"]
                if len(statements) > 2:
                    logger.warning('Found %d statements, this loader can only load 1.' % (len(statements),))
                if len(statements) == 1:
                    logger.info('Statement found')

                    statement = statements[0]
                    args['statements'] = dict()
                    # Just pick english as the primary language
                    args["primary_statements"] = ["en"]
                    digest = self.file_cacher.put_file_from_path(
                        os.path.join(statements_dir, statement),
                        "Statement for task %s" % (short_name,))
                    args['statements']["en"] = Statement("en", digest)

        # Attachments
        args["attachments"] = dict()
        attachments_dir = os.path.join(self.path, 'attachments')
        if os.path.exists(attachments_dir):
            logger.info("Attachments found")
            for filename in sorted(os.listdir(attachments_dir)):
                digest = self.file_cacher.put_file_from_path(
                    os.path.join(attachments_dir, filename),
                    "Attachment %s for task %s" % (filename, short_name))
                args["attachments"][filename] = Attachment(filename, digest)

        args["submission_format"] = ["%s.%%l" % args["name"]]

        # Obtaining testcases' codename
        # FIXME: Unzip or something?
        td = TemporaryDirectory()

        with zipfile.ZipFile(os.path.join(self.path, 'data.zip'), 'r') as zip_ref:
            zip_ref.extractall(td.name)

        testcase_codenames = sorted([
            filename[:-3]
            for filename in os.listdir(td.name)
            if filename[-3:] == '.in'])

        # These options cannot be configured in the CTF format.
        # Uncomment the following to set specific values for them.

        # No user tests for AIO
        # args['max_user_test_number'] = 10
        # args['min_user_test_interval'] = make_timedelta(60)
        # args['min_user_test_interval'] = make_timedelta(60)

        # No tokens for AIO
        # args['token_mode'] = 'infinite'
        # args['token_max_number'] = 100
        # args['token_min_interval'] = make_timedelta(60)
        # args['token_gen_initial'] = 1
        # args['token_gen_number'] = 1
        # args['token_gen_interval'] = make_timedelta(1800)
        # args['token_gen_max'] = 2

        # Takes best score for each subtask
        args['score_mode'] = SCORE_MODE_MAX_SUBTASK

        # Unlimited submissions per problem
        #args['max_submission_number'] = 50
        #args['max_user_test_number'] = 50
        
        # 60 seconds between submissions
        args['min_submission_interval'] = make_timedelta(60)

        # Only integer scores in AIO
        # args['score_precision'] = 2

        # Always give full-feedback in AIO
        args['feedback_level'] = 'full'

        task = Task(**args)

        # Args for test data
        args = dict()

        args["task"] = task
        args["description"] = "Default" # Default dataset
        args["autojudge"] = True

        args["time_limit"] = float(data['timelimit'])
        args["memory_limit"] = int(data['memlimit'])

        args["managers"] = {}

        # Checker
        # TODO: Add support for getting and compiling the checker
        # this is a bit complicated since we need the compilation
        # to happen on the CMS machine.
        evaluation_param = "diff"

        # Note that the original TPS worked with custom task type Batch2017
        # and Communication2017 instead of Batch and Communication.
        # TODO: Support other task types.
        args["task_type"] = "Batch"
        args["task_type_parameters"] = self._get_task_type_parameters(data, evaluation_param)

        # Graders
        # TODO: Add support for getting the grader

        # Manager
        # TODO: Add support for getting the manager

        # Testcases
        args["testcases"] = {}

        # Finally, upload testcases
        for codename in testcase_codenames:
            infile = os.path.join(td.name, "%s.in" % codename)
            outfile = os.path.join(td.name, "%s.out" % codename)
            if not os.path.exists(outfile):
                logger.critical(
                    'Could not find the output file for testcase %s', codename)
                logger.critical('Aborting...')
                return

            input_digest = self.file_cacher.put_file_from_path(
                infile,
                "Input %s for task %s" % (codename, short_name))
            output_digest = self.file_cacher.put_file_from_path(
                outfile,
                "Output %s for task %s" % (codename, short_name))
            testcase = Testcase(codename, True,
                                input_digest, output_digest)
            args["testcases"][codename] = testcase

        # Score Type
        cms_spec_path = os.path.join(self.path, 'cms_spec')
        if not os.path.exists(cms_spec_path):
            logger.critical('Could not find CMS spec. Aborting...')
            return
        with io.open(cms_spec_path, 'rt', encoding='utf-8') as f:
            cms_spec_string = f.read()

        # TODO: Support other score types
        args["score_type"] = "GroupMin"
        args["score_type_parameters"] = json.loads(cms_spec_string)

        dataset = Dataset(**args)
        task.active_dataset = dataset

        logger.info("Task parameters loaded.")

        return task
