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
            "supervisor_process": "supervisord-process-name"
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



### Usage

```
manage.py [-h] project_key {deploy,update-php,update-node,restart-supervisor,restart-service,revert-deployment}
```
