class Job:
    def prepare(self):
        return 1

    def run(self):
        return self.prepare()
