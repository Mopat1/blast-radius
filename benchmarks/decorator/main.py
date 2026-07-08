def log(fn):
    def wrapper():
        return fn()
    return wrapper


@log
def task():
    return 1


def run():
    return task()
