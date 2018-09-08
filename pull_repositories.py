#!/usr/bin/env python
"""Keep all your local copies of github repositories up-to-date

Only prints output on errors and --dry-run, which makes this
suitable for cron jobs.

Version 0.1
2018-07-26
"""
import argparse
import os
import json
import sys
import re
import csv
import subprocess
from time import sleep

import requests

# add config file to sys path
this_dir = os.path.dirname(os.path.abspath(__file__))
if this_dir not in sys.path:
    sys.path.insert(0, this_dir)

from config import (
    pull_my_repos, github_api_token,
    default_destination, my_github_username
)

def get_my_gh_repos():
    # thanks postman
    url = "https://api.github.com/graphql"
    payload = """{
        \"query\": \"query {
            viewer {
                repositories(first:100) {
                    edges {
                        node {
                            sshUrl
                            name
                        }
                    }
                }
            }
        }
        \"}"""
    payload = re.sub('\s+', ' ', payload)
    headers = {
        'Authorization': "bearer  " + github_api_token,
        'Cache-Control': "no-cache",
    }

    response = requests.request(
        "POST",
        url,
        data=payload,
        headers=headers,
    )

    viewer = json.loads(response.text)['data']['viewer']

    gh_repos = viewer['repositories']['edges']
    gh_repos = [r['node'] for r in gh_repos]

    gh_repos = {
        '{}/{}'.format(my_github_username, r['name']): r
        for r in gh_repos
    }
    return gh_repos

def read_repo_csv():
    config_csv = os.path.join(this_dir, 'config.csv')
    repo_list = list()
    with open(config_csv, 'r') as fr:
        csvr = csv.reader(fr)
        headers = next(csvr)
        # skip the documentation line
        next(csvr)
        for line in csvr:
            repo_list.append(dict(zip(headers, line)))

    repos = {
        '{}/{}'.format(r['user'], r['name']): r
        for r in repo_list
    }
    for repo in repos.values():
        # get rid of empty values
        for k in list(repo.keys()):
            if not repo[k]:
                del repo[k]

        do_pull = repo.get('do_pull', 'true').lower()
        do_pull = False if do_pull == 'false' else True
        repo['do_pull'] = do_pull

    return repos

def run_main():
    args = parse_cl_args()

    verbose = args.verbose
    dry_run = args.dry_run
    redirect_stdout = '1>/dev/null'
    if dry_run:
        redirect_stdout = "'{}'".format(redirect_stdout)

    gh_repos = get_my_gh_repos() if pull_my_repos else list()
    repos = read_repo_csv()

    # merge gh_repos into repos
    for key, gh_repo in gh_repos.items():
        # if it doesn't exist, just add it
        if key not in repos:
            repos[key] = gh_repo
        # if it exists, then merge the two dictionaries
        else:
            repo = repos[key]
            repo.update(gh_repo)


    for key in repos:
        repo = repos[key]
        do_pull = repo.get('do_pull', True)
        if not do_pull:
            if dry_run or verbose:
                print('skipping {}\n'.format(key))
            continue

        if verbose:
            print('processing', key)
        sshUrl = repo['sshUrl']
        local_destination = os.path.expanduser(repo.get('local_destination', default_destination))
        local_repo_dir_name = repo.get('local_repo_dir_name', repo['name'])
        echo = 'echo' if dry_run else ''
        command = """
        cd "{local_destination}"
        if [ "{echo}" = "echo" ] ; then
            echo cd "{local_destination}"
        fi
        if [ ! -e "{local_repo_dir_name}" ] ; then
            # couldn't find the repo!
            if {clone} ; then
                {echo} git clone "{sshUrl}" {redirect_stdout}
            else
                echo "couldn't find repository {local_destination}/{local_repo_dir_name}! did you mean to {__file__} --clone?"
            fi
        else
            {echo} cd "{local_repo_dir_name}"
            {echo} git pull {redirect_stdout}
            if [ "$?" -ne 0 ] ; then
                echo "failure occurred on {local_destination}/{local_repo_dir_name}"
            fi
        fi
        # don't stop the python script if a pull or other command fails
        exit 0
        """.format(
            local_destination=local_destination,
            local_repo_dir_name=local_repo_dir_name,
            sshUrl=sshUrl,
            echo=echo,
            redirect_stdout=redirect_stdout,
            clone=str(args.clone).lower(),
            __file__=__file__,
        )
        exit_code = subprocess.call(command, shell=True)
        if not dry_run:
            sleep(args.seconds_between_pulls)

        # add some spacing so it's easier to read
        if dry_run:
            print()

    success = True
    return success

def parse_cl_args():
    argParser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    argParser.add_argument('--dry-run', default=False, action='store_true')
    argParser.add_argument('--verbose', default=False, action='store_true')
    argParser.add_argument(
        '--seconds-between-pulls', default=0, type=int,
        help='number of seconds to wait between each pull, default %(default)s',
    )
    argParser.add_argument(
        '--clone', default=False, action='store_true',
        help="by default, print an error message if a repository can't be found.\n"
             "if --clone is specified, then clone it instead."
    )

    args = argParser.parse_args()
    return args

if __name__ == '__main__':
    success = run_main()
    exit_code = 0 if success else 1
    exit(exit_code)
