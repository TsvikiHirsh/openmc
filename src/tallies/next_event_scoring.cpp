#include "openmc/tallies/next_event_scoring.h"

#include <algorithm> // for clamp

#include "openmc/photon.h"
#include "openmc/search.h"
#include "openmc/secondary_uncorrelated.h"
#include "openmc/settings.h"
#include "openmc/source.h"

namespace openmc {

// Classical electron radius squared in barns, r_e = alpha*hbar*c/(m_e*c^2).
// PLANCK_C is h*c in eV-Angstrom and 1 Angstrom^2 = 1e8 barns.
constexpr double R_ELECTRON_SQ =
  PLANCK_C / (2.0 * PI) / (FINE_STRUCTURE * MASS_ELECTRON_EV) * PLANCK_C /
  (2.0 * PI) / (FINE_STRUCTURE * MASS_ELECTRON_EV) * 1.0e8;

void score_point_tally_elastic(
  Particle& p, int i_nuclide, const Reaction& rx, int i_product, Direction v_t)
{

  const auto& nuc {data::nuclides[i_nuclide]};
  double awr = nuc->awr_;

  // Neutron velocity in LAB
  Direction v_n = std::sqrt(p.E()) * p.u();
  auto u_n = v_n / v_n.norm();

  // Velocity of center-of-mass
  Direction v_cm = (v_n + awr * v_t) / (awr + 1.0);
  auto u_cm = v_cm / v_cm.norm();

  double E_in = p.E();
  double E_com = v_cm.dot(v_cm);
  double E_out = (v_n - v_cm).dot(v_n - v_cm);

  auto& d = rx.products_[i_product].distribution_[0];
  auto d_ = dynamic_cast<UncorrelatedAngleEnergy*>(d.get());

  auto pdf = [&](Direction u, double& E) {
    double mu = u.dot(u_cm);
    double mu_l = u.dot(u_n);
    E = E_out;
    double jac =
      get_jac_and_transform_impl(E_com, mu, E, p.current_seed(), awr);
    double mu_cm =
      1.0 + mu_l * std::sqrt(E_in * E) / E_out - (E_in + E) / (2.0 * E_out);
    mu_cm = std::clamp(mu_cm, -1.0, 1.0);
    if (!d_->angle().empty()) {
      return jac * d_->angle().evaluate(p.E(), mu_cm) / (2.0 * PI);
    } else {
      return jac * 0.5 / (2.0 * PI);
    }
  };
  score_point_tally_impl(p.r(), p.type(), p.time(), pdf);
}

void score_point_tally_inelastic(
  Particle& p, int i_nuclide, const Reaction& rx, int i_product, double yield)
{
  const auto& nuc {data::nuclides[i_nuclide]};
  double awr = nuc->awr_;
  auto u_n = p.u();
  auto E_n = p.E();
  auto is_com = rx.scatter_in_cm_;

  auto pdf = [&](Direction u, double& E) {
    double mu = u.dot(u_n);
    return rx.products_[i_product].sample_energy_and_pdf(
             E_n, mu, E, p.current_seed(), is_com, awr) /
           (2.0 * PI) * yield;
  };
  score_point_tally_impl(p.r(), p.type(), p.time(), pdf);
}

void score_point_tally_fission(
  Particle& p, int i_nuclide, const Reaction& rx, int i_product)
{
  const auto& nuc {data::nuclides[i_nuclide]};
  double awr = nuc->awr_;
  auto u_n = p.u();
  auto E_n = p.E();
  auto is_com = rx.scatter_in_cm_;

  auto pdf = [&](Direction u, double& E) {
    double mu = u.dot(u_n);
    return rx.products_[i_product].sample_energy_and_pdf(
             E_n, mu, E, p.current_seed(), is_com, awr) /
           (2.0 * PI);
  };
  score_point_tally_impl(p.r(), p.type(), p.time(), pdf);
}

void score_point_tally_sab(Particle& p, int i_nuclide, const ThermalData& sab,
  const NuclideMicroXS& micro)
{
  const auto& nuc {data::nuclides[i_nuclide]};
  double awr = nuc->awr_;
  auto u_n = p.u();
  auto E_n = p.E();
  auto pdf = [&](Direction u, double& E) {
    double mu = u.dot(u_n);
    return sab.sample_energy_and_pdf(
             micro, E_n, mu, E, p.current_seed(), false, awr) /
           (2.0 * PI);
  };
  score_point_tally_impl(p.r(), p.type(), p.time(), pdf);
}

void score_point_tally_coherent(Particle& p, int i_element)
{
  const auto& elm {*data::elements[i_element]};
  const auto& micro {p.photon_xs(i_element)};

  double alpha = p.E() / MASS_ELECTRON_EV;
  double x2_max = std::pow(MASS_ELECTRON_EV / PLANCK_C * alpha, 2);
  auto u_n = p.u();
  double wgt = p.wgt();

  auto pdf = [&](Direction u, double& E) {
    double mu = u.dot(u_n);
    E = p.E();

    // The angular distribution of coherent scattering is given by the Thomson
    // cross section weighted by the square of the form factor F(x^2, Z). Only
    // the integral of F^2/Z^2 over x^2 is stored (see
    // PhotonReaction.to_hdf5), so differentiate the tabulated integral to
    // recover F^2 on the sampled segment, consistent with how
    // PhotonInteraction::rayleigh_scatter samples x^2.
    double x2 = x2_max * 0.5 * (1.0 - mu);
    const auto& x {elm.coherent_int_form_factor_.x()};
    const auto& y {elm.coherent_int_form_factor_.y()};
    if (x2 >= x.back())
      return 0.0;
    int i = x2 <= x.front() ? 0 : lower_bound_index(x.cbegin(), x.cend(), x2);
    double form_factor_sq = static_cast<double>(elm.Z_) * elm.Z_ *
                            (y[i + 1] - y[i]) / (x[i + 1] - x[i]);

    double dsig_dmu = 0.5 * R_ELECTRON_SQ * (1.0 + mu * mu) * form_factor_sq;
    return wgt * dsig_dmu / micro.coherent;
  };
  score_point_tally_impl(p.r(), p.type(), p.time(), pdf);
}

void score_point_tally_incoherent(Particle& p, int i_element)
{
  const auto& elm {*data::elements[i_element]};
  const auto& micro {p.photon_xs(i_element)};

  double alpha = p.E() / MASS_ELECTRON_EV;
  auto u_n = p.u();
  double wgt = p.wgt();

  auto pdf = [&](Direction u, double& E) {
    double mu = u.dot(u_n);

    // Klein-Nishina differential cross section for the free-electron
    // scattering angle mu weighted by the incoherent scattering function
    // S(x, Z), matching the rejection sampling in
    // PhotonInteraction::compton_scatter
    double alpha_out = alpha / (1.0 + alpha * (1.0 - mu));
    double f = alpha_out / alpha;
    double kn = 0.5 * R_ELECTRON_SQ * f * f * (f + 1.0 / f + mu * mu - 1.0);
    double x =
      MASS_ELECTRON_EV / PLANCK_C * alpha * std::sqrt(0.5 * (1.0 - mu));
    double sf = elm.incoherent_form_factor_(x);

    // Sample the Doppler-broadened outgoing energy for this angle
    int i_shell;
    elm.compton_doppler(alpha, mu, &E, &i_shell, p.current_seed());

    return wgt * kn * sf / micro.incoherent;
  };
  score_point_tally_impl(p.r(), p.type(), p.time(), pdf);
}

void score_point_tally_isotropic_photon(
  Particle& p, double E, double multiplicity)
{
  int photon = ParticleType::photon().transport_index();
  if (E < settings::energy_cutoff[photon])
    return;

  double val = p.wgt() * multiplicity / (4.0 * PI);
  auto pdf = [&](Direction u, double& E_out) {
    E_out = E;
    return val;
  };
  score_point_tally_impl(p.r(), ParticleType::photon(), p.time(), pdf);
}

void score_point_tally_photon_production(
  Particle& p, int i_nuclide, const Reaction& rx, int i_product, double wgt)
{
  const auto& nuc {data::nuclides[i_nuclide]};
  double awr = nuc->awr_;
  auto u_n = p.u();
  auto E_n = p.E();

  auto pdf = [&](Direction u, double& E) {
    double mu = u.dot(u_n);
    // Photon production distributions are sampled directly in the lab frame
    // (see sample_secondary_photons), so no CM-to-lab transformation is done
    return wgt *
           rx.products_[i_product].sample_energy_and_pdf(
             E_n, mu, E, p.current_seed(), false, awr) /
           (2.0 * PI);
  };
  score_point_tally_impl(p.r(), ParticleType::photon(), p.time(), pdf);
}

void score_point_tally_source(SourceSite& site, int source_index)
{
  auto src_ = model::external_sources[source_index].get();
  auto src = dynamic_cast<IndependentSource*>(src_);
  if (!src)
    fatal_error("Only independent source is valid for point detectors.");
  auto pdf = [&](Direction u, double& E) {
    E = site.E;
    return src->angle()->evaluate(u);
  };
  score_point_tally_impl(site.r, site.particle, site.time, pdf);
}

} // namespace openmc
