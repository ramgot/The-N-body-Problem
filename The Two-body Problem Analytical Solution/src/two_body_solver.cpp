#include "two_body_solver.h"
#include <cmath>
#include <stdexcept>
#include <algorithm>
#include <string>

TwoBodySolver::TwoBodySolver(double mass1, double mass2)
    : m1(mass1), m2(mass2), mu(G* (mass1 + mass2)) {

    if (mass1 <= 0 || mass2 <= 0) {
        throw std::invalid_argument("Masses must be positive");
    }
}

double TwoBodySolver::safe_acos(double x) const {
    if (x <= -1.0) return M_PI;
    if (x >= 1.0) return 0.0;
    return std::acos(x);
}

double TwoBodySolver::safe_sqrt(double x) const {
    if (x < 0) {
        if (x > -1e-12) return 0.0;
        throw std::runtime_error("Negative value in sqrt: " + std::to_string(x));
    }
    return std::sqrt(x);
}

OrbitalElements TwoBodySolver::cartesianToElements(const Vector3& r, const Vector3& v, double t0) const {
    double r_mag = r.norm();
    double v_sq = v.norm2();

    if (r_mag < 1e-15) {
        throw std::runtime_error("Bodies are at the same position");
    }

    double energy_per_mass = 0.5 * v_sq - mu / r_mag;
    Vector3 h_vec = r.cross(v);
    double h_mag = h_vec.norm();

    if (h_mag < 1e-15) {
        throw std::runtime_error("Zero angular momentum (rectilinear motion)");
    }

    OrbitalElements elem;
    elem.a = -mu / (2.0 * energy_per_mass);
    elem.e = std::sqrt(1.0 + 2.0 * energy_per_mass * h_mag * h_mag / (mu * mu));
    elem.i = safe_acos(h_vec.z / h_mag);

    Vector3 n_vec(-h_vec.y, h_vec.x, 0.0);
    double n_mag = n_vec.norm();
    if (n_mag > 1e-15) {
        elem.Omega = safe_acos(n_vec.x / n_mag);
        if (n_vec.y < 0) elem.Omega = 2.0 * M_PI - elem.Omega;
    }
    else {
        elem.Omega = 0.0;
    }

    Vector3 e_vec = (v.cross(h_vec) * (1.0 / mu)) - (r * (1.0 / r_mag));
    double e_mag = e_vec.norm();

    if (n_mag > 1e-15 && e_mag > 1e-15) {
        double cos_omega = n_vec.dot(e_vec) / (n_mag * e_mag);
        cos_omega = std::max(-1.0, std::min(1.0, cos_omega));
        elem.omega = safe_acos(cos_omega);
        if (e_vec.z < 0) elem.omega = 2.0 * M_PI - elem.omega;
    }
    else {
        elem.omega = 0.0;
    }

    double cos_nu = e_vec.dot(r) / (e_mag * r_mag);
    double sin_nu = h_vec.dot(e_vec.cross(r)) / (h_mag * e_mag * r_mag);
    cos_nu = std::max(-1.0, std::min(1.0, cos_nu));
    double cos_E = (elem.e + cos_nu) / (1.0 + elem.e * cos_nu);
    double sin_E = safe_sqrt(1.0 - elem.e * elem.e) * sin_nu / (1.0 + elem.e * cos_nu);
    cos_E = std::max(-1.0, std::min(1.0, cos_E));
    double E = std::atan2(sin_E, cos_E);
    if (E < 0) E += 2.0 * M_PI;

    elem.M0 = E - elem.e * std::sin(E);
    elem.epoch = t0;
    elem.period = 2.0 * M_PI * std::sqrt(elem.a * elem.a * elem.a / mu);

    return elem;
}

void TwoBodySolver::setInitialConditions(const Body& body1, const Body& body2, double t0) {
    Vector3 r = body2.position - body1.position;
    Vector3 v = body2.velocity - body1.velocity;

    elements = cartesianToElements(r, v, t0);

    double total_mass = m1 + m2;
    com_pos = (body1.position * m1 + body2.position * m2) * (1.0 / total_mass);
    com_vel = (body1.velocity * m1 + body2.velocity * m2) * (1.0 / total_mass);
}

void TwoBodySolver::setElements(const OrbitalElements& elem,
    const Vector3& com_pos_,
    const Vector3& com_vel_) {
    elements = elem;
    com_pos = com_pos_;
    com_vel = com_vel_;
}

double TwoBodySolver::solveKeplerEquation(double M, double e, double tolerance) const {
    M = std::fmod(M, 2.0 * M_PI);
    if (M < 0) M += 2.0 * M_PI;

    double E = (e < 0.8) ? M : M + 0.85 * e * std::sin(M);

    const int max_iter = 50;
    for (int iter = 0; iter < max_iter; ++iter) {
        double sinE = std::sin(E);
        double cosE = std::cos(E);

        double f = E - e * sinE - M;
        double f_prime = 1.0 - e * cosE;

        if (std::abs(f_prime) < 1e-15) {
            f_prime = (f_prime >= 0) ? 1e-15 : -1e-15;
        }

        double delta = f / f_prime;
        E -= delta;

        if (E < 0) E += 2.0 * M_PI;
        if (E > 2.0 * M_PI) E -= 2.0 * M_PI;

        if (std::abs(delta) < tolerance) break;
    }

    return E;
}

Vector3 TwoBodySolver::computeRelativePosition(double t) const {
    double n = 2.0 * M_PI / elements.period;
    double M = elements.M0 + n * (t - elements.epoch);
    double E = solveKeplerEquation(M, elements.e);

    double cos_E = std::cos(E);
    double sin_E = std::sin(E);

    double x_orb = elements.a * (cos_E - elements.e);
    double y_orb = elements.a * safe_sqrt(1.0 - elements.e * elements.e) * sin_E;

    double cos_omega = std::cos(elements.omega);
    double sin_omega = std::sin(elements.omega);
    double cos_Omega = std::cos(elements.Omega);
    double sin_Omega = std::sin(elements.Omega);
    double cos_i = std::cos(elements.i);
    double sin_i = std::sin(elements.i);

    double Px = cos_omega * cos_Omega - sin_omega * cos_i * sin_Omega;
    double Py = cos_omega * sin_Omega + sin_omega * cos_i * cos_Omega;
    double Pz = sin_omega * sin_i;

    double Qx = -sin_omega * cos_Omega - cos_omega * cos_i * sin_Omega;
    double Qy = -sin_omega * sin_Omega + cos_omega * cos_i * cos_Omega;
    double Qz = cos_omega * sin_i;

    return Vector3(
        Px * x_orb + Qx * y_orb,
        Py * x_orb + Qy * y_orb,
        Pz * x_orb + Qz * y_orb
    );
}

std::pair<Body, Body> TwoBodySolver::computeStateAtTime(double t) const {
    Vector3 r_rel = computeRelativePosition(t);

    double n = 2.0 * M_PI / elements.period;
    double M = elements.M0 + n * (t - elements.epoch);
    double E = solveKeplerEquation(M, elements.e);

    double r_mag = elements.a * (1.0 - elements.e * std::cos(E));
    double factor = safe_sqrt(mu * elements.a) / r_mag;
    double vx_orb = -factor * std::sin(E);
    double vy_orb = factor * safe_sqrt(1.0 - elements.e * elements.e) * std::cos(E);

    double cos_omega = std::cos(elements.omega);
    double sin_omega = std::sin(elements.omega);
    double cos_Omega = std::cos(elements.Omega);
    double sin_Omega = std::sin(elements.Omega);
    double cos_i = std::cos(elements.i);
    double sin_i = std::sin(elements.i);

    double Px = cos_omega * cos_Omega - sin_omega * cos_i * sin_Omega;
    double Py = cos_omega * sin_Omega + sin_omega * cos_i * cos_Omega;
    double Pz = sin_omega * sin_i;

    double Qx = -sin_omega * cos_Omega - cos_omega * cos_i * sin_Omega;
    double Qy = -sin_omega * sin_Omega + cos_omega * cos_i * cos_Omega;
    double Qz = cos_omega * sin_i;

    Vector3 v_rel(
        Px * vx_orb + Qx * vy_orb,
        Py * vx_orb + Qy * vy_orb,
        Pz * vx_orb + Qz * vy_orb
    );

    double total_mass = m1 + m2;
    double factor1 = -m2 / total_mass;
    double factor2 = m1 / total_mass;

    Body body1, body2;
    body1.position = r_rel * factor1 + com_pos;
    body2.position = r_rel * factor2 + com_pos;
    body1.velocity = v_rel * factor1 + com_vel;
    body2.velocity = v_rel * factor2 + com_vel;
    body1.mass = m1;
    body2.mass = m2;

    return { body1, body2 };
}

std::vector<std::pair<Body, Body>> TwoBodySolver::computeStatesAtTimes(
    const std::vector<double>& times) const {

    std::vector<std::pair<Body, Body>> states;
    states.reserve(times.size());

    for (double t : times) {
        states.push_back(computeStateAtTime(t));
    }

    return states;
}
