from variant import Variant


class Product(object):
    def __init__(self, name, url):
        self.name = name
        self.url = url
        self.variants = []

    def add_var_by_parts(self, vid, size):
        self.variants.append(Variant(vid, size))

    def add_var(self, var):
        self.variants.append(var)
