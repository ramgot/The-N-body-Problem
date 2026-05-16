#include "two_body_solver.h"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <vector>

namespace {

double relativeError(double absolute_error, double scale) {
    if (std::abs(scale) <= std::numeric_limits<double>::min()) {
        return absolute_error;
    }
    return absolute_error / std::abs(scale);
}

void computeAccelerations(std::vector<Body>& bodies) {
    for (auto& body : bodies) {
        body.resetAcceleration();
    }

    Vector3 force = bodies[0].forceFrom(bodies[1]);
    bodies[0].acceleration += force / bodies[0].mass;
    bodies[1].acceleration -= force / bodies[1].mass;
}

std::vector<Body> integrateTwoBody(std::vector<Body> bodies, double dt, double t_max) {
    size_t steps = static_cast<size_t>(std::llround(t_max / dt));
    computeAccelerations(bodies);

    for (size_t step = 0; step < steps; ++step) {
        for (auto& body : bodies) {
            body.updateVelocityHalf(dt);
        }
        for (auto& body : bodies) {
            body.updatePosition(dt);
        }

        computeAccelerations(bodies);

        for (auto& body : bodies) {
            body.updateVelocityFull(dt);
        }
    }

    return bodies;
}

double totalEnergy(const std::vector<Body>& bodies) {
    double energy = 0.0;
    for (const auto& body : bodies) {
        energy += body.kineticEnergy();
    }
    energy += bodies[0].potentialEnergyWith(bodies[1]);
    return energy;
}

void printNumericalComparison(const TwoBodySolver& solver,
                              const std::vector<Body>& initial_bodies,
                              double dt,
                              double t_max) {
    std::vector<Body> numerical = integrateTwoBody(initial_bodies, dt, t_max);
    auto analytical = solver.computeStateAtTime(t_max);

    Vector3 numerical_r = numerical[1].position - numerical[0].position;
    Vector3 analytical_r = analytical.second.position - analytical.first.position;
    Vector3 numerical_v = numerical[1].velocity - numerical[0].velocity;
    Vector3 analytical_v = analytical.second.velocity - analytical.first.velocity;

    double position_abs_error = (numerical_r - analytical_r).norm();
    double velocity_abs_error = (numerical_v - analytical_v).norm();
    double initial_energy = totalEnergy(initial_bodies);
    double final_energy = totalEnergy(numerical);
    double energy_abs_error = std::abs(final_energy - initial_energy);

    std::cout << "\nNumerical Verlet vs analytical at T=" << t_max / 3600.0 << " h"
              << " (dt=" << dt << " s)\n";
    std::cout << "Position abs error: " << position_abs_error << " m\n";
    std::cout << "Position rel error: " << relativeError(position_abs_error, analytical_r.norm()) << "\n";
    std::cout << "Velocity abs error: " << velocity_abs_error << " m/s\n";
    std::cout << "Velocity rel error: " << relativeError(velocity_abs_error, analytical_v.norm()) << "\n";
    std::cout << "Energy abs error: " << energy_abs_error << " J\n";
    std::cout << "Energy rel error: " << relativeError(energy_abs_error, initial_energy) << "\n";
}

} // namespace

int main() {
    std::cout << "=== Testing Two-Body Solver ===\n";
    
    try {
        // Солнце и Земля
        Body sun(Vector3(0, 0, 0), Vector3(0, 0, 0), SOLAR_MASS);
        
        double v_earth = std::sqrt(G * SOLAR_MASS / AU);
        Body earth(Vector3(AU, 0, 0), Vector3(0, v_earth, 0), EARTH_MASS);
        std::vector<Body> initial_bodies = {sun, earth};
        
        TwoBodySolver solver(SOLAR_MASS, EARTH_MASS);
        solver.setInitialConditions(sun, earth);
        
        auto elem = solver.getElements();
        std::cout << "Period: " << elem.period / YEAR << " years\n";
        std::cout << "Eccentricity: " << elem.e << "\n";
        
        auto state = solver.computeStateAtTime(elem.period / 4);
        Vector3 r = state.second.position - state.first.position;
        std::cout << "Position after 1/4 period: ("
                  << r.x / AU << ", " << r.y / AU << ") AU\n";

        std::cout << std::scientific << std::setprecision(6);
        printNumericalComparison(solver, initial_bodies, 3600.0, 24.0 * 3600.0);
        printNumericalComparison(solver, initial_bodies, 3600.0, YEAR);
        
        std::cout << "Test PASSED!\n";
        return 0;
        
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << "\n";
        std::cout << "Test FAILED!\n";
        return 1;
    }
}
