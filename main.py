import os

from classes.shopify import Shopify
from classes.logger import Logger


def main():
    log = Logger('M').log
    threads = []
    i = 0
    files = os.listdir('configs')
    for config in files:
        if config in {'config.example.json',
                      'slack_config.json',
                      'slack_config.example.json'
                      }:
            pass
        else:
            log('loading thread {} with config {}'.format(i, config))
            threads.append(Shopify('configs/' + config, i))
            threads[i].start()
            i += 1

if __name__ == '__main__':
    main()
