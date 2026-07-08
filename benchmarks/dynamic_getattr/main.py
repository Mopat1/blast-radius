class API:
    def ping(self):
        return "pong"


def call(api, name):
    return getattr(api, name)()
