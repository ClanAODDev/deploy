import subprocess
import sys
import os
import json

DEPLOYING_USER = "dcdeaton"
DOCKER_PHP_CONTAINER = "clanaod-php-fpm-8-2"

def load_project_paths():

    try:
        with open('projects.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print("Error: Configuration file 'projects.json' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Configuration file 'projects.json' is not a valid JSON.")
        sys.exit(1)

def deploy_project(project_path, branch_name):
    
    commands = [
        f"cd {project_path}",
        f"sudo -u {DEPLOYING_USER} git fetch --all > /dev/null",
        f"sudo -u {DEPLOYING_USER} git reset --hard origin/{branch_name} > /dev/null",
        f"sudo -u {DEPLOYING_USER} git pull origin {branch_name} > /dev/null"
    ]

    try:
        
        process = subprocess.Popen(
            " && ".join(commands),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        stdout, stderr = process.communicate()

        
        if process.returncode != 0:
            raise Exception(f"Git operation failed: {stderr.decode().strip()}")

        print("Deployment successful.")
    except Exception as e:
        print(f"An error occurred during deployment: {e}")

def update_php_packages(project_path, container_name):
    if not os.path.exists(os.path.join(project_path, "composer.json")):
        print(f"Error: No 'composer.json' found in the project directory. This is not a PHP project.")
        return

    docker_command = f"docker exec {container_name} /bin/bash -c 'cd {project_path} && composer update --no-interaction --no-dev'"

    command = f"sudo -u {DEPLOYING_USER} {docker_command} > /dev/null"

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

def update_node_packages(project_path):
    if not os.path.exists(os.path.join(project_path, "package.json")):
        print(f"Error: No 'package.json' found in the project directory. Not a Node.js project.")
        return

    command = f"cd {project_path} && sudo -u {DEPLOYING_USER} npm update > /dev/null"

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
    if len(sys.argv) < 3:
        print("Usage: python manage.py <project_key> --deploy <branch_name> | --update-php | --update-node")
        sys.exit(1)
    
    project_key = sys.argv[1]
    action = sys.argv[2]

    project_paths = load_project_paths()
    project_path = project_paths.get(project_key)

    if project_path is None:
        print(f"Error: No project found for key '{project_key}'.")
        sys.exit(1)

    if action == "--deploy":
        if len(sys.argv) != 4:
            print("Error: Branch name is required for deployment.")
            sys.exit(1)
        branch_name = sys.argv[3]
        deploy_project(project_path, branch_name)
    elif action == "--update-php":
        update_php_packages(project_path, DOCKER_PHP_CONTAINER)
    elif action == "--update-node":
        update_node_packages(project_path)
    else:
        print("Error: Invalid action. Use --deploy <branch_name>, --update-php, or --update-node.")
        sys.exit(1)
