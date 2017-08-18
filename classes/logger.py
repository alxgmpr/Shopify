from json import load
from datetime import datetime

import requests


class Logger:
    def __init__(self, tid):
        self.format = '%H:%M:%S.%f'
        self.tid = tid
        with open('configs/slack_config.json') as config:
            self.c = load(config)

    def log(self, text, slack=False):
        now = datetime.now().strftime(self.format)[:-4]
        print '[{}] :: [{}] :: {}'.format(self.tid, now, text)
        if slack and self.c['enable']:
            data = {
                'text': '*thread {}* - ```{}```\n'.format(self.tid, text)
            }
            r = requests.post(
                self.c['webhook_url'],
                json=data,
                headers={'Content-type': 'application/json'}
            )
            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                print r.text
                exit(-1)
