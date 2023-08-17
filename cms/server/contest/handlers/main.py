#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2018 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2015-2016 William Di Luigi <williamdiluigi@gmail.com>
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

"""Non-categorized handlers for CWS.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import ipaddress
import itertools
import json
import logging

import tornado.web

from cms import config
from cms.db import PrintJob, User, Participation
from cms.grading.steps import COMPILATION_MESSAGES, EVALUATION_MESSAGES
from cms.server import multi_contest
from cms.server.contest.authentication import validate_login
from cms.server.contest.communication import get_communications
from cms.server.contest.printing import accept_print_job, PrintingDisabled, \
    UnacceptablePrintJob
from cmscommon.datetime import make_datetime, make_timestamp

from ..phase_management import actual_phase_required

from .contest import ContestHandler


logger = logging.getLogger(__name__)


# Dummy function to mark translatable strings.
def N_(msgid):
    return msgid


class MainHandler(ContestHandler):
    """Home page handler.

    """
    @multi_contest
    def get(self):
        # Allow students to self register
        # for practice contests
        # FIXME: Hackily check if "ractice"
        # (as in "practice") is in the contest
        # title.
        if self.contest.description and "ractice" in self.contest.description:
            self.r_params["allow_self_rego"] = True
        else:
            self.r_params["allow_self_rego"] = False
        self.render("overview.html", **self.r_params)


class LoginHandler(ContestHandler):
    """Login handler.

    """
    @multi_contest
    def post(self):
        error_args = {"login_error": "true"}
        next_page = self.get_argument("next", None)
        if next_page is not None:
            error_args["next"] = next_page
            if next_page != "/":
                next_page = self.url(*next_page.strip("/").split("/"))
            else:
                next_page = self.url()
        else:
            next_page = self.contest_url()
        error_page = self.contest_url(**error_args)

        username = self.get_argument("username", "")
        password = self.get_argument("password", "")

        try:
            # In py2 Tornado gives us the IP address as a native binary
            # string, whereas ipaddress wants text (unicode) strings.
            ip_address = ipaddress.ip_address(str(self.request.remote_ip))
        except ValueError:
            logger.warning("Invalid IP address provided by Tornado: %s",
                           self.request.remote_ip)
            return None

        participation, cookie = validate_login(
            self.sql_session, self.contest, self.timestamp, username, password,
            ip_address)

        cookie_name = self.contest.name + "_login"
        if cookie is None:
            self.clear_cookie(cookie_name)
        else:
            self.set_secure_cookie(cookie_name, cookie, expires_days=None)

        if participation is None:
            self.redirect(error_page)
        else:
            if not participation.user.email or len(participation.user.email.split(':')) <= 1:
                # If they haven't filled in their details
                # (which are stored as colon delimited string in
                # the email field), send them to the page to fill that in
                self.redirect(self.contest_url("getinfo"))
            else:
                self.redirect(next_page)


class PracticeRegistrationHandler(ContestHandler):
    """Practice rego handler
        
    Allow students to self-register for the practice contest.
    """
    def get(self):
        self.r_params["errors"] = []
        self.r_params["success"] = False
        self.render("practicerego.html", **self.r_params)

    def post(self):
        username = self.get_argument("username", None)

        password = self.get_argument("password", None)
        password2 = self.get_argument("password2", None)
        logger.info("Being asked to do a thing for %s %s", username, password)

        errors = []

        # Check they supplied a username and password
        if not username.isalnum():
            errors.append("Your username must only contain a-zA-Z0-9")
        if not username:
            errors.append("Please supply a username.")
        if not password or not password2:
            errors.append("Please supply a password.")
        if password != password2:
            errors.append("Please make sure the passwords match.")
        if errors:
            # Do not continue if fields did not pass validation
            pass
        # Check that registration is allowed
        elif not self.contest.description or "ractice" not in self.contest.description:
            errors.append("Self-registration is not allowed.")
        # Check that the username is unused.
        elif self.sql_session.query(User).filter(User.username == username).count():
            errors.append("User already exists. Choose another username.")
        else:
            # Create the user, then create the participation object
            new_user = User(
                username=username,
                password="plaintext:"+password,
                first_name="",
                last_name="",
                email="Intermediate")

            self.sql_session.add(new_user)

            new_participation = Participation(
                #contest_id=self.contest.id,
                contest=self.contest,
                #user_id=new_user.id,
                user=new_user)
            self.sql_session.add(new_participation)

            self.sql_session.commit()

        self.r_params["success"] = not errors
        self.r_params["errors"] = errors 
        self.render("practicerego.html", **self.r_params)



class StartHandler(ContestHandler):
    """Start handler.

    Used by a user who wants to start their per_user_time.

    """
    @tornado.web.authenticated
    @actual_phase_required(-1)
    @multi_contest
    def post(self):
        participation = self.current_user

        logger.info("Starting now for user %s", participation.user.username)
        participation.starting_time = self.timestamp
        self.sql_session.commit()

        self.redirect(self.contest_url())


class LogoutHandler(ContestHandler):
    """Logout handler.

    """
    @multi_contest
    def post(self):
        self.clear_cookie(self.contest.name + "_login")
        self.redirect(self.contest_url())


class NotificationsHandler(ContestHandler):
    """Displays notifications.

    """

    refresh_cookie = False

    @tornado.web.authenticated
    @multi_contest
    def get(self):
        participation = self.current_user

        last_notification = self.get_argument("last_notification", None)
        if last_notification is not None:
            last_notification = make_datetime(float(last_notification))

        res = get_communications(self.sql_session, participation,
                                 self.timestamp, after=last_notification)

        # Simple notifications
        notifications = self.service.notifications
        username = participation.user.username
        if username in notifications:
            for notification in notifications[username]:
                res.append({"type": "notification",
                            "timestamp": make_timestamp(notification[0]),
                            "subject": notification[1],
                            "text": notification[2],
                            "level": notification[3]})
            del notifications[username]

        self.write(json.dumps(res))


class PrintingHandler(ContestHandler):
    """Serve the interface to print and handle submitted print jobs.

    """
    @tornado.web.authenticated
    @actual_phase_required(0)
    @multi_contest
    def get(self):
        participation = self.current_user

        if not self.r_params["printing_enabled"]:
            raise tornado.web.HTTPError(404)

        printjobs = self.sql_session.query(PrintJob)\
            .filter(PrintJob.participation == participation)\
            .all()

        remaining_jobs = max(0, config.max_jobs_per_user - len(printjobs))

        self.render("printing.html",
                    printjobs=printjobs,
                    remaining_jobs=remaining_jobs,
                    max_pages=config.max_pages_per_job,
                    pdf_printing_allowed=config.pdf_printing_allowed,
                    **self.r_params)

    @tornado.web.authenticated
    @actual_phase_required(0)
    @multi_contest
    def post(self):
        try:
            printjob = accept_print_job(
                self.sql_session, self.service.file_cacher, self.current_user,
                self.timestamp, self.request.files)
            self.sql_session.commit()
        except PrintingDisabled:
            raise tornado.web.HTTPError(404)
        except UnacceptablePrintJob as e:
            self.notify_error(e.subject, e.text)
        else:
            self.service.printing_service.new_printjob(printjob_id=printjob.id)
            self.notify_success(N_("Print job received"),
                                N_("Your print job has been received."))

        self.redirect(self.contest_url("printing"))


class DocumentationHandler(ContestHandler):
    """Displays the instruction (compilation lines, documentation,
    ...) of the contest.

    """
    @tornado.web.authenticated
    @multi_contest
    def get(self):
        self.render("documentation.html",
                    COMPILATION_MESSAGES=COMPILATION_MESSAGES,
                    EVALUATION_MESSAGES=EVALUATION_MESSAGES,
                    **self.r_params)


class GetInfoHandler(ContestHandler):
    """AIO student details form handler.

       After logging in, contestants are redirected to this form
       to fill in their details.
    """
    @tornado.web.authenticated
    @multi_contest
    def post(self):
        firstname = self.get_argument("firstname", None)
        lastname = self.get_argument("lastname", None)
        gender = self.get_argument("gender", None)
        year = self.get_argument("year", None)
        email = self.get_argument("email", None)

        # No colons as we use it as a delimeter
        firstname = firstname.replace(':', '')
        lastname = lastname.replace(':', '')
        gender = gender.replace(':', '')
        year = year.replace(':', '')
        email = email.replace(':', '')

        # Participations are stored in the database in the email field
        # in the format
        # <"Intermediate" or "Senior":<fullname>:<gender>:<year>:<email>

        # The division is not part of the form, so split that out
        # and prepend it so as not to overwrite it.
        if self.current_user.user.email:
            division = self.current_user.user.email.split(":")[0]
        else:
            # No division set.
            division = ""

        combined = ":".join([division, firstname, lastname, gender, year, email])

        # Verify that the fields are acceptable
        errors = []
        if firstname == "": errors.append("Please enter a first name")
        if lastname == "": errors.append("Please enter a last name")
        if year == "": errors.append("Please enter a year") # Dropdown, so should not happen
        if gender == "": errors.append("Please enter gender") # Dropdown, so should not happen
        if email == "": errors.append("Please enter an email")
        if '@' not in email: errors.append("Please enter a valid email")

        if errors:
            logger.info("Received %s errors %s", combined, str(errors))
            self._return_filled_info_form(combined, errors)
        else:
            self.current_user.user.email = combined

            # Save to the first/last name fields as well, so it says
            # "You are logged in as FirstName LastName (Username)" correctly
            self.current_user.user.first_name = firstname
            self.current_user.user.last_name = lastname

            self.sql_session.commit()

            # Take them back to the main page
            self.redirect(self.contest_url())

    @tornado.web.authenticated
    @multi_contest
    def get(self):
        combined =  self.current_user.user.email
        self._return_filled_info_form(combined, [])

    def _return_filled_info_form(self, combined, errors):
        if combined:
            combined = combined.split(":")
        else:
            combined = []
        fields = [
            "form_division", # Not actually used in the form
            "form_firstname",
            "form_lastname",
            "form_gender",
            "form_year",
            "form_email"
        ]
        for field, value in itertools.zip_longest(fields, combined, fillvalue=""):
            self.r_params[field] = value
        self.r_params["form_errors"] = errors
        self.render("getinfo.html", **self.r_params)

