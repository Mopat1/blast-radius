def target():
    return 1


def apply(fn):
    return fn()


def run():
    return apply(target)
