import os

from classes.shopify import Shopify
from classes.logger import Logger


def main():
    log = Logger('M').log
    threads = []
    i = 0
    files = os.listdir('configs')
    with open('proxies.txt') as proxy_file:
        proxies = proxy_file.read().splitlines()
    for config in files:
        # list of config names that aren't threads
        if config in {'config.example.json',
                      'slack_config.json',
                      'slack_config.example.json'
                      }:
            pass
        else:
            log('loading thread {} with config {}'.format(i, config))
            try:
                proxy = proxies[i]
            except IndexError:
                proxy = None
            threads.append(Shopify('configs/' + config, i, proxy))
            threads[i].start()
            i += 1

if __name__ == '__main__':
    main()
