"""Test BOL k-eff consistency between standalone and depletion calculations.

This test verifies that the k-eff at Beginning Of Life (BOL) is consistent
between:
1. A standalone kcode calculation
2. The first step of a depletion calculation using the integrate method

This test was added to address an issue where depletion calculations with the
integrate method produced different BOL k-eff values compared to standalone
kcode calculations, especially when using long depletion chains.

The fix ensures that material compositions are synchronized between the initial
XML export and subsequent transport solves during depletion.
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
    n_rings = 1  # Smaller problem for faster testing
    n_wedges = 2
    return generate_problem(n_rings, n_wedges)


def test_bol_keff_consistency(run_in_tmpdir, problem):
    """Test that BOL k-eff matches between standalone and depletion runs.

    This test runs both a standalone kcode calculation and a depletion
    calculation, then compares the k-eff values. They should match within
    statistical uncertainty since they're using the same initial composition
    and same random seed.
    """
    geometry, lower_left, upper_right = problem

    # Settings for consistent comparison
    settings = openmc.Settings()
    settings.particles = 500
    settings.batches = 50
    settings.inactive = 10
    space = openmc.stats.Box(lower_left, upper_right)
    settings.source = openmc.IndependentSource(space=space)
    settings.seed = 42  # Fixed seed for reproducibility
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
    chain_file = Path(__file__).parents[2] / 'chain_simple.xml'
    op = openmc.deplete.CoupledOperator(model_depletion, chain_file)

    # Run very short depletion to get BOL k-eff
    dt = [0.1]  # 0.1 days - very short to minimize changes
    from openmc.data import JOULE_PER_EV
    power = 2.337e15 * JOULE_PER_EV * 1e6  # Similar to main test
    integrator = openmc.deplete.PredictorIntegrator(op, dt, power)
    integrator.integrate()

    # Get BOL k-eff from depletion results
    results = openmc.deplete.Results("depletion_results.h5")
    time, keff_depl = results.get_keff()
    keff_bol = keff_depl[0]  # First entry is BOL

    # Compare k-eff values
    keff_standalone_val = keff_standalone.nominal_value
    keff_standalone_std = keff_standalone.std_dev
    keff_bol_val = keff_bol[0]
    keff_bol_std = keff_bol[1]

    # The k-eff values should match within statistical uncertainty
    # We use 3-sigma criterion for the test
    diff = abs(keff_standalone_val - keff_bol_val)
    combined_std = np.sqrt(keff_standalone_std**2 + keff_bol_std**2)

    print(f"\nStandalone k-eff: {keff_standalone_val:.6f} +/- {keff_standalone_std:.6f}")
    print(f"Depletion BOL k-eff: {keff_bol_val:.6f} +/- {keff_bol_std:.6f}")
    print(f"Difference: {diff:.6e}")
    print(f"Combined std dev: {combined_std:.6e}")
    print(f"Difference in sigmas: {diff/combined_std:.2f}")

    # Assert that the difference is within 3 sigma
    assert diff < 3.0 * combined_std, \
        f"BOL k-eff discrepancy: standalone={keff_standalone_val:.6f}, " \
        f"depletion={keff_bol_val:.6f}, diff={diff:.6e} " \
        f"({diff/combined_std:.2f} sigma)"


def test_bol_keff_from_statepoint(run_in_tmpdir, problem):
    """Test that BOL k-eff in depletion results matches statepoint file.

    This verifies that the k-eff stored in depletion_results.h5 matches
    the k-eff in the corresponding statepoint file.
    """
    geometry, lower_left, upper_right = problem

    settings = openmc.Settings()
    settings.particles = 500
    settings.batches = 50
    settings.inactive = 10
    space = openmc.stats.Box(lower_left, upper_right)
    settings.source = openmc.IndependentSource(space=space)
    settings.seed = 42
    settings.verbosity = 1

    model = openmc.Model(geometry=geometry, settings=settings)
    chain_file = Path(__file__).parents[2] / 'chain_simple.xml'
    op = openmc.deplete.CoupledOperator(model, chain_file)

    # Run short depletion
    dt = [0.1]
    from openmc.data import JOULE_PER_EV
    power = 2.337e15 * JOULE_PER_EV * 1e6
    integrator = openmc.deplete.PredictorIntegrator(op, dt, power)
    integrator.integrate()

    # Get k-eff from depletion results
    results = openmc.deplete.Results("depletion_results.h5")
    time, keff_results = results.get_keff()
    keff_bol_results = keff_results[0]

    # Get k-eff from statepoint file
    sp = openmc.StatePoint("openmc_simulation_n0.h5")
    keff_bol_sp = sp.keff

    # They should match exactly (same source data)
    assert keff_bol_results[0] == keff_bol_sp.nominal_value
    assert keff_bol_results[1] == keff_bol_sp.std_dev
