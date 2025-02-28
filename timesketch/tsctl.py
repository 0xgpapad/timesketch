#!/usr/bin/python
# Copyright 2015 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""This module is for management of the Timesketch application."""
from __future__ import unicode_literals

import codecs
import sys
import yaml

import six

from flask import current_app

from flask_migrate import MigrateCommand
from flask_script import Command
from flask_script import Manager
from flask_script import Server
from flask_script import Option
from flask_script import prompt_bool
from flask_script import prompt_pass
from sqlalchemy.exc import IntegrityError

from timesketch import version
from timesketch.app import create_app
from timesketch.lib.datastores.opensearch import OpenSearchDataStore
from timesketch.models import db_session
from timesketch.models import drop_all
from timesketch.models.user import Group
from timesketch.models.user import User
from timesketch.models.sketch import SearchIndex
from timesketch.models.sketch import SearchTemplate
from timesketch.models.sketch import Sketch
from timesketch.models.sketch import Timeline


class GetVersion(Command):
    """Returns the version information of Timesketch."""

    # pylint: disable=method-hidden
    def run(self):
        """Return the version information of Timesketch."""
        return 'Timesketch version: {0:s}'.format(
            version.get_version())


class DropDataBaseTables(Command):
    """Drop all database tables."""

    # pylint: disable=method-hidden
    def run(self):
        """Drop all tables after user ha verified."""
        verified = prompt_bool(
            'Do you really want to drop all the database tables?')
        if verified:
            sys.stdout.write('All tables dropped. Database is now empty.\n')
            drop_all()


class GrantUser(Command):
    """Grant a user user access to a sketch."""
    option_list = (
        Option('--username', '-u', dest='username', required=True),
        Option('--sketchId', '-s', dest='sketch_id', required=True), )

    # pylint: disable=arguments-differ, method-hidden
    def run(self, username, sketch_id):
        """Creates the user."""
        if not isinstance(sketch_id, six.text_type):
            sketch_id = codecs.decode(sketch_id, 'utf-8')
        if not isinstance(username, six.text_type):
            username = codecs.decode(username, 'utf-8')
        sketch = Sketch.query.filter_by(id=sketch_id).first()
        user = User.query.filter_by(username=username).first()
        if not sketch:
            sys.stdout.write('No sketch found with this ID.')
        elif not user:
            sys.stdout.write('User [{0:s}] does not exist.\n'.format(
                username))
        else:
            sketch.grant_permission(permission='read', user=user)
            sketch.grant_permission(permission='write', user=user)
            sys.stdout.write('User {0:s} added to the sketch {1:s}.\n'.format(
                username, sketch_id))


class AddUser(Command):
    """Create a new Timesketch user."""
    option_list = (
        Option('--username', '-u', dest='username', required=True),
        Option('--password', '-p', dest='password', required=False), )

    def get_password_from_prompt(self):
        """Get password from the command line prompt."""
        first_password = prompt_pass('Enter password')
        second_password = prompt_pass('Enter password again')
        if first_password != second_password:
            sys.stderr.write('Passwords don\'t match, try again.\n')
            self.get_password_from_prompt()
        return first_password

    # pylint: disable=arguments-differ, method-hidden
    def run(self, username, password):
        """Creates the user."""
        if not password:
            password = self.get_password_from_prompt()
        if not isinstance(password, six.text_type):
            password = codecs.decode(password, 'utf-8')
        if not isinstance(username, six.text_type):
            username = codecs.decode(username, 'utf-8')
        user = User.get_or_create(username=username)
        user.set_password(plaintext=password)
        db_session.add(user)
        db_session.commit()
        sys.stdout.write('User {0:s} created/updated\n'.format(username))


class MakeUserAdmin(Command):
    """Make user into an administrator."""
    option_list = (
        Option('--username', '-u', dest='username', required=True),
        Option(
            '--remove', '-r', dest='remove', action='store_true',
            required=False, default=False),
    )

    # pylint: disable=arguments-differ, method-hidden
    def run(self, username, remove):
        """Adds the admin bit to a user."""
        user = User.query.filter_by(username=username).first()

        if not user:
            sys.stdout.write('User [{0:s}] does not exist.\n'.format(
                username))
            return
        user.admin = not remove
        db_session.add(user)
        db_session.commit()

        if remove:
            sys.stdout.write('User {0:s} is no longer an admin.\n'.format(
                username))
        else:
            sys.stdout.write('User {0:s} is now an admin.\n'.format(username))

class DisableUser(Command):
    """Disable User"""
    option_list = (
        Option('--username', '-u', dest='username', required=True),
    )

    # pylint: disable=arguments-differ, method-hidden
    def run(self, username):
        """Sets the active bit of a user to false."""
        user = User.query.filter_by(username=username).first()

        if not user:
            sys.stdout.write('User [{0:s}] does not exist.\n'.format(
                username))
            return
        user.active = False
        db_session.add(user)
        db_session.commit()

        sys.stdout.write('User {0:s} is deactivated.\n'.format(username))

class EnableUser(Command):
    """Enable User"""
    option_list = (
        Option('--username', '-u', dest='username', required=True),
    )

    # pylint: disable=arguments-differ, method-hidden
    def run(self, username):
        """Sets the active bit of a user to true."""
        user = User.query.filter_by(username=username).first()

        if not user:
            sys.stdout.write('User [{0:s}] does not exist.\n'.format(
                username))
            return
        user.active = True
        db_session.add(user)
        db_session.commit()

        sys.stdout.write('User {0:s} is activated.\n'.format(username))

class ListUsers(Command):
    """List all users."""

    # pylint: disable=arguments-differ, method-hidden
    def run(self):
        """The run method for the command."""
        for user in User.query.all():
            if user.admin:
                extra = ' (admin)'
            else:
                extra = ''
            print('{0:s}{1:s}'.format(user.username, extra))


class AddGroup(Command):
    """Create a new Timesketch group."""
    option_list = (Option('--name', '-n', dest='name', required=True), )

    # pylint: disable=arguments-differ, method-hidden
    def run(self, name):
        """Creates the group."""
        if not isinstance(name, six.text_type):
            name = codecs.decode(name, 'utf-8')
        group = Group.get_or_create(name=name)
        db_session.add(group)
        db_session.commit()
        sys.stdout.write('Group {0:s} created\n'.format(name))


class ListGroups(Command):
    """List all groups."""

    # pylint: disable=arguments-differ, method-hidden
    def run(self):
        """The run method for the command."""
        for group in Group.query.all():
            print(group.name)


class GroupManager(Command):
    """Manage group memberships."""
    option_list = (
        Option(
            '--remove',
            '-r',
            dest='remove',
            action='store_true',
            required=False,
            default=False),
        Option(
            '--expand',
            dest='expand',
            action='store_true',
            required=False,
            default=False),
        Option('--group', '-g', dest='group_name', required=True),
        Option('--user', '-u', dest='user_name', required=False, default=None)
    )

    # pylint: disable=arguments-differ, method-hidden
    def run(self, remove, expand, group_name, user_name):
        """Add the user to the group."""
        if not isinstance(group_name, six.text_type):
            group_name = codecs.decode(group_name, 'utf-8')

        group = Group.query.filter_by(name=group_name).first()

        # List all members of a group and then exit.
        if expand:
            for _user in group.users:
                print(_user.username)
            return

        if not isinstance(user_name, six.text_type):
            user_name = codecs.decode(user_name, 'utf-8')
        user = None
        if user_name:
            user = User.query.filter_by(username=user_name).first()

        # Add or remove user from group
        if remove and user:
            try:
                user.groups.remove(group)
                sys.stdout.write('{0:s} removed from group {1:s}\n'.format(
                    user_name, group_name))
                db_session.commit()
            except ValueError:
                sys.stdout.write('{0:s} is not a member of group {1:s}\n'.
                                 format(user_name, group_name))
        elif user:
            user.groups.append(group)
            try:
                db_session.commit()
                sys.stdout.write('{0:s} added to group {1:s}\n'.format(
                    user_name, group_name))
            except IntegrityError:
                sys.stdout.write('{0:s} is already a member of group {1:s}\n'.
                                 format(user_name, group_name))


class AddSearchIndex(Command):
    """Create a new Timesketch searchindex."""
    option_list = (
        Option('--name', '-n', dest='name', required=True),
        Option('--index', '-i', dest='index', required=True),
        Option('--user', '-u', dest='username', required=True), )

    # pylint: disable=arguments-differ, method-hidden
    def run(self, name, index, username):
        """Create the SearchIndex."""
        datastore = OpenSearchDataStore(
            host=current_app.config['OPENSEARCH_HOST'],
            port=current_app.config['OPENSEARCH_PORT'])
        user = User.query.filter_by(username=username).first()
        if not user:
            sys.stderr.write('User does not exist\n')
            sys.exit(1)
        if not datastore.client.indices.exists(index=index):
            sys.stderr.write('Index does not exist in the datastore\n')
            sys.exit(1)
        if SearchIndex.query.filter_by(name=name, index_name=index).first():
            sys.stderr.write(
                'Index with this name already exist in Timesketch\n')
            sys.exit(1)
        searchindex = SearchIndex(
            name=name, description=name, user=user, index_name=index)
        db_session.add(searchindex)
        db_session.commit()
        searchindex.grant_permission('read')
        sys.stdout.write('Search index {0:s} created\n'.format(name))


class PurgeTimeline(Command):
    """Delete timeline permanently from Timesketch and OpenSearch."""
    option_list = (Option(
        '--index', '-i', dest='index_name', required=True), )

    # pylint: disable=arguments-differ, method-hidden
    def run(self, index_name):
        """Delete timeline in both Timesketch and OpenSearch.

        Args:
            index_name: The name of the index in OpenSearch
        """
        if not isinstance(index_name, six.text_type):
            index_name = codecs.decode(index_name, 'utf-8')

        searchindex = SearchIndex.query.filter_by(
            index_name=index_name).first()

        if not searchindex:
            sys.stdout.write('No such index\n')
            sys.exit()

        datastore = OpenSearchDataStore(
            host=current_app.config['OPENSEARCH_HOST'],
            port=current_app.config['OPENSEARCH_PORT'])

        timelines = Timeline.query.filter_by(searchindex=searchindex).all()
        sketches = [
            t.sketch for t in timelines
            if t.sketch and t.sketch.get_status.status != 'deleted'
        ]
        if sketches:
            sys.stdout.write('WARNING: This timeline is in use by:\n')
            for sketch in sketches:
                sys.stdout.write(' * {0:s}\n'.format(sketch.name))
                sys.stdout.flush()
        really_delete = prompt_bool(
            'Are you sure you want to delete this timeline?')
        if really_delete:
            for timeline in timelines:
                db_session.delete(timeline)
            db_session.delete(searchindex)
            db_session.commit()
            datastore.client.indices.delete(index=index_name)


class SearchTemplateManager(Command):
    """Command Module to manipulate Search templates."""
    option_list = (
        Option('--import', '-i', dest='import_location', required=False),
        Option('--export', '-e', dest='export_location', required=False),
    )

    # pylint: disable=arguments-differ, method-hidden
    def run(self, import_location, export_location):
        """Export/Import search templates to/from file.

        Args:
            import_location: Path to the yaml file to import templates.
            export_location: Path to the yaml file to export templates.
        """

        if export_location:
            search_templates = []
            for search_template in SearchTemplate.query.all():
                labels = []
                for label in search_template.labels:
                    if label.label.startswith('supported_os:'):
                        labels.append(label.label.replace(
                            'supported_os:', ''))
                search_templates.append({
                    'name': search_template.name,
                    'query_string': search_template.query_string,
                    'query_dsl': search_template.query_dsl,
                    'supported_os': labels
                })

            with open(export_location, 'w') as fh:
                yaml.safe_dump(search_templates, stream=fh)

        if import_location:
            try:
                with open(import_location, 'rb') as fh:
                    search_templates = yaml.safe_load(fh)
            except IOError as e:
                sys.stdout.write('Unable to open file: {0!s}\n'.format(e))
                sys.exit(1)

            for search_template in search_templates:
                name = search_template['name']
                query_string = search_template['query_string']
                query_dsl = search_template['query_dsl']

                # Skip search template if already exits.
                if SearchTemplate.query.filter_by(name=name).first():
                    continue

                imported_template = SearchTemplate(
                    name=name,
                    user=User(None),
                    query_string=query_string,
                    query_dsl=query_dsl)

                # Add supported_os labels.
                for supported_os in search_template['supported_os']:
                    label_name = 'supported_os:{0:s}'.format(supported_os)
                    label = SearchTemplate.Label.get_or_create(
                        label=label_name, user=None)
                    imported_template.labels.append(label)

                # Set flag to identify local vs import templates.
                remote_flag = SearchTemplate.Label.get_or_create(
                    label='remote_template', user=None)
                imported_template.labels.append(remote_flag)

                db_session.add(imported_template)
                db_session.commit()


class ListSketches(Command):
    """List all available sketches."""

    # pylint: disable=arguments-differ, method-hidden
    def run(self):
        """The run method for the command."""
        sketches = Sketch.query.all()

        name_len = max([len(x.name) for x in sketches])
        desc_len = max([len(x.description) for x in sketches])

        if not name_len:
            name_len = 5
        if not desc_len:
            desc_len = 10

        fmt_string = '{{0:^3d}} | {{1:{0:d}s}} | {{2:{1:d}s}}'.format(
            name_len, desc_len)

        print('+-'*40)
        print(' ID | Name {0:s} | Description'.format(' '*(name_len-5)))
        print('+-'*40)
        for sketch in sketches:
            status = sketch.get_status.status
            if status == 'deleted':
                continue

            if status == 'archived':
                name = '{0:s} (archived)'.format(sketch.name)
            else:
                name = sketch.name

            print(fmt_string.format(
                sketch.id, name, sketch.description))
            print('-'*80)


class ImportTimeline(Command):
    """Create a new Timesketch timeline from a file."""
    option_list = (
        Option('--file', '-f', dest='file_path', required=True),
        Option('--sketch_id', '-s', dest='sketch_id', required=False),
        Option('--username', '-u', dest='username', required=False),
        Option('--timeline_name', '-n', dest='timeline_name',
               required=False),
    )

    # pylint: disable=arguments-differ, method-hidden, unused-argument
    def run(self, file_path, sketch_id, username, timeline_name):
        """This is the run method."""
        print(
            'This function has been deprecated, please use the '
            'timesketch_importer instead: '
            'https://github.com/google/timesketch/blob/master/'
            'docs/UploadData.md')


def main():
    """Main function of the script, setting up the shell manager."""
    # Setup Flask-script command manager and register commands.
    shell_manager = Manager(create_app)
    shell_manager.add_command('grant_user', GrantUser())
    shell_manager.add_command('add_user', AddUser())
    shell_manager.add_command('make_admin', MakeUserAdmin())
    shell_manager.add_command('list_users', ListUsers())
    shell_manager.add_command('add_group', AddGroup())
    shell_manager.add_command('list_groups', ListGroups)
    shell_manager.add_command('manage_group', GroupManager())
    shell_manager.add_command('add_index', AddSearchIndex())
    shell_manager.add_command('db', MigrateCommand)
    shell_manager.add_command('drop_db', DropDataBaseTables())
    shell_manager.add_command('list_sketches', ListSketches())
    shell_manager.add_command('purge', PurgeTimeline())
    shell_manager.add_command('search_template', SearchTemplateManager())
    shell_manager.add_command('import', ImportTimeline())
    shell_manager.add_command('version', GetVersion())
    shell_manager.add_command('disable_user', DisableUser())
    shell_manager.add_command("enable_user", EnableUser())
    shell_manager.add_command('runserver',
                              Server(host='127.0.0.1', port=5000))
    shell_manager.add_option(
        '-c',
        '--config',
        dest='config',
        default='/etc/timesketch/timesketch.conf',
        required=False)
    shell_manager.run()


if __name__ == '__main__':
    main()
