#ifndef TWO_BODY_SOLVER_H
#define TWO_BODY_SOLVER_H

#include "body.h"
#include "common.h"
#include <vector>

struct OrbitalElements {
    double a;           // Semi-major axis (m)
    double e;           // Eccentricity
    double i;           // Inclination (rad)
    double omega;       // Argument of periapsis (rad)
    double Omega;       // Longitude of ascending node (rad)
    double M0;          // Mean anomaly at epoch (rad)
    double epoch;       // Epoch time (s)
    double period;      // Orbital period (s)
};

class TwoBodySolver {
private:
    double m1, m2;              // Masses of bodies (kg)
    double mu;                   // Gravitational parameter G*(m1+m2)
    OrbitalElements elements;    // Orbital elements
    Vector3 com_pos;             // Center of mass position
    Vector3 com_vel;             // Center of mass velocity

    // Safe math helpers
    double safe_acos(double x) const;
    double safe_sqrt(double x) const;

    // Convert cartesian to orbital elements
    OrbitalElements cartesianToElements(const Vector3& r, const Vector3& v, double t0) const;

public:
    // Constructor
    TwoBodySolver(double mass1, double mass2);

    // Set initial conditions from state vectors
    void setInitialConditions(const Body& body1, const Body& body2, double t0 = 0.0);

    // Set directly from orbital elements
    void setElements(const OrbitalElements& elem,
        const Vector3& com_pos = Vector3(0, 0, 0),
        const Vector3& com_vel = Vector3(0, 0, 0));

    // Solve Kepler's equation M = E - e*sin(E)
    double solveKeplerEquation(double M, double e, double tolerance = 1e-12) const;

    // Get state at time t
    std::pair<Body, Body> computeStateAtTime(double t) const;

    // Get states at multiple times
    std::vector<std::pair<Body, Body>> computeStatesAtTimes(const std::vector<double>& times) const;

    // Get relative position at time t
    Vector3 computeRelativePosition(double t) const;

    // Get orbital period
    double getPeriod() const { return elements.period; }

    // Get orbital elements
    OrbitalElements getElements() const { return elements; }
};

#endif