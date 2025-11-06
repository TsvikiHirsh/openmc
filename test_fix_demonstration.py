"""Demonstration script showing BOL k-eff discrepancy before and after fix.

This script demonstrates the issue and the fix by:
1. Running with the synchronization disabled (simulating the bug)
2. Running with the synchronization enabled (showing the fix)
"""

import sys
from math import pi
from pathlib import Path
import shutil

# Check if numpy is available
try:
    import numpy as np
    import openmc
    import openmc.deplete
except ImportError as e:
    print(f"Error: Required module not available: {e}")
    print("This test requires OpenMC and its dependencies to be installed.")
    sys.exit(1)


def create_pincell_model():
    """Create a simple pincell model for testing."""

    # Define materials
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

    return openmc.Model(geometry=geometry, settings=settings)


def run_standalone_kcode():
    """Run standalone kcode calculation."""
    print("\n" + "="*80)
    print("STEP 1: Running standalone kcode calculation (REFERENCE)")
    print("="*80)

    model = create_pincell_model()
    sp_file = model.run()
    sp = openmc.StatePoint(sp_file)
    keff = sp.keff

    print(f"\nStandalone k-eff: {keff.nominal_value:.8f} +/- {keff.std_dev:.8f}")

    # Clean up
    for f in Path('.').glob('*.h5'):
        if 'depletion' not in f.name:
            f.unlink()
    for f in Path('.').glob('*.xml'):
        f.unlink()

    return keff.nominal_value, keff.std_dev


def run_depletion_with_sync(enable_sync=True):
    """Run depletion calculation with or without synchronization."""

    if enable_sync:
        print("\n" + "="*80)
        print("STEP 3: Running depletion WITH synchronization fix")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("STEP 2: Running depletion WITHOUT synchronization (BUG)")
        print("="*80)

    model = create_pincell_model()
    chain_file = 'tests/chain_simple.xml'

    op = openmc.deplete.CoupledOperator(model, chain_file)

    # Temporarily disable/enable synchronization for demonstration
    if not enable_sync:
        # Save the original method
        original_method = op._synchronize_materials_with_number
        # Replace with a no-op
        op._synchronize_materials_with_number = lambda: None
        print("(Synchronization disabled to demonstrate the bug)")
    else:
        print("(Synchronization enabled - this is the fix)")

    # Run very short depletion
    time_steps = [0.01]  # Very short to minimize changes
    power = 174  # W/cm
    integrator = openmc.deplete.PredictorIntegrator(op, time_steps, power, timestep_units='d')
    integrator.integrate()

    # Get BOL k-eff from depletion results
    results = openmc.deplete.Results("depletion_results.h5")
    time, keff = results.get_keff(time_units='d')
    keff_bol = keff[0]

    print(f"\nDepletion BOL k-eff: {keff_bol[0]:.8f} +/- {keff_bol[1]:.8f}")

    # Clean up
    for f in Path('.').glob('*.h5'):
        f.unlink()
    for f in Path('.').glob('*.xml'):
        f.unlink()

    return keff_bol[0], keff_bol[1]


def main():
    """Main demonstration function."""

    print("\n" + "="*80)
    print("DEMONSTRATION: BOL k-eff Discrepancy Fix")
    print("="*80)
    print("\nThis script demonstrates the BOL k-eff discrepancy issue and its fix.")
    print("It will run three calculations:")
    print("  1. Standalone kcode (reference)")
    print("  2. Depletion without synchronization (shows the bug)")
    print("  3. Depletion with synchronization (shows the fix)")

    try:
        # Run reference calculation
        keff_ref, std_ref = run_standalone_kcode()

        # Run without fix
        keff_no_sync, std_no_sync = run_depletion_with_sync(enable_sync=False)

        # Run with fix
        keff_with_sync, std_with_sync = run_depletion_with_sync(enable_sync=True)

        # Print comparison
        print("\n" + "="*80)
        print("RESULTS COMPARISON")
        print("="*80)

        print(f"\n1. Reference (standalone kcode):")
        print(f"   k-eff = {keff_ref:.8f} +/- {std_ref:.8f}")

        print(f"\n2. WITHOUT synchronization (bug):")
        print(f"   k-eff = {keff_no_sync:.8f} +/- {std_no_sync:.8f}")
        diff_no_sync = abs(keff_ref - keff_no_sync)
        sigma_no_sync = diff_no_sync / np.sqrt(std_ref**2 + std_no_sync**2)
        print(f"   Difference from reference: {diff_no_sync:.8f} ({sigma_no_sync:.2f} sigma)")
        if diff_no_sync > 3 * std_ref:
            print(f"   ⚠️  WARNING: Difference exceeds 3 sigma! This is the BUG.")

        print(f"\n3. WITH synchronization (fix):")
        print(f"   k-eff = {keff_with_sync:.8f} +/- {std_with_sync:.8f}")
        diff_with_sync = abs(keff_ref - keff_with_sync)
        sigma_with_sync = diff_with_sync / np.sqrt(std_ref**2 + std_with_sync**2)
        print(f"   Difference from reference: {diff_with_sync:.8f} ({sigma_with_sync:.2f} sigma)")
        if diff_with_sync <= 3 * std_ref:
            print(f"   ✓ GOOD: Difference is within 3 sigma. Fix works!")

        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"\nImprovement: The fix reduces the discrepancy by "
              f"{(diff_no_sync - diff_with_sync)/diff_no_sync*100:.1f}%")
        print(f"From {diff_no_sync:.8f} to {diff_with_sync:.8f}")

    except Exception as e:
        print(f"\nError during execution: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
