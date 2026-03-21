#ifndef COMMON_H
#define COMMON_H

#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>

// Physical constants
constexpr double G = 6.67430e-11;          // Gravitational constant (m^3 kg^-1 s^-2)
constexpr double SOFTENING = 1e-9;          // Softening parameter for numerical stability
constexpr double SOLAR_MASS = 1.989e30;     // Solar mass (kg)
constexpr double EARTH_MASS = 5.972e24;     // Earth mass (kg)
constexpr double AU = 1.496e11;             // Astronomical unit (m)
constexpr double YEAR = 365.25 * 24 * 3600; // Year in seconds

// Mathematical constants
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// Simulation parameters
struct SimulationParams {
    size_t n_bodies;
    double dt;
    double t_max;
    double softening;

    SimulationParams(size_t n = 1000, double dt_ = 3600.0, double t_max_ = YEAR)
        : n_bodies(n), dt(dt_), t_max(t_max_), softening(SOFTENING) {}
};

// Performance metrics
struct PerformanceMetrics {
    double execution_time;   // seconds
    double flops;            // floating point operations
    double gflops;           // GFLOP/s
    double energy_error;     // relative energy error
    size_t steps_completed;

    PerformanceMetrics()
        : execution_time(0.0), flops(0.0), gflops(0.0),
        energy_error(0.0), steps_completed(0) {}
};

// Utility functions
inline double sqr(double x) { return x * x; }
inline double cube(double x) { return x * x * x; }

#endif // COMMON_H