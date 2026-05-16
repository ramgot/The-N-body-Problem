#include "../include/body.h"
#include "../include/common.h"
#include <cmath>
#include <random>
#include <stdexcept>

Body::Body() : mass(0.0) {
    position.zero();
    velocity.zero();
    acceleration.zero();
}

Body::Body(const Vector3& pos, const Vector3& vel, double m)
    : position(pos), velocity(vel), mass(m) {
    acceleration.zero();
}

Body::Body(const Body& other)
    : position(other.position), velocity(other.velocity),
    acceleration(other.acceleration), mass(other.mass) {}

void Body::resetAcceleration() {
    acceleration.zero();
}

// Update methods for Verlet integration
void Body::updatePosition(double dt) {
    // Drift step for kick-drift-kick Velocity Verlet.
    position += velocity * dt;
}

void Body::updateVelocityHalf(double dt) {
    // v(t + dt/2) = v(t) + 0.5 * a(t) * dt
    velocity += acceleration * (0.5 * dt);
}

void Body::updateVelocityFull(double dt) {
    // v(t + dt) = v(t + dt/2) + 0.5 * a(t+dt) * dt
    velocity += acceleration * (0.5 * dt);
}

// Kinetic energy
double Body::kineticEnergy() const {
    return 0.5 * mass * velocity.norm2();
}

// Potential energy with another body
double Body::potentialEnergyWith(const Body& other) const {
    Vector3 r = other.position - position;
    return -G * mass * other.mass / r.norm();
}

// Force on this body from another body
Vector3 Body::forceFrom(const Body& other, double softening) const {
    Vector3 r = other.position - position;
    double dist_sq = r.norm2() + softening * softening;
    double dist = std::sqrt(dist_sq);
    double inv_dist3 = 1.0 / (dist * dist_sq);

    double force_mag = G * mass * other.mass * inv_dist3;
    return r * force_mag;
}

// SystemState implementation
SystemState::SystemState(size_t n) : bodies(n), time(0.0), total_energy(0.0) {}

SystemState::SystemState(const std::vector<Body>& b, double t)
    : bodies(b), time(t), total_energy(0.0) {}

void SystemState::computeConservedQuantities() {
    total_energy = 0.0;
    total_momentum.zero();
    angular_momentum.zero();

    size_t N = bodies.size();

    // Kinetic energy and momentum
    for (const auto& body : bodies) {
        total_energy += body.kineticEnergy();
        total_momentum += body.velocity * body.mass;
        angular_momentum += body.position.cross(body.velocity) * body.mass;
    }

    // Potential energy
    for (size_t i = 0; i < N; ++i) {
        for (size_t j = i + 1; j < N; ++j) {
            total_energy += bodies[i].potentialEnergyWith(bodies[j]);
        }
    }
}

double SystemState::energyError(const SystemState& initial) const {
    double delta = total_energy - initial.total_energy;
    if (!std::isfinite(delta) || !std::isfinite(initial.total_energy)) {
        return std::numeric_limits<double>::infinity();
    }

    double scale = std::abs(initial.total_energy);
    if (scale <= std::numeric_limits<double>::min()) {
        return std::abs(delta);
    }

    return std::abs(delta) / scale;
}

double SystemState::momentumError(const SystemState& initial) const {
    Vector3 diff = total_momentum - initial.total_momentum;
    return diff.norm() / initial.total_momentum.norm();
}

double SystemState::angularMomentumError(const SystemState& initial) const {
    Vector3 diff = angular_momentum - initial.angular_momentum;
    return diff.norm() / initial.angular_momentum.norm();
}

// Initial condition generators
namespace InitialConditions {

    std::vector<Body> twoBodyCircular(double m1, double m2, double distance, double t0) {
        (void)t0;
        std::vector<Body> bodies(2);

        double mu = G * (m1 + m2);
        double v = std::sqrt(mu / distance);

        // Body 1 at origin
        bodies[0] = Body(Vector3(0, 0, 0), Vector3(0, 0, 0), m1);

        // Body 2 on circular orbit
        bodies[1] = Body(Vector3(distance, 0, 0), Vector3(0, v, 0), m2);

        return bodies;
    }

    std::vector<Body> twoBodyElliptical(double m1, double m2, double a, double e, double t0) {
        (void)t0;
        std::vector<Body> bodies(2);

        double r_peri = a * (1 - e);
        double v_peri = std::sqrt(G * (m1 + m2) * (1 + e) / (r_peri * (1 - e)));

        bodies[0] = Body(Vector3(0, 0, 0), Vector3(0, 0, 0), m1);
        bodies[1] = Body(Vector3(r_peri, 0, 0), Vector3(0, v_peri, 0), m2);

        return bodies;
    }

    std::vector<Body> plummerSphere(size_t N, double total_mass, double scale_radius) {
        std::vector<Body> bodies(N);
        double mass_per_body = total_mass / N;

        // Simple uniform sphere for demonstration
        // For actual Plummer model, more sophisticated generation needed
        for (size_t i = 0; i < N; ++i) {
            double r = scale_radius * std::pow(rand() / (double)RAND_MAX, 1.0 / 3.0);
            double theta = 2.0 * M_PI * (rand() / (double)RAND_MAX);
            double phi = std::acos(2.0 * (rand() / (double)RAND_MAX) - 1.0);

            Vector3 pos(
                r * std::sin(phi) * std::cos(theta),
                r * std::sin(phi) * std::sin(theta),
                r * std::cos(phi)
            );

            // Velocity from virial theorem approximation
            double v = std::sqrt(G * total_mass / r) * 0.5;
            double v_theta = 2.0 * M_PI * (rand() / (double)RAND_MAX);
            double v_phi = std::acos(2.0 * (rand() / (double)RAND_MAX) - 1.0);

            Vector3 vel(
                v * std::sin(v_phi) * std::cos(v_theta),
                v * std::sin(v_phi) * std::sin(v_theta),
                v * std::cos(v_phi)
            );

            bodies[i] = Body(pos, vel, mass_per_body);
        }

        return bodies;
    }

    std::vector<Body> sunEarthMoon() {
        const double m_sun = SOLAR_MASS;
        const double m_earth = EARTH_MASS;
        const double m_moon = 7.3477e22;
        const double earth_semi_major = AU;
        const double moon_distance = 384400e3;
        const double earth_speed = 29.78e3;
        const double moon_speed = 1.022e3;

        Vector3 earth_pos(earth_semi_major, 0, 0);
        Vector3 moon_pos = earth_pos + Vector3(moon_distance, 0, 0);
        Vector3 earth_vel(0, earth_speed, 0);
        Vector3 moon_vel(0, earth_speed + moon_speed, 0);

        Vector3 sun_vel = -(earth_vel * m_earth + moon_vel * m_moon) / m_sun;

        std::vector<Body> bodies(3);
        bodies[0] = Body(Vector3(0, 0, 0), sun_vel, m_sun);
        bodies[1] = Body(earth_pos, earth_vel, m_earth);
        bodies[2] = Body(moon_pos, moon_vel, m_moon);
        return bodies;
    }

    std::vector<Body> solarSystem() {
        struct PlanetInfo { const char* name; double a_au; double mass; };
        const PlanetInfo planets[] = {
            {"Mercury", 0.387, 3.3011e23},
            {"Venus",   0.723, 4.8675e24},
            {"Earth",   1.000, 5.9724e24},
            {"Mars",    1.524, 6.4171e23},
            {"Jupiter", 5.204, 1.8982e27},
            {"Saturn",  9.582, 5.6834e26},
            {"Uranus", 19.201, 8.6810e25},
            {"Neptune",30.047, 1.02413e26},
            {"Pluto",  39.48,  1.303e22},
        };

        std::vector<Body> bodies;
        bodies.reserve(1 + sizeof(planets) / sizeof(planets[0]));

        // Sun at origin; velocity adjusted after planets are initialized
        bodies.emplace_back(Vector3(0, 0, 0), Vector3(0, 0, 0), SOLAR_MASS);

        for (const auto& planet : planets) {
            double radius = planet.a_au * AU;
            double speed = std::sqrt(G * SOLAR_MASS / radius);
            bodies.emplace_back(Vector3(radius, 0, 0), Vector3(0, speed, 0), planet.mass);
        }

        Vector3 total_momentum(0, 0, 0);
        for (size_t i = 1; i < bodies.size(); ++i) {
            total_momentum += bodies[i].velocity * bodies[i].mass;
        }
        bodies[0].velocity = -total_momentum / bodies[0].mass;
        return bodies;
    }

    std::vector<Body> randomSphere(size_t N, double total_mass, double radius, unsigned int seed) {
        std::mt19937_64 rng(seed ? seed : 123456789);
        std::uniform_real_distribution<double> unit(0.0, 1.0);
        std::uniform_real_distribution<double> direction(-1.0, 1.0);

        std::vector<Body> bodies;
        bodies.reserve(N);
        double mass_per_body = total_mass / static_cast<double>(N);

        for (size_t i = 0; i < N; ++i) {
            double u = unit(rng);
            double r = radius * std::cbrt(u);
            double theta = std::acos(direction(rng));
            double phi = 2.0 * M_PI * unit(rng);

            Vector3 pos(
                r * std::sin(theta) * std::cos(phi),
                r * std::sin(theta) * std::sin(phi),
                r * std::cos(theta)
            );

            double speed = std::sqrt(G * total_mass / (r + 1e6));
            Vector3 vel(
                speed * std::sin(theta) * std::cos(phi),
                speed * std::sin(theta) * std::sin(phi),
                speed * std::cos(theta)
            );

            bodies.emplace_back(pos, vel, mass_per_body);
        }

        return bodies;
    }

} // namespace InitialConditions
