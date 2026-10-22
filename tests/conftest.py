import importlib.util

_HAAD = importlib.util.find_spec("haad") is not None

# tests that need optional dependencies: tests/haad needs haad (Python 3.14, run them in haad's environment, see
# tests/haad/README.md), tests/ad needs appdaemon
collect_ignore = [
    name for name, available in [("haad", _HAAD), ("ad", importlib.util.find_spec("appdaemon") is not None)] if not available
]

# haad's simulator fixture, for tests/haad
pytest_plugins = ["haad.testing.pytest_plugin"] if _HAAD else []
