#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2015 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2018 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2013-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2016 Myungwoo Chun <mc.tamaki@gmail.com>
# Copyright © 2016 Amir Keivan Mohtashami <akmohtashami97@gmail.com>
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

import logging

from cms.locale import DEFAULT_TRANSLATION

from .language import Language, CompiledLanguage


__all__ = [
    # __init__.py
    "JobException", "format_status_text",
    # language.py
    "Language", "CompiledLanguage",
]


logger = logging.getLogger(__name__)


class JobException(Exception):
    """Exception raised by a worker doing a job.

    """
    def __init__(self, msg=""):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)

    def __repr__(self):
        return "JobException(\"%s\")" % (repr(self.msg))


def get_simple_status_text(status):
    mapping_startswith = [
            ("Evaluation didn't produce file", "Output file was not produced. Check you are creating the output file "
                "with name given in the problem statement. You may wish to use or consult the templates for this problem."),
            ("Execution timed out", "Time limit exceeded before your program finished. "
            "This may be due to an infinite loop/recursion, or your "
            "algorithm may be too slow for this subtask"),
            ("Execution killed", "Program crashed. Possibly due to accessing or requesting invalid memory "
            "(e.g. out-of-bounds array access)"),
            ("Execution failed because the return code was nonzero", "Your program did not finish successfully "
            "(return code nonzero). Possibly due to an Exception or Error being thrown."),
    ]
    for old, new in mapping_startswith:
        if status.startswith(old):
            return new
    return status

def format_status_text(status, translation=DEFAULT_TRANSLATION):
    """Format the given status text in the given locale.

    A status text is the content of SubmissionResult.compilation_text,
    Evaluation.text and UserTestResult.(compilation|evaluation)_text.
    It is a list whose first element is a string with printf-like
    placeholders and whose other elements are the data to use to fill
    them.
    The first element will be translated using the given translator (or
    the identity function, if not given), completed with the data and
    returned.

    status ([unicode]): a status, as described above.
    translation (Translation): the translation to use.

    """
    _ = translation.gettext

    try:
        if not isinstance(status, list):
            raise TypeError("Invalid type: %r" % type(status))

        plain = get_simple_status_text(status[0])
        # The empty msgid corresponds to the headers of the pofile.
        text = _(plain) if plain != '' else ''
        return text % tuple(status[1:])
    except Exception:
        logger.error("Unexpected error when formatting status "
                     "text: %r", status, exc_info=True)
        return _("N/A")
