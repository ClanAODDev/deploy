#!/usr/bin/env python3

import unittest
from unittest.mock import patch, mock_open, MagicMock, call
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manage

class TestConfigLoading(unittest.TestCase):
    def test_load_valid_config(self):
        config_data = '{"projects": {"test-project": {"path": "/test"}}}'
        with patch('builtins.open', mock_open(read_data=config_data)):
            config = manage.load_config('test.json')
            self.assertEqual(config['projects']['test-project']['path'], '/test')

    def test_load_missing_config(self):
        with patch('builtins.open', side_effect=FileNotFoundError):
            with self.assertRaises(SystemExit):
                manage.load_config('missing.json')

    def test_load_invalid_json(self):
        with patch('builtins.open', mock_open(read_data='invalid json')):
            with self.assertRaises(SystemExit):
                manage.load_config('invalid.json')

class TestValidateRequiredParams(unittest.TestCase):
    def test_all_params_present(self):
        config = {'path': '/test', 'branch': 'main'}
        manage.validate_required_params(config, ['path', 'branch'])

    def test_missing_param(self):
        config = {'path': '/test'}
        with self.assertRaises(SystemExit):
            manage.validate_required_params(config, ['path', 'branch'])

class TestGitFetchWithRetry(unittest.TestCase):
    @patch('subprocess.Popen')
    @patch('time.sleep')
    def test_successful_fetch(self, mock_sleep, mock_popen):
        process_mock = MagicMock()
        process_mock.returncode = 0
        process_mock.communicate.return_value = (b'', b'')
        mock_popen.return_value = process_mock

        result = manage.git_fetch_with_retry('/test/path', 'testuser')

        self.assertTrue(result)
        mock_popen.assert_called_once()
        mock_sleep.assert_not_called()

    @patch('subprocess.Popen')
    @patch('time.sleep')
    def test_fetch_with_retry(self, mock_sleep, mock_popen):
        process_mock_fail = MagicMock()
        process_mock_fail.returncode = 1
        process_mock_fail.communicate.return_value = (b'', b'error')

        process_mock_success = MagicMock()
        process_mock_success.returncode = 0
        process_mock_success.communicate.return_value = (b'', b'')

        mock_popen.side_effect = [process_mock_fail, process_mock_success]

        result = manage.git_fetch_with_retry('/test/path', 'testuser')

        self.assertTrue(result)
        self.assertEqual(mock_popen.call_count, 2)
        mock_sleep.assert_called_once_with(10)

    @patch('subprocess.Popen')
    @patch('time.sleep')
    def test_fetch_all_retries_fail(self, mock_sleep, mock_popen):
        process_mock = MagicMock()
        process_mock.returncode = 1
        process_mock.communicate.return_value = (b'', b'connection failed')
        mock_popen.return_value = process_mock

        with self.assertRaises(Exception) as context:
            manage.git_fetch_with_retry('/test/path', 'testuser')

        self.assertIn('Failed to fetch from Git', str(context.exception))
        self.assertEqual(mock_popen.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 3)

class TestDeployProject(unittest.TestCase):
    def setUp(self):
        self.project_config = {
            'path': '/test/project',
            'branch': 'main',
            'deploying_user': 'testuser'
        }

    @patch('manage.git_fetch_with_retry')
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('subprocess.getoutput')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_successful_deploy(self, mock_file, mock_exists, mock_getoutput,
                               mock_popen, mock_run, mock_git_fetch):
        mock_git_fetch.return_value = True
        mock_exists.return_value = False
        mock_getoutput.side_effect = [
            'origin/main',
            ''
        ]

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='abc123\n',
            stderr=''
        )

        process_mock = MagicMock()
        process_mock.returncode = 0
        process_mock.communicate.return_value = (b'', b'')
        mock_popen.return_value = process_mock

        manage.deploy_project(self.project_config)

        mock_git_fetch.assert_called_once()
        self.assertTrue(mock_popen.called)

    @patch('manage.git_fetch_with_retry')
    def test_deploy_git_fetch_fails(self, mock_git_fetch):
        mock_git_fetch.return_value = False

        with self.assertRaises(SystemExit):
            manage.deploy_project(self.project_config)

    @patch('manage.git_fetch_with_retry')
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_deploy_commit_hash_fails(self, mock_exists, mock_run, mock_git_fetch):
        from subprocess import CalledProcessError
        mock_git_fetch.return_value = True
        mock_exists.return_value = False
        mock_run.side_effect = CalledProcessError(1, 'git', stderr='Git error')

        with self.assertRaises(SystemExit):
            manage.deploy_project(self.project_config)

    @patch('manage.git_fetch_with_retry')
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('subprocess.getoutput')
    @patch('os.path.exists')
    @patch('os.path.isdir')
    @patch('builtins.open', new_callable=mock_open)
    def test_deploy_laravel_with_migrations(self, mock_file, mock_isdir, mock_exists,
                                           mock_getoutput, mock_popen, mock_run, mock_git_fetch):
        self.project_config['container'] = 'test-container'
        mock_git_fetch.return_value = True
        mock_exists.return_value = False
        mock_isdir.return_value = True
        mock_getoutput.side_effect = ['origin/main', '']

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='abc123\n',
            stderr=''
        )

        process_mock = MagicMock()
        process_mock.returncode = 0
        process_mock.communicate.return_value = (b'', b'')
        mock_popen.return_value = process_mock

        manage.deploy_project(self.project_config)

        migration_calls = [c for c in mock_run.call_args_list
                          if 'artisan migrate' in str(c)]
        self.assertTrue(len(migration_calls) > 0)

    @patch('manage.git_fetch_with_retry')
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('subprocess.getoutput')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='old123\n')
    def test_deploy_updates_last_revision(self, mock_file, mock_exists, mock_getoutput,
                                         mock_popen, mock_run, mock_git_fetch):
        mock_git_fetch.return_value = True
        mock_exists.side_effect = lambda path: 'LAST_REVISION' in path
        mock_getoutput.side_effect = ['origin/main', '']

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='abc123\n'
        )

        process_mock = MagicMock()
        process_mock.returncode = 0
        process_mock.communicate.return_value = (b'', b'')
        mock_popen.return_value = process_mock

        manage.deploy_project(self.project_config)

        write_calls = [c for c in mock_file().write.call_args_list]
        self.assertTrue(any('abc123' in str(c) for c in write_calls))

    @patch('manage.git_fetch_with_retry')
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('subprocess.getoutput')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_deploy_failure_raises_exception(self, mock_file, mock_exists, mock_getoutput,
                                            mock_popen, mock_run, mock_git_fetch):
        mock_git_fetch.return_value = True
        mock_exists.return_value = False
        mock_getoutput.side_effect = ['origin/main', '']

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='abc123\n'
        )

        process_mock = MagicMock()
        process_mock.returncode = 1
        process_mock.communicate.return_value = (b'', b'deployment error')
        mock_popen.return_value = process_mock

        with self.assertRaises(Exception) as context:
            manage.deploy_project(self.project_config)

        self.assertIn('Deployment failed', str(context.exception))

    @patch('manage.git_fetch_with_retry')
    @patch('subprocess.run')
    @patch('subprocess.getoutput')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_deploy_branch_not_exists(self, mock_file, mock_exists,
                                      mock_getoutput, mock_run, mock_git_fetch):
        mock_git_fetch.return_value = True
        mock_exists.return_value = False
        mock_getoutput.side_effect = [
            'origin/develop',
            ''
        ]

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='abc123\n'
        )

        with self.assertRaises(SystemExit):
            manage.deploy_project(self.project_config)

    @patch('manage.git_fetch_with_retry')
    @patch('subprocess.run')
    @patch('subprocess.getoutput')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_deploy_with_unstaged_changes(self, mock_file, mock_exists,
                                          mock_getoutput, mock_run, mock_git_fetch):
        mock_git_fetch.return_value = True
        mock_exists.return_value = False
        mock_getoutput.side_effect = [
            'origin/main',
            'M modified_file.txt'
        ]

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='abc123\n'
        )

        with self.assertRaises(SystemExit):
            manage.deploy_project(self.project_config)

    @patch('manage.git_fetch_with_retry')
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('subprocess.getoutput')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_deploy_with_force(self, mock_file, mock_exists, mock_getoutput,
                               mock_popen, mock_run, mock_git_fetch):
        mock_git_fetch.return_value = True
        mock_exists.return_value = False
        mock_getoutput.side_effect = [
            'origin/main',
            'M modified_file.txt'
        ]

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='abc123\n'
        )

        process_mock = MagicMock()
        process_mock.returncode = 0
        process_mock.communicate.return_value = (b'', b'')
        mock_popen.return_value = process_mock

        manage.deploy_project(self.project_config, force=True)

        git_reset_call = [c for c in mock_run.call_args_list
                         if 'git reset --hard' in str(c)]
        self.assertTrue(len(git_reset_call) > 0)

class TestRestartSupervisord(unittest.TestCase):
    def setUp(self):
        self.project_config = {
            'container': 'test-container',
            'supervisor_process': 'test-process'
        }

    @patch('subprocess.run')
    def test_successful_restart(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        manage.restart_supervisord_process(self.project_config)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn('docker exec', call_args)
        self.assertIn('test-container', call_args)
        self.assertIn('supervisorctl restart', call_args)

    @patch('subprocess.run')
    def test_failed_restart(self, mock_run):
        mock_run.side_effect = Exception("Docker error")

        with self.assertRaises(Exception):
            manage.restart_supervisord_process(self.project_config)

class TestRestartSystemdService(unittest.TestCase):
    def setUp(self):
        self.project_config = {
            'systemd_service': 'test-service'
        }

    @patch('subprocess.run')
    def test_successful_restart(self, mock_run):
        result_mock = MagicMock(returncode=0)
        result_mock.stdout = b'Service restart output\n'
        mock_run.return_value = result_mock
        manage.restart_systemd_service(self.project_config)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn('service test-service restart', call_args)

class TestRevertDeployment(unittest.TestCase):
    def setUp(self):
        self.project_config = {
            'path': '/test/project',
            'deploying_user': 'testuser'
        }

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='abc123\n')
    def test_successful_revert(self, mock_file, mock_exists, mock_run):
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        manage.revert_to_last_revision(self.project_config)

        self.assertEqual(mock_run.call_count, 2)
        revert_call = mock_run.call_args_list[1][0][0]
        self.assertIn('reset --hard abc123', revert_call)
        self.assertIn('sudo -u testuser', revert_call)

    @patch('os.path.exists')
    def test_revert_no_last_revision(self, mock_exists):
        mock_exists.return_value = False

        with self.assertRaises(SystemExit):
            manage.revert_to_last_revision(self.project_config)

class TestUpdatePhpPackages(unittest.TestCase):
    def setUp(self):
        self.project_config = {
            'path': '/test/project',
            'deploying_user': 'testuser',
            'container': 'test-container'
        }

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_successful_update(self, mock_exists, mock_run):
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        manage.update_php_packages(self.project_config)

        call_args = mock_run.call_args[0][0]
        self.assertIn('docker exec', call_args)
        self.assertIn('composer update', call_args)
        self.assertIn('--no-dev', call_args)

    @patch('os.path.exists')
    def test_no_composer_json(self, mock_exists):
        mock_exists.return_value = False

        with self.assertRaises(SystemExit):
            manage.update_php_packages(self.project_config)

class TestUpdateNpmPackages(unittest.TestCase):
    def setUp(self):
        self.project_config = {
            'path': '/test/project',
            'deploying_user': 'testuser'
        }

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_successful_update(self, mock_exists, mock_run):
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        manage.update_npm_packages(self.project_config)

        call_args = mock_run.call_args[0][0]
        self.assertIn('npm update', call_args)

    def test_blocked_npm_updates(self):
        self.project_config['block_npm_updates'] = True

        with self.assertRaises(SystemExit):
            manage.update_npm_packages(self.project_config)

    @patch('os.path.exists')
    def test_no_package_json(self, mock_exists):
        mock_exists.return_value = False

        with self.assertRaises(SystemExit):
            manage.update_npm_packages(self.project_config)

class TestToggleMaintenanceMode(unittest.TestCase):
    def setUp(self):
        self.project_config = {
            'path': '/test/project',
            'deploying_user': 'testuser',
            'container': 'test-container'
        }

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_enable_maintenance(self, mock_exists, mock_run):
        mock_exists.side_effect = lambda path: 'artisan' in path
        mock_run.return_value = MagicMock(returncode=0)

        manage.toggle_maintenance_mode(self.project_config)

        call_args = mock_run.call_args[0][0]
        self.assertIn('down --with-secret', call_args)

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_disable_maintenance(self, mock_exists, mock_run):
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        manage.toggle_maintenance_mode(self.project_config)

        call_args = mock_run.call_args[0][0]
        self.assertIn('up', call_args)

    @patch('os.path.exists')
    def test_not_laravel_project(self, mock_exists):
        mock_exists.return_value = False

        with self.assertRaises(SystemExit):
            manage.toggle_maintenance_mode(self.project_config)

class TestTrackerForumSync(unittest.TestCase):
    def setUp(self):
        self.project_config = {
            'path': '/test/project',
            'cron_user': 'cronuser',
            'container': 'test-container'
        }

    @patch('subprocess.run')
    def test_successful_sync(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        manage.tracker_forum_sync(self.project_config)

        call_args = mock_run.call_args[0][0]
        self.assertIn('docker exec', call_args)
        self.assertIn('artisan do:membersync', call_args)

    @patch('subprocess.run')
    def test_sync_failure(self, mock_run):
        from subprocess import CalledProcessError
        error = CalledProcessError(1, 'docker')
        error.stderr = b'Sync failed'
        mock_run.side_effect = error

        with self.assertRaises(SystemExit):
            manage.tracker_forum_sync(self.project_config)

class TestMain(unittest.TestCase):
    @patch('manage.load_config')
    @patch('manage.deploy_project')
    def test_main_deploy_action(self, mock_deploy, mock_config):
        mock_config.return_value = {
            'projects': {
                'test-key': {'path': '/test', 'branch': 'main', 'deploying_user': 'test'}
            }
        }

        args = MagicMock()
        args.project_key = 'test-key'
        args.action = 'deploy'
        args.config = 'test.json'

        manage.main(args)

        mock_deploy.assert_called_once()

    @patch('manage.load_config')
    def test_main_invalid_project_key(self, mock_config):
        mock_config.return_value = {
            'projects': {
                'test-key': {'path': '/test'}
            }
        }

        args = MagicMock()
        args.project_key = 'invalid-key'
        args.action = 'deploy'
        args.config = 'test.json'

        with self.assertRaises(SystemExit):
            manage.main(args)

    @patch('manage.load_config')
    def test_main_no_projects_in_config(self, mock_config):
        mock_config.return_value = {}

        args = MagicMock()
        args.project_key = 'test-key'
        args.action = 'deploy'
        args.config = 'test.json'

        with self.assertRaises(SystemExit):
            manage.main(args)

    @patch('manage.load_config')
    def test_main_invalid_action(self, mock_config):
        mock_config.return_value = {
            'projects': {
                'test-key': {'path': '/test'}
            }
        }

        args = MagicMock()
        args.project_key = 'test-key'
        args.action = 'invalid-action'
        args.config = 'test.json'

        with self.assertRaises(SystemExit):
            manage.main(args)

class TestEdgeCases(unittest.TestCase):
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_revert_empty_last_revision(self, mock_exists, mock_run):
        mock_exists.return_value = True

        with patch('builtins.open', mock_open(read_data='\n')):
            config = {'path': '/test', 'deploying_user': 'test'}

            with self.assertRaises(SystemExit):
                manage.revert_to_last_revision(config)

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='invalid123\n')
    def test_revert_invalid_commit(self, mock_file, mock_exists, mock_run):
        from subprocess import CalledProcessError
        mock_exists.return_value = True
        mock_run.side_effect = CalledProcessError(1, 'git', stderr='Invalid commit')

        config = {'path': '/test', 'deploying_user': 'test'}

        with self.assertRaises(SystemExit):
            manage.revert_to_last_revision(config)

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_php_update_fails(self, mock_exists, mock_run):
        from subprocess import CalledProcessError
        mock_exists.return_value = True
        mock_run.side_effect = CalledProcessError(1, 'composer')

        config = {
            'path': '/test',
            'deploying_user': 'test',
            'container': 'test-container'
        }

        with self.assertRaises(SystemExit):
            manage.update_php_packages(config)

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_npm_update_fails(self, mock_exists, mock_run):
        from subprocess import CalledProcessError
        mock_exists.return_value = True
        mock_run.side_effect = CalledProcessError(1, 'npm')

        config = {
            'path': '/test',
            'deploying_user': 'test'
        }

        with self.assertRaises(SystemExit):
            manage.update_npm_packages(config)

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_maintenance_toggle_fails(self, mock_exists, mock_run):
        from subprocess import CalledProcessError
        mock_exists.side_effect = lambda path: 'artisan' in path
        error = CalledProcessError(1, 'docker')
        error.stderr = b'Docker error'
        mock_run.side_effect = error

        config = {
            'path': '/test',
            'deploying_user': 'test',
            'container': 'test-container'
        }

        with self.assertRaises(SystemExit):
            manage.toggle_maintenance_mode(config)

if __name__ == '__main__':
    unittest.main()
