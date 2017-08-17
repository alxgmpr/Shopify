from datetime import datetime


class Logger:
    def __init__(self, tid):
        self.format = '%H:%M:%S.%f'
        self.tid = tid

    def log(self, text):
        now = datetime.now().strftime(self.format)[:-4]
        print '[{}] :: [{}] :: {}'.format(self.tid, now, text)
