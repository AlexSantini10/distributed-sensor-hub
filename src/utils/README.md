# Utilities

Shared support code used across the node runtime.

## Files

- `config.py`: loads and validates environment-backed node and sensor configuration.
- `logging.py`: configures bootstrap/runtime logging and structured demo events.
- `typing.py`: defines shared JSON aliases, protocols, and callback types.
- `__init__.py`: marks the utility package.

The package contains cross-cutting helpers only; domain behavior remains owned by the corresponding subsystem packages.
