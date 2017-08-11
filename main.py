import os

from classes.shopify import Shopify
from classes.logger import Logger

log = Logger().log


def main():
    threads = []
    i = 0
    for config in os.listdir('configs'):
        if config != "config.example.json":
            log('MAIN', 'loading thread {} with config {}'.format(i, config))
            threads.append(Shopify('configs/' + config, i))
            threads[i].start()
            i += 1
        else:
            raise Exception('rename config.example.json')
if __name__ == '__main__':
    main()
