# Installing the BOL K-eff Fix

## Problem

After pulling the branch, `pip install .` may not update the installed package due to caching.

## Solution

### Option 1: Force Reinstall (Recommended for Testing)

```bash
cd /path/to/openmc
pip install --force-reinstall --no-deps .
```

The `--no-deps` flag prevents reinstalling dependencies, making it faster.

### Option 2: Editable Install (Recommended for Development)

```bash
cd /path/to/openmc
pip uninstall openmc  # Remove old installation
pip install -e .      # Install in editable mode
```

With editable mode (`-e`), changes to the code are immediately reflected without reinstalling.

## Verify Installation

### Check 1: Verify OpenMC location

```bash
python -c "import openmc; print(openmc.__file__)"
```

Should show your local directory, NOT something like `/usr/local/lib/python3.11/site-packages/openmc/__init__.py`

### Check 2: Verify the fix is present

```bash
python -c "
import inspect
import openmc.deplete
source = inspect.getsource(openmc.deplete.CoupledOperator)
has_fix = '_synchronize_materials_with_number' in source
print(f'Fix present: {has_fix}')
if not has_fix:
    print('ERROR: Fix not installed! Run pip install --force-reinstall --no-deps .')
"
```

### Check 3: Run verification test

```bash
cd /path/to/openmc
python verify_fix.py
```

This will:
1. Check if the fix is installed
2. Run a standalone kcode calculation
3. Run a depletion calculation
4. Compare the results

Expected output:
```
✓ Fix is installed correctly!
...
✓ SUCCESS: Difference is within 3σ - Fix is working!
```

## Common Issues

### Issue: "ModuleNotFoundError: No module named 'openmc'"

**Solution**: The virtual environment isn't activated, or OpenMC isn't installed.

```bash
# If using venv
source /openmc_venv/bin/activate

# Then install
pip install -e .
```

### Issue: Old version still being used

**Solution**: Clear Python cache and reinstall

```bash
# Remove cached bytecode
find . -type d -name __pycache__ -exec rm -rf {} +
find . -name "*.pyc" -delete

# Force reinstall
pip uninstall openmc
pip install --no-cache-dir -e .
```

### Issue: "Fix present: False" after installation

**Cause**: You're in a different directory or using a different Python environment

**Solution**:

1. Check you're in the right directory:
   ```bash
   pwd  # Should be /path/to/your/openmc
   git branch  # Should show the fix branch
   ```

2. Check you're using the right Python:
   ```bash
   which python
   which pip
   ```

3. Make sure you pulled the latest changes:
   ```bash
   git pull origin claude/fix-openmc-depletion-integrate-011CUrTwmHSpHj6xkWH6idiZ
   ```

4. Reinstall:
   ```bash
   pip install --force-reinstall --no-deps .
   ```

## Testing the Fix

### Quick Test

```bash
python verify_fix.py
```

### Full Test Suite

```bash
pytest tests/regression_tests/deplete_with_transport/test_bol_keff.py -v
pytest tests/regression_tests/deplete_with_transport/test_chain_sizes.py -v
```

## Expected Results

With the fix properly installed:
- BOL k-eff from depletion should match standalone kcode within 2-3σ
- No AttributeError should occur
- Works with all chain sizes (9 to 3820 nuclides)

## Still Having Issues?

1. Check commit hash:
   ```bash
   git log --oneline -3
   ```
   
   Should show:
   ```
   1c4499c Document AttributeError fix
   90182c3 Fix AttributeError in _synchronize_materials_with_number
   7bd877e Add detailed uncertainty analysis...
   ```

2. Make absolutely sure you're installing from the right directory:
   ```bash
   ls -la openmc/deplete/coupled_operator.py
   grep -n "_synchronize_materials_with_number" openmc/deplete/coupled_operator.py
   ```
   
   Should show the method exists around line 394.

3. If all else fails, try a clean reinstall:
   ```bash
   pip uninstall openmc
   cd /path/to/openmc
   git clean -fdx  # WARNING: Removes all untracked files!
   git pull
   pip install -e .
   ```
