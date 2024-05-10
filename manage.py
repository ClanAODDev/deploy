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
        return

    if args.action == 'deploy':
        print(f"Deploying {project_config['branch']} on {args.project_key}")
        deploy_project(project_config, config['deploying_user'])
    elif args.action == 'update-php':
        print(f"Updating PHP packages for {args.project_key}")
        update_php_packages(project_path, config['DOCKER_PHP_CONTAINER'], config['deploying_user'])
    elif args.action == 'update-node':
        print(f"Updating Node packages for {args.project_key}")
        update_node_packages(project_path, config['deploying_user'])
    elif args.action == 'restart-supervisor':
        if not args.process_name:
            print("Error: Supervisord process name is required for restart.")
        return
        print(f"Restarting {args.process_name} supervisord process")
        restart_supervisord_process(config['DOCKER_PHP_CONTAINER'], args.process_name, config['deploying_user'])
    else:
        print("Error: Invalid action.")

def load_config():
    try:
        with open('config.json', 'r') as file:
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

def restart_supervisord_process(container_name, process_name, deploying_user):
    command = f"sudo -u {deploying_user} docker exec {container_name} supervisorctl restart {process_name}"
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Successfully restarted '{process_name}' in '{container_name}'.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to restart SupervisorD process '{process_name}': {e.stderr.decode()}")
        sys.exit(1)

def deploy_project(project_config, deploying_user):
    project_path = project_config['path']
    branch_name = project_config['branch']

    if not git_fetch_with_retry(project_path, deploying_user):
        return

    remote_branches = subprocess.getoutput(
        f"cd {project_path} && sudo -u {deploying_user} git branch -r"
    )

    if f"origin/{branch_name}" not in remote_branches:
        print(f"Error: Branch '{branch_name}' does not exist on the remote.")
        return

    # Check for unstaged changes
    status_check = subprocess.getoutput(
        f"cd {project_path} && sudo -u {deploying_user} git status --porcelain"
    )
    if status_check:
        print("Error: Unstaged changes detected. Please commit or stash changes before deploying.")
        
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

    if process.returncode != 0:
        raise Exception(f"Deployment failed: {stderr.decode().strip()}")

    print(f"Deployment successful for {branch_name} on {project_path}")

def update_php_packages(project_path, container_name, deploying_user):
    if not os.path.exists(os.path.join(project_path, "composer.json")):
        print(f"Error: No 'composer.json' found in the project directory. This is not a PHP project.")
        return

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

def update_node_packages(project_path, deploying_user):
    if not os.path.exists(os.path.join(project_path, "package.json")):
        print(f"Error: No 'package.json' found in the project directory. Not a Node.js project.")
        return

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
    config = load_config()
    parser = argparse.ArgumentParser(description="Manage project deployments and updates.")
    parser.add_argument("project_key", help="Project key which includes the project and branch info")
    parser.add_argument("action", choices=['deploy', 'update-php', 'update-node', 'restart-supervisor'], help="Action to perform")
    parser.add_argument("--process_name", help="Name of the SupervisorD process to restart, required if action is 'restart-supervisor'")

    args = parser.parse_args()
    main(args, config)