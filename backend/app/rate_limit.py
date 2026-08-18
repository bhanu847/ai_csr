from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared across main.py (registers the exception handler) and any router
# that needs to decorate an endpoint — a separate module so neither side
# has to import the other.
limiter = Limiter(key_func=get_remote_address)
