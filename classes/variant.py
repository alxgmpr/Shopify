class Variant(object):
    def __init__(self, vid, size, stock=None):
        self.id = vid
        self.size = str(size)
        self.stock = stock
