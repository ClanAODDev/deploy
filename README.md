# AOD Project Manager

Handles in-situ deployment, package updates of PHP, Node.js projects, and restarting managed processes. 

### Setup

Example `config.json`:

```json
{
    "projects": {
        "tracker-dev": {
            "deploying_user": "username",
            "path": "/path/to/project1",
            "branch": "develop",
            "container": "php-fpm-container1",
            "supervisor_process": "supervisord-process-name",
            "block_npm_updates": true
        },
        "discord-bot-dev": {
            "deploying_user": "username",
            "path": "/path/to/project2",
            "branch": "develop",
            "systemd_service": "service-name"
        }
    }
}
```

| Project Key        | Value                                                                                                   |
|--------------------|---------------------------------------------------------------------------------------------------------|
| deploying_user     | User account configured to pull changes from GitHub, perform deployment tasks, etc                      |
| path               | Absolute path to the project                                                                            |
| branch             | Git branch to lock the project to. Deployments will only use this branch.                               |
| supervisor_process | If a supervisor process exists for the project, the process name (Depends on Docker)                    |
| container          | If the project runs inside a Docker container, the container name (PHP projects currently require this) |
| block_npm_updates  | Useful if the project has a `package.json` but shouldn't have a `node_modules` folder built             |
| systemd_service    | If the project runs in a systemd service, the service name to enable restarts                           |

### Usage

```
manage.py [-h] project_key {
    deploy,               # Pull the latest changes from the designated branch
    update-php,           # Run a `composer update --no-dev`
    update-node,          # Run a `npm update`
    restart-supervisor,   # Restart the designated supervisord process
    restart-service,      # Restart the designated systemd service
    revert-deployment,    # Reverts a deployment to the previous commit (defined in LAST_REVISION)
    toggle-maintenance    # Laravel-specific - toggles maintenance mode up or down
    tracker-sync          # Should only be run on the production Tracker project, syncs forum data with tracker data
}
```
