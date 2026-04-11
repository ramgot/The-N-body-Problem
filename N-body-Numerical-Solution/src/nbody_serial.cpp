#include "../../Common/include/body.h"
#include "../../Common/include/common.h"
#include <iostream>
#include <iomanip>
#include <chrono>
#include <vector>
#include <cmath>
#include <string>

class NBodySimulationSerial {
private:
    std::vector<Body> bodies;
    SystemState current_state;
    SimulationParams params;
    size_t num_bodies;
    double dt;
    double t_max;
    double softening;

public:
    NBodySimulationSerial(const std::vector<Body>& initial_bodies, 
                          const SimulationParams& sim_params)
        : bodies(initial_bodies), 
          params(sim_params),
          num_bodies(initial_bodies.size()),
          dt(sim_params.dt),
          t_max(sim_params.t_max),
          softening(sim_params.softening) {
        std::cout << "Initializing simulation with " << num_bodies << " bodies..." << std::endl;
        current_state = SystemState(bodies, 0.0);
        current_state.computeConservedQuantities();
        std::cout << "Initialization complete." << std::endl;
    }

    void computeAccelerations() {
        // Reset accelerations
        for (auto& body : bodies) {
            body.resetAcceleration();
        }

        // Compute forces between all pairs
        for (size_t i = 0; i < num_bodies; ++i) {
            for (size_t j = i + 1; j < num_bodies; ++j) {
                Vector3 force = bodies[i].forceFrom(bodies[j], softening);
                
                // Apply force to both bodies (Newton's 3rd law)
                bodies[i].acceleration += force / bodies[i].mass;
                bodies[j].acceleration -= force / bodies[j].mass;
            }
        }
    }

    void integrationStep() {
        // First half of velocity update
        for (auto& body : bodies) {
            body.updateVelocityHalf(dt);
        }

        // Update positions
        for (auto& body : bodies) {
            body.updatePosition(dt);
        }

        // Compute new accelerations
        computeAccelerations();

        // Second half of velocity update
        for (auto& body : bodies) {
            body.updateVelocityFull(dt);
        }
    }

    PerformanceMetrics run() {
        PerformanceMetrics metrics;
        auto start_time = std::chrono::high_resolution_clock::now();

        size_t steps = static_cast<size_t>(t_max / dt);
        metrics.steps_completed = steps;
        
        std::cout << "Total steps to compute: " << steps << std::endl;
        std::cout << "Progress: 0%" << std::flush;

        // Main simulation loop
        for (size_t step_count = 0; step_count < steps; ++step_count) {
            integrationStep();
            
            // Show progress every 10%
            if (steps > 100 && step_count % (steps / 10) == 0) {
                int percent = (step_count * 100) / steps;
                std::cout << "\rProgress: " << percent << "%" << std::flush;
            }
            
            // Update system state every 100 steps
            if (step_count % 100 == 0) {
                current_state.bodies = bodies;
                current_state.time = step_count * dt;
                current_state.computeConservedQuantities();
            }
        }

        std::cout << "\rProgress: 100%" << std::endl;

        auto end_time = std::chrono::high_resolution_clock::now();
        metrics.execution_time = std::chrono::duration<double>(end_time - start_time).count();

        // Compute final state and errors
        current_state.bodies = bodies;
        current_state.time = steps * dt;
        current_state.computeConservedQuantities();

        // Compute initial state for error calculation
        SystemState initial_state(bodies, 0.0);
        initial_state.computeConservedQuantities();

        metrics.energy_error = current_state.energyError(initial_state);

        // Estimate FLOPS: for each pair (N*(N-1)/2) we do ~20 operations
        double operations_per_pair = 20.0;
        double operations_per_body = 10.0;
        double total_pairs = 0.5 * num_bodies * (num_bodies - 1);
        
        metrics.flops = steps * (total_pairs * operations_per_pair + 
                                 num_bodies * operations_per_body);
        metrics.gflops = metrics.flops / metrics.execution_time / 1e9;

        return metrics;
    }

    const SystemState& getState() const { return current_state; }
};

// Select an initial condition scenario for N-body simulation
std::vector<Body> createScenarioBodies(size_t N, const std::string& scenario) {
    if (scenario == "auto") {
        if (N == 3) {
            return InitialConditions::sunEarthMoon();
        }
        if (N == 10) {
            return InitialConditions::solarSystem();
        }
        return InitialConditions::randomSphere(N, SOLAR_MASS * 0.01 * N, AU * 2.0, 12345);
    }
    if (scenario == "sun-earth-moon") {
        return InitialConditions::sunEarthMoon();
    }
    if (scenario == "solar-system") {
        return InitialConditions::solarSystem();
    }
    if (scenario == "random") {
        return InitialConditions::randomSphere(N, SOLAR_MASS * 0.01 * N, AU * 2.0, 12345);
    }

    std::cerr << "Unknown scenario '" << scenario << "', using random initial conditions." << std::endl;
    return InitialConditions::randomSphere(N, SOLAR_MASS * 0.01 * N, AU * 2.0, 12345);
}

int main(int argc, char** argv) {
    // Default simulation parameters
    size_t n_bodies = 100;
    double dt = 3600.0;
    double t_max = 24 * 3600; // 1 day
    std::string scenario = "auto";

    // Parse command line arguments
    if (argc > 1) n_bodies = std::stoul(argv[1]);
    if (argc > 2) dt = std::stod(argv[2]);
    if (argc > 3) t_max = std::stod(argv[3]);
    if (argc > 4) scenario = argv[4];

    std::cout << "N-Body Simulation (Serial Version)" << std::endl;
    std::cout << "================================" << std::endl;
    std::cout << "Number of bodies: " << n_bodies << std::endl;
    std::cout << "Time step: " << dt << " s" << std::endl;
    std::cout << "Total time: " << t_max / 3600 << " hours" << std::endl;
    std::cout << "Scenario: " << scenario << std::endl;

    std::vector<Body> bodies = createScenarioBodies(n_bodies, scenario);

    SimulationParams params(n_bodies, dt, t_max);
    NBodySimulationSerial simulation(bodies, params);

    std::cout << "Starting simulation..." << std::endl;
    
    // Run simulation
    PerformanceMetrics metrics = simulation.run();

    // Output results
    std::cout << "\nResults:" << std::endl;
    std::cout << "--------" << std::endl;
    std::cout << "Execution time: " << metrics.execution_time << " seconds" << std::endl;
    std::cout << "Performance: " << metrics.gflops << " GFLOP/s" << std::endl;
    std::cout << "Energy error: " << metrics.energy_error << std::endl;
    std::cout << "Steps completed: " << metrics.steps_completed << std::endl;

    return 0;
}