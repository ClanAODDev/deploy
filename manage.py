import subprocess
import sys
import os
import argparse
import json

def main(args, config):
    project_paths = config['PROJECT_PATHS']
    project_path = project_paths.get(args.project_key)
    if project_path is None:
        print(f"Error: No project found for key '{args.project_key}'.")
        return

    if args.action == 'deploy':
        if args.branch_name is None:
            print("Error: Branch name is required for deployment.")
            return
        print(f"Deploying {args.branch_name} on {args.project_key}")
        deploy_project(project_path, args.branch_name, config['DEPLOYING_USER'])
    elif args.action == 'update-php':
        print(f"Updating PHP packages for {args.project_key}")
        update_php_packages(project_path, config['DOCKER_PHP_CONTAINER'], config['DEPLOYING_USER'])
    elif args.action == 'update-node':
        print(f"Updating Node packages for {args.project_key}")
        update_node_packages(project_path, config['DEPLOYING_USER'])
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

def deploy_project(project_path, branch_name, deploying_user):
    if not git_fetch_with_retry(project_path, deploying_user):
        return

    # Check for branch existence remotely
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

    print("Deployment successful.")

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
    parser.add_argument("project_key", help="Project key to identify the project path")
    parser.add_argument("action", choices=['deploy', 'update-php', 'update-node'], help="Action to perform")
    parser.add_argument("--branch_name", help="Branch name for deployment, required if action is 'deploy'")

    args = parser.parse_args()
    main(args, config)