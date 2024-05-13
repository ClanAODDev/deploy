#!/usr/bin/python3

import subprocess
import sys
import os
import argparse
import json

def main(args, config):
    projects = config['projects']
    project_config = projects.get(args.project_key)

    if project_config is None:
        print(f"Error: No project found for key '{args.project_key}'.")
        sys.exit(1)

    if args.action == 'deploy':
        deploy_project(project_config)
    elif args.action == 'update-php':
        update_php_packages(project_config)
    elif args.action == 'update-node':
        update_node_packages(project_config)
    elif args.action == 'restart-supervisor':
        restart_supervisord_process(project_config)
    elif args.action == 'restart-service':
        restart_systemd_service(project_config)
    else:
        print("Error: Invalid action.")
        sys.exit(1)

def load_config():
    try:
        with open('deploy.config.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print("Error: Configuration file 'config.json' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Configuration file 'config.json' is not valid JSON.")
        sys.exit(1)

def git_fetch_with_retry(project_path, deploying_user, retries=3, delay=10):
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
    if project_config['container'] is None:
        print("Error: Container name is required for restart.")
        sys.exit(1)
    if project_config['supervisor_process'] is None:
        print("Error: Supervisord process name is required for restart.")
        sys.exit(1)

    container_name = project_config['container']
    process_name = project_config['supervisor_process']
    print(f"Restarting '{process_name}' supervisord process in '{container_name}'")

    command = f"docker exec {container_name} supervisorctl restart {process_name}"
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Successfully restarted '{process_name}' in '{container_name}'.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to restart supervisord process '{process_name}' in '{container_name}'.: {e.stderr.decode()}")
        sys.exit(1)

def restart_systemd_service(project_config):
    if project_config['systemd_service'] is None:
        print("Error: Systemd service name is required for restart.")
        sys.exit(1)

    service_name = project_config['systemd_service']
    print(f"Restarting '{service_name}'")
    
    command = f"service {service_name} restart"
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Successfully restarted '{service_name}'.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to restart service '{service_name}'.: {e.stderr.decode()}")
        sys.exit(1)

def deploy_project(project_config):
    if project_config['project_path'] is None:
        print("Error: Project path is required.")
        sys.exit(1)
    if project_config['branch_name'] is None:
        print("Error: Branch name is required.")
        sys.exit(1)
    if project_config['deploying_user'] is None:
        print("Error: Deploying user is required.")
        sys.exit(1)

    project_path = project_config['path']
    branch_name = project_config['branch']
    deploying_user = project_config['deploying_user']
    database_file = os.path.join(project_path, "storage", "database.sqlite")
    
    print(f"Deploying {branch_name} to {project_path}")
 
    if not git_fetch_with_retry(project_path, deploying_user):
        sys.exit(1)

    # Track current revision in case we need to back out
    commit_hash_command = f"sudo -u {deploying_user} git -C {project_path} rev-parse HEAD"
    try:
        completed_process = subprocess.run(commit_hash_command, shell=True, check=True, text=True, stdout=subprocess.PIPE)
        current_commit_hash = completed_process.stdout.strip()
        print(f"Current commit hash: {current_commit_hash}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to get current commit hash: {e.stderr}")
        sys.exit(1)
    last_revision_path = os.path.join(project_path, "LAST_REVISION")
    with open(last_revision_path, 'w') as file:
        file.write(current_commit_hash + "\n")
    print(f"Updated LAST_REVISION file at {last_revision_path}")

    remote_branches = subprocess.getoutput(
        f"cd {project_path} && sudo -u {deploying_user} git branch -r"
    )

    if f"origin/{branch_name}" not in remote_branches:
        print(f"Error: Branch '{branch_name}' does not exist on the remote.")
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
            docker_command = f"docker exec {project_config['container']} /usr/bin/php {project_path}/artisan migrate --force"
            subprocess.run(docker_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("Database migrations completed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to run database migrations: {e.stderr.decode()}")

    if process.returncode != 0:
        raise Exception(f"Deployment failed: {stderr.decode().strip()}")

    # Ensure correct ownership of SQLite db
    if os.path.exists(database_file):
        stat_info = os.stat(database_file)
        uid = stat_info.st_uid
        gid = stat_info.st_gid
        nginx_uid = pwd.getpwnam("nginx").pw_uid
        nginx_data_gid = grp.getgrnam("nginx-data").gr_gid

        if uid != nginx_uid or gid != nginx_data_gid:
            os.chown(database_file, nginx_uid, nginx_data_gid)

    print(f"Deployment successful for {branch_name} on {project_path}")

def update_php_packages(project_config):
    if project_config['project_path'] is None:
        print("Error: Project path is required.")
        sys.exit(1)
    if project_config['deploying_user'] is None:
        print("Error: Deploying user is required.")
        sys.exit(1)

    project_path = project_config['path']
    deploying_user = project_config['deploying_user']
    print(f"Updating PHP composer packages in {project_path}")

    if not os.path.exists(os.path.join(project_path, "composer.json")):
        print(f"Error: No 'composer.json' found in the project directory. This is not a PHP project.")
        sys.exit(1)

    docker_command = f"docker exec {container_name} /bin/bash -c 'cd {project_path} && composer update --no-interaction --no-dev'"
    command = f"sudo -u {deploying_user} {docker_command} > /dev/null"

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

        print("PHP package update successful.")
    except Exception as e:
        print("An error occurred during PHP package update: " + str(e))
        sys.exit(1)

def update_node_packages(project_config):
    if project_config['project_path'] is None:
        print("Error: Project path is required.")
        sys.exit(1)
    if project_config['deploying_user'] is None:
        print("Error: Deploying user is required.")
        sys.exit(1)

    project_path = project_config['path']
    deploying_user = project_config['deploying_user']
    print(f"Updating Node packages in {project_path}")

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
            raise Exception("Node.js package update failed: " + stderr.decode().strip())

        print("Node.js package update successful.")
    except Exception as e:
        print("An error occurred during Node.js package update: " + str(e))

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("Must be run as root.")
        sys.exit(1)
    config = load_config()
    parser = argparse.ArgumentParser(description="Manage project deployments and updates.")
    parser.add_argument("project_key", help="Project key which includes the project and branch info")
    parser.add_argument("action", choices=['deploy', 'update-php', 'update-node', 'restart-supervisor', 'restart-service'], help="Action to perform")

    args = parser.parse_args()
    main(args, config)
