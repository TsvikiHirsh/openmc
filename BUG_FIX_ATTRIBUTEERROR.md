# Bug Fix: AttributeError in _synchronize_materials_with_number

## Issue

When running the BOL k-eff fix with OpenMC, users encountered this error:

```python
File "/openmc_venv/lib/python3.11/site-packages/openmc/material.py", line 1498, in <listcomp>
    nuclides = [nuclide for nuclide in nuclides if nuclide.name not in nuclides_to_ignore]
                                                   ^^^^^^^^^^^^
AttributeError: 'tuple' object has no attribute 'name'
```

## Root Cause

The original implementation of `_synchronize_materials_with_number()` directly set the material's internal `_nuclides` attribute to a list of tuples:

```python
# WRONG - causes AttributeError
new_nuclides = []
for nuc in self.number.nuclides:
    # ... get density ...
    new_nuclides.append((nuc, atom_per_bcm, 'ao'))

mat._nuclides = new_nuclides  # Direct assignment of tuples
```

When OpenMC tried to export materials to XML, the `_get_nuclides_xml()` method expected nuclides to be objects with a `.name` attribute, not raw tuples. This caused the AttributeError.

## Fix

Use the Material API (`add_nuclide()`) instead of directly manipulating internal attributes:

```python
# CORRECT - uses Material API
mat._nuclides = []  # Clear existing

for nuc in self.number.nuclides:
    # ... get density ...
    mat.add_nuclide(nuc, atom_per_bcm, 'ao')  # Use API
```

The `Material.add_nuclide()` method properly handles the internal representation, ensuring compatibility with export methods.

## Changes Made

**File**: `openmc/deplete/coupled_operator.py`

**Lines Modified**: 413-429

**Before**:
```python
# Get all nuclides and their densities from self.number for this material
new_nuclides = []
for nuc in self.number.nuclides:
    if nuc not in self.nuclides_with_data:
        continue
    atom_per_cc = self.number.get_atom_density(mat_id, nuc)
    if atom_per_cc > 0.0:
        atom_per_bcm = atom_per_cc * 1.0e-24
        new_nuclides.append((nuc, atom_per_bcm, 'ao'))

# Replace material nuclides with the synchronized list
mat._nuclides = new_nuclides
```

**After**:
```python
# Clear existing nuclides from the material
mat._nuclides = []

# Re-add nuclides from self.number using the Material API
for nuc in self.number.nuclides:
    if nuc not in self.nuclides_with_data:
        continue
    atom_per_cc = self.number.get_atom_density(mat_id, nuc)
    if atom_per_cc > 0.0:
        atom_per_bcm = atom_per_cc * 1.0e-24
        # Use the Material API to add nuclides properly
        mat.add_nuclide(nuc, atom_per_bcm, 'ao')
```

## Testing

To verify the fix works:

```bash
# Run the pincell depletion example
cd /root/OpenMC/openmc/examples/9_11_25/
python run_depletion.py
```

Expected behavior:
- ✓ No AttributeError
- ✓ Materials export correctly to XML
- ✓ Depletion calculation runs successfully
- ✓ BOL k-eff matches standalone transport calculation

## Impact

This fix maintains the functionality of the BOL k-eff correction while ensuring proper compatibility with OpenMC's Material class API.

**No functional changes** - only fixes the runtime error. The synchronization logic remains the same.

## Commit

**Commit**: `90182c3`

**Message**: "Fix AttributeError in _synchronize_materials_with_number"

**Branch**: `claude/fix-openmc-depletion-integrate-011CUrTwmHSpHj6xkWH6idiZ`

## Status

✅ **FIXED** - Ready for testing

The code should now work correctly with OpenMC 0.13.0+ installations.
