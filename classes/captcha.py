class Captcha:
    def __init__(self, sitekey, url, solution=None):
        self.sitekey = sitekey
        self.solution = solution
        self.url = url

    # TODO: move the solving methods into this class
    # def get_sol_2cap(self)
