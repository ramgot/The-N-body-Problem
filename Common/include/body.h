#ifndef BODY_H
#define BODY_H

#include "vector3.h"
#include <vector>

struct Body {
    Vector3 position;
    Vector3 velocity;
    Vector3 acceleration;
    double mass;

    // Constructors
    Body();
    Body(const Vector3& pos, const Vector3& vel, double m);
    Body(const Body& other);

    // Methods
    void resetAcceleration();
    void updatePosition(double dt);
    void updateVelocityHalf(double dt);
    void updateVelocityFull(double dt);

    double kineticEnergy() const;
    double potentialEnergyWith(const Body& other) const;
    Vector3 forceFrom(const Body& other, double softening = 1e-9) const;
};

struct SystemState {
    std::vector<Body> bodies;
    double time;
    double total_energy;
    Vector3 total_momentum;
    Vector3 angular_momentum;

    SystemState(size_t n = 0);
    SystemState(const std::vector<Body>& b, double t = 0.0);

    void computeConservedQuantities();
    double energyError(const SystemState& initial) const;
    double momentumError(const SystemState& initial) const;
    double angularMomentumError(const SystemState& initial) const;
};

// Namespace for initial condition generators
namespace InitialConditions {
    std::vector<Body> twoBodyCircular(double m1, double m2, double distance, double t0 = 0.0);
    std::vector<Body> twoBodyElliptical(double m1, double m2, double a, double e, double t0 = 0.0);
    std::vector<Body> plummerSphere(size_t N, double total_mass, double scale_radius);
    std::vector<Body> sunEarthMoon();
    std::vector<Body> solarSystem();
    std::vector<Body> randomSphere(size_t N, double total_mass, double radius, unsigned int seed = 0);
}

#endif // BODY_H