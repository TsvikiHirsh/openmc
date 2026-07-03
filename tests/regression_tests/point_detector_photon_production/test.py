import openmc

from tests.testing_harness import PyAPITestHarness


class PointDetectorPhotonProductionTestHarness(PyAPITestHarness):
    """Coupled neutron-photon problem with point detectors scoring the flux
    of both particle types, including photons born in neutron reactions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        water = openmc.Material()
        water.set_density('g/cm3', 1.0)
        water.add_nuclide('H1', 2.0)
        water.add_nuclide('O16', 1.0)
        self._model.materials = openmc.Materials([water])

        sphere = openmc.Sphere(r=12.0)
        outer = openmc.Sphere(r=30.0, boundary_type='vacuum')
        inside = openmc.Cell(region=-sphere, fill=water)
        outside = openmc.Cell(region=+sphere & -outer)
        self._model.geometry = openmc.Geometry([inside, outside])

        source = openmc.IndependentSource()
        source.space = openmc.stats.Point((0., 0., 0.))
        source.angle = openmc.stats.Isotropic()
        source.energy = openmc.stats.Discrete([2.0e6], [1.0])
        source.particle = 'neutron'

        settings = openmc.Settings()
        settings.particles = 2000
        settings.batches = 5
        settings.photon_transport = True
        settings.run_mode = 'fixed source'
        settings.source = source
        self._model.settings = settings

        point_filter = openmc.PointFilter([((0., 20., 0.), 1.0)])
        particle_filter = openmc.ParticleFilter(['neutron', 'photon'])
        tally = openmc.Tally()
        tally.filters = [point_filter, particle_filter]
        tally.scores = ['flux']
        self._model.tallies = openmc.Tallies([tally])


def test_point_detector_photon_production():
    harness = PointDetectorPhotonProductionTestHarness(
        'statepoint.5.h5', model=openmc.Model())
    harness.main()
