"""Test BOL k-eff discrepancy between kcode and depletion with integrate method."""

from math import pi
import openmc
import openmc.deplete
import numpy as np

# Define materials (from pincell example)
uo2 = openmc.Material(name='UO2 fuel at 2.4% wt enrichment')
uo2.set_density('g/cm3', 10.29769)
uo2.add_element('U', 1., enrichment=2.4)
uo2.add_element('O', 2.)

helium = openmc.Material(name='Helium for gap')
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
fuel_or = openmc.ZCylinder(r=0.39218, name='Fuel OR')
clad_ir = openmc.ZCylinder(r=0.40005, name='Clad IR')
clad_or = openmc.ZCylinder(r=0.45720, name='Clad OR')
box = openmc.model.RectangularPrism(pitch, pitch, boundary_type='reflective')

fuel = openmc.Cell(fill=uo2, region=-fuel_or)
gap = openmc.Cell(fill=helium, region=+fuel_or & -clad_ir)
clad = openmc.Cell(fill=zircaloy, region=+clad_ir & -clad_or)
water = openmc.Cell(fill=borated_water, region=+clad_or & -box)

geometry = openmc.Geometry([fuel, gap, clad, water])

# Set material volume for depletion
uo2.volume = pi * fuel_or.r**2

# Settings
settings = openmc.Settings()
settings.batches = 100
settings.inactive = 10
settings.particles = 1000
bounds = [-0.62992, -0.62992, -1, 0.62992, 0.62992, 1]
uniform_dist = openmc.stats.Box(bounds[:3], bounds[3:])
settings.source = openmc.IndependentSource(
    space=uniform_dist, constraints={'fissionable': True})
settings.seed = 1

print("="*80)
print("PART 1: Running standalone kcode calculation")
print("="*80)

model = openmc.Model(geometry=geometry, settings=settings)
sp_file = model.run()
sp = openmc.StatePoint(sp_file)
keff_kcode = sp.keff
print(f"K-eff from standalone kcode: {keff_kcode.nominal_value:.6f} +/- {keff_kcode.std_dev:.6f}")

print("\n" + "="*80)
print("PART 2: Running depletion with integrate method (short chain)")
print("="*80)

# Recreate model for depletion
model2 = openmc.Model(geometry=geometry, settings=settings)
chain_file = 'tests/chain_simple.xml'
op = openmc.deplete.CoupledOperator(model2, chain_file)

# Run very short depletion (just to get BOL k-eff)
time_steps = [0.1]  # Very short time step in days
power = 174  # W/cm
integrator = openmc.deplete.PredictorIntegrator(op, time_steps, power, timestep_units='d')
integrator.integrate()

# Get BOL k-eff from depletion results
results = openmc.deplete.Results("depletion_results.h5")
time, keff = results.get_keff(time_units='d')
keff_bol = keff[0]  # First entry is BOL
print(f"K-eff from depletion (BOL, short chain): {keff_bol[0]:.6f} +/- {keff_bol[1]:.6f}")

print("\n" + "="*80)
print("COMPARISON")
print("="*80)
print(f"K-eff difference: {abs(keff_kcode.nominal_value - keff_bol[0]):.6e}")
print(f"Difference in standard deviations: {abs(keff_kcode.nominal_value - keff_bol[0]) / keff_kcode.std_dev:.2f} sigma")

if abs(keff_kcode.nominal_value - keff_bol[0]) > 3 * keff_kcode.std_dev:
    print("WARNING: Difference is more than 3 sigma!")
else:
    print("OK: Difference is within 3 sigma")
