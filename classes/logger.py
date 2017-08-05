from datetime import datetime


class Logger:
    def __init__(self):
        self.format = '%H:%M:%S.%f'

    def log(self, tid, text):
        now = datetime.now().strftime(self.format)[:-4]
        print '[t-{}] :: [{}] :: {}'.format(tid, now, text)
