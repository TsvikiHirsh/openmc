#ifndef OPENMC_TALLIES_NEXT_EVENT_SCORING_H
#define OPENMC_TALLIES_NEXT_EVENT_SCORING_H

#include "openmc/nuclide.h"
#include "openmc/particle.h"
#include "openmc/random_lcg.h"
#include "openmc/ray.h"
#include "openmc/tallies/filter.h"
#include "openmc/tallies/tally.h"
#include "openmc/tallies/tally_scoring.h"
#include "openmc/thermal.h"

namespace openmc {

void score_point_tally_elastic(
  Particle& p, int i_nuclide, const Reaction& rx, int i_product, Direction v_t);

void score_point_tally_inelastic(
  Particle& p, int i_nuclide, const Reaction& rx, int i_product, double yield);

void score_point_tally_fission(
  Particle& p, int i_nuclide, const Reaction& rx, int i_product);

void score_point_tally_sab(Particle& p, int i_nuclide, const ThermalData& sab,
  const NuclideMicroXS& micro);

void score_point_tally_source(SourceSite& site, int source_index);

//! Score photon point tallies for coherent (Rayleigh) scattering
void score_point_tally_coherent(Particle& p, int i_element);

//! Score photon point tallies for incoherent (Compton) scattering
void score_point_tally_incoherent(Particle& p, int i_element);

//! Score photon point tallies for isotropically emitted photons
//! (fluorescence from atomic relaxation, positron annihilation)
//
//! \param[in] p Particle at the emission site (its weight and position are
//!   used; the emitted particle is always a photon)
//! \param[in] E Energy of the emitted photon(s)
//! \param[in] multiplicity Number of photons emitted isotropically
void score_point_tally_isotropic_photon(
  Particle& p, double E, double multiplicity);

//! Score photon point tallies for photons produced by neutron reactions
void score_point_tally_photon_production(
  Particle& p, int i_nuclide, const Reaction& rx, int i_product, double wgt);

template<typename PDF>
void score_point_tally_impl(
  const Position r, const ParticleType type, const double time, PDF pdffunc)
{
  for (auto& det : model::active_point_detectors) {
    auto u = (det - r);
    double total_distance = u.norm();
    u /= total_distance;
    double E;
    double pdf = pdffunc(u, E);
    if (pdf == 0.0)
      continue;
    auto p = ParticleRay(r, u, type, time, E);
    p.Ray::trace(total_distance);
    double distance = p.traversal_distance();
    // Use a small tolerance to avoid dropping rays that reached the detector
    // but accumulated floating-point roundoff along the way
    if (distance < total_distance - TINY_BIT)
      continue;
    double mfp = p.traversal_mfp();
    double attenuation = std::exp(-mfp);

    // Save the attenuation for point filter handling
    p.wgt_last() = p.wgt();
    p.wgt() *= attenuation;

    double flux = p.wgt_last() * pdf;
    score_tracklength_tally_general(p, flux, model::active_point_tallies);
  }
}

} // namespace openmc

#endif // OPENMC_TALLIES_NEXT_EVENT_SCORING_H
