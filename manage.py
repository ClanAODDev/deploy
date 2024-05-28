#!/usr/bin/python3

import subprocess
import sys
import os
import argparse
import json
import time


def load_config(config_file):
    try:
        with open(config_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Error: Configuration file '{config_file}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Configuration file '{config_file}' is not valid JSON.")
        sys.exit(1)


def main(args):
    config = load_config(args.config if 'config' in args else 'deploy.config.json')
    if 'projects' not in config:
        print("Error: No projects defined in configuration")
        sys.exit(1)

    projects = config['projects']
    project_config = projects.get(args.project_key)

    if project_config is None:
        print(f"Error: No project found for key '{args.project_key}'.")
        sys.exit(1)

    if args.action == 'deploy':
        deploy_project(project_config)
    elif args.action == 'update-php':
        update_php_packages(project_config)
    elif args.action == 'update-npm':
        update_npm_packages(project_config)
    elif args.action == 'restart-supervisor':
        restart_supervisord_process(project_config)
    elif args.action == 'restart-service':
        restart_systemd_service(project_config)
    elif args.action == 'revert-deployment':
        revert_to_last_revision(project_config)
    elif args.action == 'toggle-maintenance':
        toggle_maintenance_mode(project_config)
    elif args.action == 'tracker-sync':
        tracker_forum_sync(project_config)
    else:
        print("Error: Invalid action.")
        sys.exit(1)


def git_fetch_with_retry(project_path, deploying_user, retries=3, delay=10):
    stderr = None
    command = [
        f"cd {project_path}",
        f"sudo -u {deploying_user} git fetch --all"
    ]

    while retries > 0:
        process = subprocess.Popen(
            " && ".join(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        stdout, stderr = process.communicate()
        if process.returncode == 0:
            return True
        retries -= 1
        time.sleep(delay)  # Wait before retrying

    raise Exception(f"Failed to fetch from Git after several retries: {stderr.decode().strip()}")


def restart_supervisord_process(project_config):
    validate_required_params(project_config, [
        'container', 'supervisor_process'
    ])

    container_name = project_config['container']
    process_name = project_config['supervisor_process']
    print(f"Restarting '{process_name}' supervisord process in '{container_name}'")

    command = f"docker exec {container_name} supervisorctl restart {process_name}"
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Successfully restarted '{process_name}' in '{container_name}'")
    except subprocess.CalledProcessError as e:
        print(f"Failed to restart supervisord process '{process_name}' in '{container_name}'.: {e.stderr.decode()}")
        sys.exit(1)


def restart_systemd_service(project_config):
    validate_required_params(project_config, [
        'systemd_service',
    ])

    service_name = project_config['systemd_service']
    print(f"Restarting '{service_name}'")

    command = f"service {service_name} restart"
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Successfully restarted '{service_name}'")
    except subprocess.CalledProcessError as e:
        print(f"Failed to restart service '{service_name}': {e.stderr.decode()}")
        sys.exit(1)


def deploy_project(project_config):
    validate_required_params(project_config, [
        'path', 'branch', 'deploying_user'
    ])

    project_path = project_config['path']
    branch_name = project_config['branch']
    deploying_user = project_config['deploying_user']

    print(f"Deploying {branch_name} to {project_path}")

    if not git_fetch_with_retry(project_path, deploying_user):
        sys.exit(1)

    # Track current revision in case we need to back out
    current_commit_hash = get_commit_hash(deploying_user, project_path)
    last_revision_path = os.path.join(project_path, "LAST_REVISION")
    with open(last_revision_path, 'w') as file:
        file.write(current_commit_hash + "\n")
        print(f"Commit {current_commit_hash} stored as last revision")
    remote_branches = subprocess.getoutput(
        f"cd {project_path} && sudo -u {deploying_user} git branch -r"
    )

    if f"origin/{branch_name}" not in remote_branches:
        print(f"Error: Branch '{branch_name}' does not exist on the remote")
        sys.exit(1)

    # Check for unstaged changes
    status_check = subprocess.getoutput(
        f"cd {project_path} && sudo -u {deploying_user} git status --porcelain"
    )
    if status_check:
        print("Error: Unstaged changes detected. Please commit or stash changes before deploying.")
        sys.exit(1)

    commands = [
        f"sudo -u {deploying_user} git fetch --all > /dev/null",
        f"sudo -u {deploying_user} git checkout {branch_name} > /dev/null",
        f"sudo -u {deploying_user} git reset --hard origin/{branch_name} > /dev/null",
        f"sudo -u {deploying_user} git submodule update --init --recursive > /dev/null"
    ]
    command_str = " && ".join([f"cd {project_path}"] + commands)

    process = subprocess.Popen(
        command_str,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True
    )
    stdout, stderr = process.communicate()

    # gracefully handle deploying Laravel projects
    if 'container' in project_config:
        try:
            docker_command = f"docker exec -u {deploying_user} {project_config['container']} /usr/local/bin/php {project_path}/artisan migrate --force"
            result = subprocess.run(docker_command, shell=True, check=True, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            print(result.stdout)
            if result.stderr:
                print(f"Warnings/Errors during migration: {result.stderr}", file=sys.stderr)
            print("Database migrations completed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to run database migrations: {e.stderr.decode()}")

    check_sqlite_perms(os.path.join(project_path, "storage", "database.sqlite"))

    new_commit_hash = get_commit_hash(deploying_user, project_path)

    print(f"Branch {branch_name} at {new_commit_hash} deployed to {project_path} successfully")

    if process.returncode != 0:
        raise Exception(f"Deployment failed: {stderr.decode().strip()}")


def get_commit_hash(deploying_user, project_path):
    commit_hash_command = f"sudo -u {deploying_user} git -C {project_path} rev-parse --short HEAD"
    try:
        completed_process = subprocess.run(commit_hash_command, shell=True, check=True, text=True,
                                           stdout=subprocess.PIPE)
        current_commit_hash = completed_process.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Failed to get current commit hash: {e.stderr}")
        sys.exit(1)
    return current_commit_hash


def check_sqlite_perms(database_file):
    if os.path.exists(database_file):
        command = f"chown nginx:nginx-data {database_file}"
        try:
            subprocess.run(command, check=True, shell=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to change ownership: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")


def revert_to_last_revision(project_config):
    validate_required_params(project_config, [
        'path', 'deploying_user'
    ])

    project_path = project_config['path']
    deploying_user = project_config['deploying_user']
    last_revision_path = os.path.join(project_path, "LAST_REVISION")

    if not os.path.exists(last_revision_path):
        print(f"No LAST_REVISION file found at {last_revision_path}. Reversion cannot proceed.")
        sys.exit(1)

    with open(last_revision_path, 'r') as file:
        last_commit_hash = file.readline().strip()

    if not last_commit_hash:
        print("LAST_REVISION file is empty. Reversion cannot proceed.")
        sys.exit(1)

    check_commit_command = f"sudo -u {deploying_user} git -C {project_path} cat-file -t {last_commit_hash}"
    try:
        subprocess.run(check_commit_command, shell=True, check=True, stdout=subprocess.PIPE)
    except subprocess.CalledProcessError:
        print(f"Commit {last_commit_hash} does not exist in the repository. Reversion cannot proceed.")
        sys.exit(1)

    revert_command = f"sudo -u {deploying_user} git -C {project_path} reset --hard {last_commit_hash}"
    try:
        subprocess.run(revert_command, shell=True, check=True)
        print(f"Successfully reverted to commit {last_commit_hash}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to revert to commit {last_commit_hash}: {e.stderr.decode()}")
        sys.exit(1)


def update_php_packages(project_config):
    validate_required_params(project_config, [
        'path', 'deploying_user', 'container'
    ])

    project_path = project_config['path']
    deploying_user = project_config['deploying_user']
    container_name = project_config['container']
    print(f"Updating PHP composer packages in {project_path}")

    if not os.path.exists(os.path.join(project_path, "composer.json")):
        print(f"Error: No 'composer.json' found in the project directory. This is not a PHP project.")
        sys.exit(1)

    docker_command = f"docker exec -u {deploying_user} {container_name} /bin/bash -c 'cd {project_path} && composer update --no-interaction --no-dev'"
    command = f"{docker_command} > /dev/null"

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            raise Exception("PHP package update failed: " + stderr.decode().strip())

        print("PHP package update successful")
    except Exception as e:
        print("An error occurred during PHP package update: " + str(e))
        sys.exit(1)


def update_npm_packages(project_config):
    if 'block_npm_updates' in project_config and project_config['block_npm_updates'] is True:
        print("Error: This project does not allow NPM updates.")
        sys.exit(1)

    validate_required_params(project_config, [
        'path', 'deploying_user'
    ])

    project_path = project_config['path']
    deploying_user = project_config['deploying_user']
    print(f"Updating NPM packages in {project_path}")

    if not os.path.exists(os.path.join(project_path, "package.json")):
        print(f"Error: No 'package.json' found in the project directory. Not a Node.js project.")
        sys.exit(1)

    command = f"cd {project_path} && sudo -u {deploying_user} npm update > /dev/null"

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            raise Exception("NPM package update failed: " + stderr.decode().strip())

        print("NPM package update successful.")
    except Exception as e:
        print("An error occurred during NPM package update: " + str(e))


def toggle_maintenance_mode(project_config):
    validate_required_params(project_config, [
        'path', 'deploying_user', 'container',
    ])

    project_path = project_config['path']
    deploying_user = project_config['deploying_user']

    artisan_path = os.path.join(project_path, 'artisan')
    maintenance_file = os.path.join(project_path, 'storage', 'framework', 'maintenance.php')

    if not os.path.exists(artisan_path):
        print(f"Error: Maintenance not supported for this project. Operation aborted.")
        sys.exit(1)

    action = 'up' if os.path.exists(maintenance_file) else 'down'

    command = f"docker exec -u {deploying_user} {project_config['container']} /usr/local/bin/php {artisan_path} {action}"

    try:
        subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Successfully changed maintenance mode to '{action}'.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to change maintenance mode: {e.stderr.decode()}")
        sys.exit(1)


def tracker_forum_sync(project_config):
    validate_required_params(project_config, [
        'path', 'cron_user', 'container'
    ])

    project_path = project_config['path']
    cron_user = project_config['cron_user']
    artisan_path = os.path.join(project_path, 'artisan')

    check_sqlite_perms(os.path.join(project_path, "storage", "database.sqlite"))

    command = f"docker exec -u {cron_user} {project_config['container']} /usr/local/bin/php {artisan_path} do:membersync"

    try:
        subprocess.run(command, shell=True, check=True)
        print(f"Member sync completed")
    except subprocess.CalledProcessError as e:
        print(f"Member sync failed: {e.stderr.decode()}")
        sys.exit(1)


def validate_required_params(project_config, required_params):
    for key in required_params:
        if key not in project_config:
            print(f"Error: {key.replace('_', ' ').capitalize()} is required.")
            sys.exit(1)


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("Must be run as root")
        sys.exit(1)
    parser = argparse.ArgumentParser(description="Manage project deployments and updates.")
    parser.add_argument("project_key", help="Project key which includes the project and branch info")
    parser.add_argument("action", choices=[
        'deploy',
        'update-php',
        'update-npm',
        'restart-supervisor',
        'restart-service',
        'revert-deployment',
        'toggle-maintenance',
        'tracker-sync',
    ], help="Action to perform")
    parser.add_argument("--config", help="Project configuration file")

    args = parser.parse_args()
    main(args)
