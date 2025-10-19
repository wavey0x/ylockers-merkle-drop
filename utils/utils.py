import time
from functools import wraps

def func_timer(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        print(f'{f.__name__} took {end - start:.2f} seconds to execute')
        return result
    return wrapper
