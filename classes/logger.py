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
                "attachments": [
                    {
                        "fallback": "log report",
                        "color": "#36a64f",
                        "author_name": "Thread {}".format(self.tid),
                        "text": text
                    }
                ]
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

    def slack_product(self, product, variant_list):
        # TODO: make this not look like shit
        if not self.c['enable']:
            return
        vv = ''
        for v in variant_list:
            o = vv
            vv = '{} {} :: {}\n'.format(o, v.id, v.size)
        data = {
            "attachments": [
                {
                    "fallback": "product",
                    "color": "#36a64f",
                    "author_name": "Thread {}".format(self.tid),
                    "text": product.name
                },
                {
                    "fallback": "variants",
                    "color": "#36a64f",
                    "text": vv
                }
            ]
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
