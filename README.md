# AOD Project Manager

Handles in-situ deployment and package updates of PHP, Node.js projects. 

### Setup

An example `config.ex.json` file is provided. Be sure to copy to a new `config.json`.

The following values are expected:

| Key                  | Value                                                         |
|----------------------|---------------------------------------------------------------|
| DEPLOYING_USER       | User configured to pull changes from GitHub                   |
| DOCKER_PHP_CONTAINER | Name of docker container responsible for serving PHP projects |
| PROJECT_PATHS        | JSON associative array of project keys and paths to recognize |

### Usage

```
manage.py [-h] [--branch_name BRANCH_NAME] [--process_name PROCESS_NAME] project_key {deploy,update-php,update-node,
restart-supervisor}
```

We currently assume PHP runs inside of a docker container, so that's a global variable hardcoded in the manage 
script. We also assume a specific deploying user for all operations, also a global variable.

There is a basic sanity check to ensure `--update-node` is used against a real NodeJS project, `--update-php` for PHP
projects, etc. based on the package file.

There is an action for restarting the supervisord process rather than baking it into the deploy action, since that 
doesn't necessarily need to happen every time code changes are made - just when code changes are made to things that 
actually get queued (like notifications).

### Things to improve/consider

The bot project builds itself on the server, but neither the tracker nor the site should ever have an `npm update` or
have a `node_modules` directory generated.

Right now it's possible to make this happen, and take up lots of space...
