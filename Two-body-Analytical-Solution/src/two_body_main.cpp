#include "two_body_solver.h"
#include "trajectory_writer.h"

#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr double kAnalyticalOpsPerStep = 220.0;

void computeAccelerations(std::vector<Body>& bodies) {
    for (auto& body : bodies) {
        body.resetAcceleration();
    }

    Vector3 force = bodies[0].forceFrom(bodies[1]);
    bodies[0].acceleration += force / bodies[0].mass;
    bodies[1].acceleration -= force / bodies[1].mass;
}

std::vector<Body> createInitialBodies(const std::string& scenario) {
    if (scenario == "auto" || scenario == "sun-earth" || scenario == "two-body") {
        Body sun(Vector3(0, 0, 0), Vector3(0, 0, 0), SOLAR_MASS);
        double v_earth = std::sqrt(G * SOLAR_MASS / AU);
        Body earth(Vector3(AU, 0, 0), Vector3(0, v_earth, 0), EARTH_MASS);
        return {sun, earth};
    }

    if (scenario == "elliptical") {
        return InitialConditions::twoBodyElliptical(SOLAR_MASS, EARTH_MASS, AU, 0.0167);
    }

    throw std::invalid_argument(
        "Unknown two-body scenario '" + scenario + "'. Use auto, sun-earth, two-body, or elliptical."
    );
}

std::string displayScenario(const std::string& scenario) {
    if (scenario == "auto" || scenario == "sun-earth" || scenario == "two-body") {
        return "sun-earth";
    }
    return scenario;
}

void printUsage(const char* program) {
    std::cout << "Usage: " << program
              << " [dt] [t_max] [--scenario auto|sun-earth|elliptical]"
              << " [--trajectory path] [--trajectory-format csv|binary]\n"
              << "\nCompatibility form: " << program << " 2 dt t_max [scenario]\n";
}

} // namespace

int main(int argc, char** argv) {
    double dt = 3600.0;
    double t_max = YEAR;
    std::string scenario = "sun-earth";
    std::string trajectory_file;
    TrajectoryFormat trajectory_format = TrajectoryFormat::Csv;
    std::vector<std::string> positional;

    try {
        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            if (arg == "--help" || arg == "-h") {
                printUsage(argv[0]);
                return 0;
            }
            if (arg == "--scenario" && i + 1 < argc) {
                scenario = argv[++i];
                continue;
            }
            if (arg.rfind("--scenario=", 0) == 0) {
                scenario = arg.substr(std::string("--scenario=").size());
                continue;
            }
            if (arg == "--trajectory" && i + 1 < argc) {
                trajectory_file = argv[++i];
                continue;
            }
            if (arg.rfind("--trajectory=", 0) == 0) {
                trajectory_file = arg.substr(std::string("--trajectory=").size());
                continue;
            }
            if (arg == "--trajectory-format" && i + 1 < argc) {
                trajectory_format = parseTrajectoryFormat(argv[++i]);
                continue;
            }
            if (arg.rfind("--trajectory-format=", 0) == 0) {
                trajectory_format = parseTrajectoryFormat(arg.substr(std::string("--trajectory-format=").size()));
                continue;
            }
            if (!arg.empty() && arg[0] == '-') {
                throw std::invalid_argument("Unexpected option '" + arg + "'");
            }
            positional.push_back(arg);
        }

        if (positional.size() == 1) {
            dt = std::stod(positional[0]);
        } else if (positional.size() == 2) {
            dt = std::stod(positional[0]);
            t_max = std::stod(positional[1]);
        } else if (positional.size() >= 3) {
            size_t requested_bodies = std::stoul(positional[0]);
            if (requested_bodies != 2) {
                std::cout << "Warning: two_body_solver always uses 2 bodies; requested N="
                          << requested_bodies << " will be ignored.\n";
            }
            dt = std::stod(positional[1]);
            t_max = std::stod(positional[2]);
            if (positional.size() >= 4) {
                scenario = positional[3];
            }
            if (positional.size() > 4) {
                throw std::invalid_argument("Too many positional arguments");
            }
        }

        if (dt <= 0.0 || t_max < 0.0) {
            throw std::invalid_argument("dt must be positive and t_max must be non-negative");
        }
    } catch (const std::exception& e) {
        std::cerr << "Error parsing command line: " << e.what() << std::endl;
        printUsage(argv[0]);
        return 1;
    }

    std::cout << "Two-Body Analytical Solver" << std::endl;
    std::cout << "==========================" << std::endl;
    std::cout << "Number of bodies: 2" << std::endl;
    std::cout << "Time step: " << dt << " s" << std::endl;
    std::cout << "Total time: " << t_max / 3600.0 << " hours" << std::endl;
    std::cout << "Scenario: " << displayScenario(scenario) << std::endl;
    if (!trajectory_file.empty()) {
        std::cout << "Trajectory output: " << trajectory_file << std::endl;
        std::cout << "Trajectory format: " << trajectoryFormatToString(trajectory_format) << std::endl;
    }

    std::vector<Body> initial_bodies;
    try {
        initial_bodies = createInitialBodies(scenario);
    } catch (const std::exception& e) {
        std::cerr << "Error loading initial conditions: " << e.what() << std::endl;
        return 1;
    }

    computeAccelerations(initial_bodies);
    SystemState initial_state(initial_bodies, 0.0);
    initial_state.computeConservedQuantities();

    TwoBodySolver solver(initial_bodies[0].mass, initial_bodies[1].mass);
    solver.setInitialConditions(initial_bodies[0], initial_bodies[1]);

    size_t steps = static_cast<size_t>(t_max / dt);
    std::cout << "Orbital period: " << solver.getPeriod() / YEAR << " years" << std::endl;
    std::cout << "Total steps to compute: " << steps << std::endl;
    std::cout << "Progress: 0%" << std::flush;

    TrajectoryWriter trajectory(trajectory_file, trajectory_format);
    if (trajectory.enabled()) {
        trajectory.write(0, 0.0, initial_bodies);
    }

    std::vector<Body> bodies = initial_bodies;
    auto start_time = std::chrono::high_resolution_clock::now();
    for (size_t step = 1; step <= steps; ++step) {
        auto state = solver.computeStateAtTime(step * dt);
        bodies[0] = state.first;
        bodies[1] = state.second;
        computeAccelerations(bodies);

        if (trajectory.enabled()) {
            trajectory.write(step, step * dt, bodies);
        }

        if (steps > 100 && step % (steps / 10) == 0) {
            int percent = static_cast<int>((step * 100) / steps);
            std::cout << "\rProgress: " << percent << "%" << std::flush;
        }
    }
    auto end_time = std::chrono::high_resolution_clock::now();
    std::cout << "\rProgress: 100%" << std::endl;

    PerformanceMetrics metrics;
    metrics.execution_time = std::chrono::duration<double>(end_time - start_time).count();
    metrics.steps_completed = steps;

    SystemState final_state(bodies, steps * dt);
    final_state.computeConservedQuantities();
    metrics.energy_error = final_state.energyError(initial_state);
    metrics.flops = steps * kAnalyticalOpsPerStep;
    metrics.gflops = metrics.execution_time > std::numeric_limits<double>::min()
        ? metrics.flops / metrics.execution_time / 1e9
        : 0.0;

    std::cout << "\nResults:" << std::endl;
    std::cout << "--------" << std::endl;
    std::cout << std::setprecision(8);
    std::cout << "Execution time: " << metrics.execution_time << " seconds" << std::endl;
    std::cout << "Performance: " << metrics.gflops << " GFLOP/s" << std::endl;
    std::cout << "Energy error: " << metrics.energy_error << std::endl;
    std::cout << "Steps completed: " << metrics.steps_completed << std::endl;

    return 0;
}
