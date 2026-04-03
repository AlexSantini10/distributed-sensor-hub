"""Configure test import paths for the repository.

Responsibilities:
    - Insert the repository root into ``sys.path`` for direct test imports.
    - Keep test execution independent of editable-package installation.
"""

import os
import sys


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
