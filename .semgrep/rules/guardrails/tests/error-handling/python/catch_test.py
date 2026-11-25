# ruleid: error-handling.bare-except-python
try:
    risky()
except:
    pass

# ruleid: error-handling.broad-exception-catch-python
try:
    risky()
except Exception:
    pass

# ok: error-handling.bare-except-python
try:
    risky()
except ValueError:
    handle()
