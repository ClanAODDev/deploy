# AOD Project Manager

Handles deployment and package updates of PHP, NodeJS projects. 


### Usage
First, ensure the `projects.json` file contains the correct absolute path to the project. The project key will be used as an argument.

```
python manage.py <project_key> --deploy <branch_name> | --update-php | --update-node
```

We currently assume PHP runs inside of a docker container, so that's a global variable hardcoded in the manage script. We also assume a specific deploying user for all operations, also a global variable.

There is a basic sanity check to ensure `--update-node` is used against a real NodeJS project, `--update-php` for PHP projects, etc based on the package file.

### Things to improve/consider
The bot project builds itself on the server, but neither the tracker nor the site should ever have an `npm update` or have a `node_modules` directory generated.

Right now it's possible to make this happen, and take up lots of space...