# AOD Project Manager

Handles in-situ deployment, package updates of PHP, Node.js projects, and restarting managed processes. 

### Setup

Example `config.json`:

```json
{
    "deploying_user": "deployer",
    "projects": {
        "tracker-dev": {
            "path": "/path/to/project1",
            "branch": "develop",
            "container": "php-fpm-container1"
        },
        "discord-bot-dev": {
            "path": "/path/to/project2",
            "branch": "develop"
        }
    }
}
```



### Usage

```
manage.py [-h] project_key {deploy,update-php,update-node,restart-supervisor} [--process_name PROCESS_NAME] 
```

We currently assume PHP runs inside of a docker container, so we include the container name as part of the project. We 
also assume a specific deploying user for all operations.

There is a basic sanity check to ensure `--update-node` is used against a real NodeJS project, `--update-php` for PHP
projects, etc. based on the package file.

There is an action for restarting the supervisord process rather than baking it into the deploy action, since that 
doesn't necessarily need to happen every time code changes are made - just when code changes are made to things that 
actually get queued (like notifications).

### Things to improve/consider

The bot project builds itself on the server, but neither the tracker nor the site should ever have an `npm update` or
have a `node_modules` directory generated.

Right now it's possible to make this happen, and take up lots of space...
