class Product(object):
    def __init__(self, name, url, price='0.00', variants=None):
        self.name = name
        self.url = url
        self.variants = variants
        self.price = price
