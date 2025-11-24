"""Simple test to verify BOL k-eff fix is working.

This script compares standalone kcode with depletion BOL k-eff.
"""

import sys
from math import pi
from pathlib import Path
import openmc
import openmc.deplete

# Check OpenMC installation
print("="*80)
print("Checking OpenMC Installation")
print("="*80)
print(f"OpenMC location: {openmc.__file__}")
print(f"OpenMC has CoupledOperator: {hasattr(openmc.deplete, 'CoupledOperator')}")

# Check if our fix is present
import inspect
source_file = inspect.getfile(openmc.deplete.CoupledOperator)
with open(source_file, 'r') as f:
    source_code = f.read()
    has_sync_method = '_synchronize_materials_with_number' in source_code
    print(f"Has _synchronize_materials_with_number method: {has_sync_method}")
    if not has_sync_method:
        print("\n" + "!"*80)
        print("ERROR: The fix is NOT installed!")
        print("Please run: pip install --force-reinstall --no-deps .")
        print("!"*80)
        sys.exit(1)

print("\n✓ Fix is installed correctly!\n")

# Define materials
uo2 = openmc.Material(name='UO2 fuel')
uo2.set_density('g/cm3', 10.29769)
uo2.add_element('U', 1., enrichment=2.4)
uo2.add_element('O', 2.)

helium = openmc.Material(name='Helium')
helium.set_density('g/cm3', 0.001598)
helium.add_element('He', 2.4044e-4)

zircaloy = openmc.Material(name='Zircaloy 4')
zircaloy.set_density('g/cm3', 6.55)
zircaloy.add_element('Sn', 0.014, 'wo')
zircaloy.add_element('Fe', 0.00165, 'wo')
zircaloy.add_element('Cr', 0.001, 'wo')
zircaloy.add_element('Zr', 0.98335, 'wo')

borated_water = openmc.Material(name='Borated water')
borated_water.set_density('g/cm3', 0.740582)
borated_water.add_element('B', 4.0e-5)
borated_water.add_element('H', 5.0e-2)
borated_water.add_element('O', 2.4e-2)
borated_water.add_s_alpha_beta('c_H_in_H2O')

# Create geometry
pitch = 1.25984
fuel_or = openmc.ZCylinder(r=0.39218)
clad_ir = openmc.ZCylinder(r=0.40005)
clad_or = openmc.ZCylinder(r=0.45720)
box = openmc.model.RectangularPrism(pitch, pitch, boundary_type='reflective')

fuel = openmc.Cell(fill=uo2, region=-fuel_or)
gap = openmc.Cell(fill=helium, region=+fuel_or & -clad_ir)
clad = openmc.Cell(fill=zircaloy, region=+clad_ir & -clad_or)
water = openmc.Cell(fill=borated_water, region=+clad_or & -box)

geometry = openmc.Geometry([fuel, gap, clad, water])
uo2.volume = pi * fuel_or.r**2

# Settings
settings = openmc.Settings()
settings.batches = 100
settings.inactive = 10
settings.particles = 1000
settings.seed = 1
bounds = [-0.62992, -0.62992, -1, 0.62992, 0.62992, 1]
settings.source = openmc.IndependentSource(
    space=openmc.stats.Box(bounds[:3], bounds[3:]),
    constraints={'fissionable': True})

print("="*80)
print("STEP 1: Standalone kcode calculation")
print("="*80)

model1 = openmc.Model(geometry=geometry, settings=settings)
sp_file = model1.run()
sp = openmc.StatePoint(sp_file)
keff_standalone = sp.keff

print(f"\nStandalone k-eff: {keff_standalone.nominal_value:.8f} +/- {keff_standalone.std_dev:.8f}")

# Clean up
for f in Path('.').glob('*.h5'):
    if 'depletion' not in f.name:
        f.unlink()
for f in Path('.').glob('*.xml'):
    f.unlink()

print("\n" + "="*80)
print("STEP 2: Depletion calculation (with fix)")
print("="*80)

model2 = openmc.Model(geometry=geometry, settings=settings)

# Use simple chain
chain_file = Path('tests/chain_simple.xml')
if not chain_file.exists():
    # Try alternate path
    chain_file = Path('../tests/chain_simple.xml')
if not chain_file.exists():
    print(f"ERROR: Cannot find chain file at {chain_file}")
    sys.exit(1)

op = openmc.deplete.CoupledOperator(model2, str(chain_file))

# Very short depletion
time_steps = [0.01]  # 0.01 days
power = 174  # W/cm
integrator = openmc.deplete.PredictorIntegrator(op, time_steps, power, timestep_units='d')
integrator.integrate()

# Get BOL k-eff
results = openmc.deplete.Results("depletion_results.h5")
time, keff = results.get_keff(time_units='d')
keff_bol = keff[0]

print(f"\nDepletion BOL k-eff: {keff_bol[0]:.8f} +/- {keff_bol[1]:.8f}")

# Compare
print("\n" + "="*80)
print("COMPARISON")
print("="*80)

diff = abs(keff_standalone.nominal_value - keff_bol[0])
combined_std = (keff_standalone.std_dev**2 + keff_bol[1]**2)**0.5
sigmas = diff / combined_std

print(f"Difference: {diff:.8f}")
print(f"Combined uncertainty: {combined_std:.8f}")
print(f"Difference in sigmas: {sigmas:.2f}σ")

if sigmas < 3.0:
    print("\n✓ SUCCESS: Difference is within 3σ - Fix is working!")
else:
    print(f"\n✗ FAILURE: Difference exceeds 3σ - Something is wrong!")

print(f"\nNote: With the fix, BOL k-eff should match standalone within ~2σ")
print(f"      Before the fix, there could be 4-5σ discrepancy with long chains")
