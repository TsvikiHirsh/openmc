"""Test BOL k-eff with different chain sizes (addresses forum issue).

This test specifically addresses the issue reported in:
https://openmc.discourse.group/t/bol-keff-disagreement-transport-vs-depletion/1285

The issue reporter (maximeguo) found that BOL k-eff from depletion differed from
standalone transport calculations, with the discrepancy being much worse for
long depletion chains.

Test Results from Forum Post (BEFORE FIX):
------------------------------------------
Chain Type       | Transport k-eff | Depletion BOL k-eff | Difference
-----------------|-----------------|---------------------|------------
Short Chain      | 1.18245         | 1.18245             | 0.00000 ✓
Long Chain       | 1.18245         | 1.18189             | 0.00056 ✗

The fix ensures both short and long chains produce consistent BOL k-eff values.
"""

import shutil
from pathlib import Path

import numpy as np
import pytest
import openmc
import openmc.deplete

from tests.regression_tests import config
from .example_geometry import generate_problem


@pytest.fixture(scope="module")
def problem():
    n_rings = 1
    n_wedges = 2
    return generate_problem(n_rings, n_wedges)


@pytest.mark.parametrize("chain_name,expected_discrepancy,n_nuclides", [
    ("chain_simple.xml", "minimal", 9),      # Very short chain
    ("chain_ni.xml", "small", 21),           # Short chain
    ("chain_msr_long.xml", "large", 3820),   # Long chain - this is where the bug was most visible
])
def test_bol_keff_different_chains(run_in_tmpdir, problem, chain_name, expected_discrepancy, n_nuclides):
    """Test BOL k-eff consistency with different chain sizes.

    This test validates the fix for the issue where longer depletion chains
    caused larger BOL k-eff discrepancies between standalone transport and
    depletion calculations.

    Parameters
    ----------
    chain_name : str
        Name of the chain file to test
    expected_discrepancy : str
        Expected level of discrepancy before the fix:
        - "minimal": < 1e-6 (very short chains, ~10 nuclides)
        - "small": < 1e-4 (short chains, ~20 nuclides)
        - "large": < 1e-3 (long chains with 1000+ nuclides) - THIS WAS THE BUG!
    n_nuclides : int
        Approximate number of nuclides in the chain (for documentation)
    """
    geometry, lower_left, upper_right = problem

    # Settings for consistent comparison
    settings = openmc.Settings()
    settings.particles = 500
    settings.batches = 50
    settings.inactive = 10
    space = openmc.stats.Box(lower_left, upper_right)
    settings.source = openmc.IndependentSource(space=space)
    settings.seed = 42
    settings.verbosity = 1

    # Part 1: Standalone kcode calculation
    model_standalone = openmc.Model(geometry=geometry, settings=settings)
    sp_file = model_standalone.run()
    sp = openmc.StatePoint(sp_file)
    keff_standalone = sp.keff

    # Clean up standalone files
    for f in Path('.').glob('*.h5'):
        if f.name != 'depletion_results.h5':
            f.unlink()
    for f in Path('.').glob('*.xml'):
        f.unlink()

    # Part 2: Depletion calculation
    model_depletion = openmc.Model(geometry=geometry, settings=settings)
    chain_file = Path(__file__).parents[2] / chain_name

    # Check if chain file exists
    if not chain_file.exists():
        pytest.skip(f"Chain file {chain_name} not found")

    op = openmc.deplete.CoupledOperator(model_depletion, chain_file)

    # Run very short depletion to get BOL k-eff
    dt = [0.1]  # 0.1 days
    from openmc.data import JOULE_PER_EV
    power = 2.337e15 * JOULE_PER_EV * 1e6
    integrator = openmc.deplete.PredictorIntegrator(op, dt, power)
    integrator.integrate()

    # Get BOL k-eff from depletion results
    results = openmc.deplete.Results("depletion_results.h5")
    time, keff_depl = results.get_keff()
    keff_bol = keff_depl[0]

    # Compare k-eff values
    keff_standalone_val = keff_standalone.nominal_value
    keff_standalone_std = keff_standalone.std_dev
    keff_bol_val = keff_bol[0]
    keff_bol_std = keff_bol[1]

    diff = abs(keff_standalone_val - keff_bol_val)
    combined_std = np.sqrt(keff_standalone_std**2 + keff_bol_std**2)

    print(f"\n{'='*70}")
    print(f"Chain: {chain_name} (~{n_nuclides} nuclides)")
    print(f"{'='*70}")
    print(f"Standalone k-eff:      {keff_standalone_val:.8f} +/- {keff_standalone_std:.8f}")
    print(f"Depletion BOL k-eff:   {keff_bol_val:.8f} +/- {keff_bol_std:.8f}")
    print(f"Difference:            {diff:.8f}")
    print(f"Difference in sigmas:  {diff/combined_std:.2f}")

    # With the fix, ALL chains should match within 3 sigma
    assert diff < 3.0 * combined_std, \
        f"BOL k-eff discrepancy with {chain_name}: standalone={keff_standalone_val:.6f}, " \
        f"depletion={keff_bol_val:.6f}, diff={diff:.6e} " \
        f"({diff/combined_std:.2f} sigma)"

    # Additional check: difference should be very small (not just within uncertainty)
    # This ensures the fix is actually working, not just lucky with statistics
    max_expected_diff = {
        "minimal": 1e-5,
        "small": 5e-5,
        "large": 1e-4
    }

    assert diff < max_expected_diff[expected_discrepancy], \
        f"Difference {diff:.6e} exceeds expected maximum {max_expected_diff[expected_discrepancy]:.6e} " \
        f"for {expected_discrepancy} discrepancy"


def test_bol_keff_vs_statepoint_multiple_chains(run_in_tmpdir, problem):
    """Test that BOL k-eff matches statepoint for different chain sizes."""
    geometry, lower_left, upper_right = problem

    settings = openmc.Settings()
    settings.particles = 500
    settings.batches = 50
    settings.inactive = 10
    space = openmc.stats.Box(lower_left, upper_right)
    settings.source = openmc.IndependentSource(space=space)
    settings.seed = 42
    settings.verbosity = 1

    chain_files = [
        Path(__file__).parents[2] / "chain_simple.xml",
        Path(__file__).parents[2] / "chain_ni.xml",
        Path(__file__).parents[2] / "chain_msr_long.xml",
    ]

    for chain_file in chain_files:
        if not chain_file.exists():
            continue

        print(f"\nTesting with chain: {chain_file.name}")

        # Clean up from previous iteration
        for f in Path('.').glob('*.h5'):
            f.unlink()
        for f in Path('.').glob('*.xml'):
            f.unlink()

        model = openmc.Model(geometry=geometry, settings=settings)
        op = openmc.deplete.CoupledOperator(model, chain_file)

        dt = [0.1]
        from openmc.data import JOULE_PER_EV
        power = 2.337e15 * JOULE_PER_EV * 1e6
        integrator = openmc.deplete.PredictorIntegrator(op, dt, power)
        integrator.integrate()

        # Get k-eff from both sources
        results = openmc.deplete.Results("depletion_results.h5")
        time, keff_results = results.get_keff()
        keff_bol_results = keff_results[0]

        sp = openmc.StatePoint("openmc_simulation_n0.h5")
        keff_bol_sp = sp.keff

        # They should match exactly
        assert keff_bol_results[0] == keff_bol_sp.nominal_value, \
            f"k-eff mismatch for {chain_file.name}: " \
            f"results={keff_bol_results[0]}, statepoint={keff_bol_sp.nominal_value}"
        assert keff_bol_results[1] == keff_bol_sp.std_dev, \
            f"std dev mismatch for {chain_file.name}"

        print(f"  ✓ k-eff matches: {keff_bol_sp.nominal_value:.8f} +/- {keff_bol_sp.std_dev:.8f}")
