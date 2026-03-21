#include "../../Common/include/body.h"
#include "../../Common/include/common.h"
#include <iostream>
#include <iomanip>
#include <chrono>
#include <vector>
#include <cmath>

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

// Упрощенная инициализация для тестирования
std::vector<Body> createTestBodies(size_t N) {
    std::vector<Body> bodies(N);
    double mass = SOLAR_MASS; // Одинаковая масса для всех
    
    std::cout << "Creating " << N << " test bodies..." << std::endl;
    
    // Простая кубическая решетка для тестирования
    int grid_size = static_cast<int>(std::ceil(std::pow(N, 1.0/3.0)));
    double spacing = AU * 0.1; // Расстояние между телами
    
    size_t index = 0;
    for (int i = 0; i < grid_size && index < N; ++i) {
        for (int j = 0; j < grid_size && index < N; ++j) {
            for (int k = 0; k < grid_size && index < N; ++k) {
                Vector3 pos(
                    (i - grid_size/2.0) * spacing,
                    (j - grid_size/2.0) * spacing,
                    (k - grid_size/2.0) * spacing
                );
                
                // Небольшие случайные скорости
                Vector3 vel(
                    (rand() / (double)RAND_MAX - 0.5) * 1000,
                    (rand() / (double)RAND_MAX - 0.5) * 1000,
                    (rand() / (double)RAND_MAX - 0.5) * 1000
                );
                
                bodies[index++] = Body(pos, vel, mass);
            }
        }
    }
    
    std::cout << "Created " << index << " bodies" << std::endl;
    return bodies;
}

int main(int argc, char** argv) {
    // Параметры по умолчанию для тестирования
    size_t n_bodies = 100;  // Уменьшил для тестирования
    double dt = 3600.0;      // 1 час
    double t_max = 24 * 3600; // 1 день (вместо года)

    // Parse command line arguments
    if (argc > 1) n_bodies = std::stoul(argv[1]);
    if (argc > 2) dt = std::stod(argv[2]);
    if (argc > 3) t_max = std::stod(argv[3]);

    std::cout << "N-Body Simulation (Serial Version - Test Mode)" << std::endl;
    std::cout << "==============================================" << std::endl;
    std::cout << "Number of bodies: " << n_bodies << std::endl;
    std::cout << "Time step: " << dt << " s" << std::endl;
    std::cout << "Total time: " << t_max / 3600 << " hours" << std::endl;

    // Создаем тестовые тела
    std::vector<Body> bodies = createTestBodies(n_bodies);

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