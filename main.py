from classes.shopify import Shopify


def main():
    s = Shopify('config.json', 1)
    s.start()

if __name__ == '__main__':
    main()
