# How to test

To run the tests for the distributed sensor hub project, follow these steps:

1. Ensure you have `pytest` installed. If not, install it using:
   ```
   pip install pytest
   ```

2. Navigate to the root directory of the project

3. Run the tests using:
   ```
   pytest --maxfail=1
   ```

   verbose:
   ```
   pytest -v --maxfail=1
   ```

   to test a single module:
   ```
   pytest -m [module_name]
   ```

   Windows PowerShell:
   ```
   python -m pytest --maxfail=1
   ```