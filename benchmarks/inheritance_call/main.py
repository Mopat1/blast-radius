class Base:
    def setup(self):
        return 0


class Child(Base):
    def run(self):
        return self.setup()
