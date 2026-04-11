#include "../../Common/include/body.h"
#include "../../Common/include/common.h"

#include <iostream>
#include <vector>
#include <cmath>
#include <chrono>
#include <stdexcept>
#include <string>
#include <sycl/sycl.hpp>

// ========================================
// SYCL N-Body Simulation Class
// ========================================
class NBodySimulationSYCL {
private:
    size_t num_bodies;
    double dt;
    double t_max;
    double softening;

    std::vector<Body> bodies;

    // SYCL buffers for positions, velocities, accelerations, masses
    sycl::buffer<double> pos_x, pos_y, pos_z;
    sycl::buffer<double> vel_x, vel_y, vel_z;
    sycl::buffer<double> acc_x, acc_y, acc_z;
    sycl::buffer<double> mass;

    sycl::queue q;
    size_t compute_units;

public:
    NBodySimulationSYCL(const std::vector<Body>& initial_bodies, double dt_, double t_max_, double soft_)
        : bodies(initial_bodies), num_bodies(initial_bodies.size()), dt(dt_), t_max(t_max_), softening(soft_),
          pos_x(sycl::range<1>(num_bodies)),
          pos_y(sycl::range<1>(num_bodies)),
          pos_z(sycl::range<1>(num_bodies)),
          vel_x(sycl::range<1>(num_bodies)),
          vel_y(sycl::range<1>(num_bodies)),
          vel_z(sycl::range<1>(num_bodies)),
          acc_x(sycl::range<1>(num_bodies)),
          acc_y(sycl::range<1>(num_bodies)),
          acc_z(sycl::range<1>(num_bodies)),
          mass(sycl::range<1>(num_bodies)),
          q(sycl::gpu_selector_v),
          compute_units(q.get_device().get_info<sycl::info::device::max_compute_units>())
          pos_y(sycl::range<1>(num_bodies)),
          pos_z(sycl::range<1>(num_bodies)),
          vel_x(sycl::range<1>(num_bodies)),
          vel_y(sycl::range<1>(num_bodies)),
          vel_z(sycl::range<1>(num_bodies)),
          acc_x(sycl::range<1>(num_bodies)),
          acc_y(sycl::range<1>(num_bodies)),
          acc_z(sycl::range<1>(num_bodies)),
          mass(sycl::range<1>(num_bodies)),
          q(sycl::gpu_selector_v)
    {
        std::cout << "Initializing SYCL simulation with " << num_bodies << " bodies..." << std::endl;
        if (!q.get_device().has(sycl::aspect::fp64)) {
            throw std::runtime_error(
                "Selected SYCL device does not support double precision (fp64). "
                "Use a different device or switch the simulation to float.");
        }

        // Copy initial data to buffers
        auto posx = pos_x.get_host_access(sycl::write_only);
        auto posy = pos_y.get_host_access(sycl::write_only);
        auto posz = pos_z.get_host_access(sycl::write_only);
        auto velx = vel_x.get_host_access(sycl::write_only);
        auto vely = vel_y.get_host_access(sycl::write_only);
        auto velz = vel_z.get_host_access(sycl::write_only);
        auto m = mass.get_host_access(sycl::write_only);

        for(size_t i = 0; i < num_bodies; ++i){
            posx[i] = bodies[i].position.x;
            posy[i] = bodies[i].position.y;
            posz[i] = bodies[i].position.z;

            velx[i] = bodies[i].velocity.x;
            vely[i] = bodies[i].velocity.y;
            velz[i] = bodies[i].velocity.z;

            m[i] = bodies[i].mass;
        }

        std::cout << "Initialization complete." << std::endl;
    }

    void computeAccelerations() {
        const size_t TILE = 128;
        size_t N = num_bodies;
        size_t global_size = ((N + TILE - 1) / TILE) * TILE;
        double soft = softening;
        double G_val = G;

        q.submit([&](sycl::handler& h) {

            auto px = pos_x.get_access<sycl::access::mode::read>(h);
            auto py = pos_y.get_access<sycl::access::mode::read>(h);
            auto pz = pos_z.get_access<sycl::access::mode::read>(h);
            auto m  = mass.get_access<sycl::access::mode::read>(h);

            auto ax = acc_x.get_access<sycl::access::mode::write>(h);
            auto ay = acc_y.get_access<sycl::access::mode::write>(h);
            auto az = acc_z.get_access<sycl::access::mode::write>(h);

            sycl::local_accessor<double,1> tile_x(TILE,h);
            sycl::local_accessor<double,1> tile_y(TILE,h);
            sycl::local_accessor<double,1> tile_z(TILE,h);
            sycl::local_accessor<double,1> tile_m(TILE,h);

            h.parallel_for(
                sycl::nd_range<1>(sycl::range<1>(global_size), sycl::range<1>(TILE)),
                [=](sycl::nd_item<1> item){

                size_t i = item.get_global_id(0);
                if (i >= N) {
                    return;
                }

                double xi = px[i];
                double yi = py[i];
                double zi = pz[i];

                double aix = 0;
                double aiy = 0;
                double aiz = 0;

                for(size_t tile = 0; tile < N; tile += TILE){

                    size_t j = tile + item.get_local_id(0);

                    if(j < N){
                        tile_x[item.get_local_id(0)] = px[j];
                        tile_y[item.get_local_id(0)] = py[j];
                        tile_z[item.get_local_id(0)] = pz[j];
                        tile_m[item.get_local_id(0)] = m[j];
                    }

                    item.barrier();

                    for(size_t k = 0; k < TILE && tile+k < N; k++){
                        double dx = tile_x[k] - xi;
                        double dy = tile_y[k] - yi;
                        double dz = tile_z[k] - zi;

                        double dist2 = dx*dx + dy*dy + dz*dz + soft*soft;
                        double inv = sycl::rsqrt(dist2);
                        double inv3 = inv*inv*inv;

                        double f = G_val * tile_m[k] * inv3;

                        aix += dx*f;
                        aiy += dy*f;
                        aiz += dz*f;
                    }

                    item.barrier();
                }

                ax[i] = aix;
                ay[i] = aiy;
                az[i] = aiz;
            });
        });
    }

    void integrationStep() {
        std::cout << "> Start integrationStep..." << std::endl;
        size_t N = num_bodies;
        double dt_local = dt;

        // First half of velocity update
        std::cout << ">> First half of velocity update..." << std::endl;
        q.submit([&](sycl::handler& h){
            std::cout << ">>> In submit..." << std::endl;
            auto vx = vel_x.get_access<sycl::access::mode::read_write>(h);
            auto vy = vel_y.get_access<sycl::access::mode::read_write>(h);
            auto vz = vel_z.get_access<sycl::access::mode::read_write>(h);
            auto ax = acc_x.get_access<sycl::access::mode::read>(h);
            auto ay = acc_y.get_access<sycl::access::mode::read>(h);
            auto az = acc_z.get_access<sycl::access::mode::read>(h);

            std::cout << ">>> parallel_for..." << std::endl;
            h.parallel_for(N, [=](auto i){
                vx[i] += 0.5*dt_local*ax[i];
                vy[i] += 0.5*dt_local*ay[i];
                vz[i] += 0.5*dt_local*az[i];
            });
            std::cout << ">>> Out submit..." << std::endl;
        });

        // Update positions
        std::cout << ">> Update positions..." << std::endl;
        q.submit([&](sycl::handler& h){
            auto vx = vel_x.get_access<sycl::access::mode::read>(h);
            auto vy = vel_y.get_access<sycl::access::mode::read>(h);
            auto vz = vel_z.get_access<sycl::access::mode::read>(h);
            auto px = pos_x.get_access<sycl::access::mode::read_write>(h);
            auto py = pos_y.get_access<sycl::access::mode::read_write>(h);
            auto pz = pos_z.get_access<sycl::access::mode::read_write>(h);

            h.parallel_for(N, [=](auto i){
                px[i] += dt_local*vx[i];
                py[i] += dt_local*vy[i];
                pz[i] += dt_local*vz[i];
            });
        });

        std::cout << ">> computeAccelerations..." << std::endl;
        computeAccelerations();

        // Second half of velocity update
        std::cout << ">> Second half of velocity update..." << std::endl;
        q.submit([&](sycl::handler& h){
            auto vx = vel_x.get_access<sycl::access::mode::read_write>(h);
            auto vy = vel_y.get_access<sycl::access::mode::read_write>(h);
            auto vz = vel_z.get_access<sycl::access::mode::read_write>(h);
            auto ax = acc_x.get_access<sycl::access::mode::read>(h);
            auto ay = acc_y.get_access<sycl::access::mode::read>(h);
            auto az = acc_z.get_access<sycl::access::mode::read>(h);

            h.parallel_for(N, [=](auto i){
                vx[i] += 0.5*dt_local*ax[i];
                vy[i] += 0.5*dt_local*ay[i];
                vz[i] += 0.5*dt_local*az[i];
            });
        });

        std::cout << ">> Wait..." << std::endl;
        q.wait(); // ждать завершения всех kernel
        std::cout << "> End integrationStep..." << std::endl;
    }

    PerformanceMetrics run() {
        PerformanceMetrics metrics;
        size_t steps = static_cast<size_t>(t_max / dt);
        std::cout << "Starting simulation on device: " 
                  << q.get_device().get_info<sycl::info::device::name>() << std::endl;
        std::cout << "Total steps: " << steps << std::endl;

        SystemState initial_state(bodies, 0.0);
        initial_state.computeConservedQuantities();

        auto start_time = std::chrono::high_resolution_clock::now();

        computeAccelerations();
        q.wait_and_throw();

        std::cout << "Start loop..." << std::endl;
        for(size_t step = 0; step < steps; ++step){
            integrationStep();

            if(steps > 100 && step % (steps/10) == 0){
                std::cout << "\rProgress: " << (step*100)/steps << "%" << std::flush;
            }
        }

        std::cout << "\rProgress: 100%" << std::endl;

        auto end_time = std::chrono::high_resolution_clock::now();
        metrics.execution_time = std::chrono::duration<double>(end_time - start_time).count();

        // Read back final state from device buffers
        auto posx = pos_x.get_host_access(sycl::read_only);
        auto posy = pos_y.get_host_access(sycl::read_only);
        auto posz = pos_z.get_host_access(sycl::read_only);
        auto velx = vel_x.get_host_access(sycl::read_only);
        auto vely = vel_y.get_host_access(sycl::read_only);
        auto velz = vel_z.get_host_access(sycl::read_only);

        for (size_t i = 0; i < num_bodies; ++i) {
            bodies[i].position = Vector3(posx[i], posy[i], posz[i]);
            bodies[i].velocity = Vector3(velx[i], vely[i], velz[i]);
        }

        SystemState final_state(bodies, t_max);
        final_state.computeConservedQuantities();
        metrics.energy_error = final_state.energyError(initial_state);
        metrics.steps_completed = steps;

        double operations_per_pair = 20.0;
        double operations_per_body = 10.0;
        double total_pairs = 0.5 * num_bodies * (num_bodies - 1);
        metrics.flops = steps * (total_pairs * operations_per_pair + num_bodies * operations_per_body);
        metrics.gflops = metrics.flops / metrics.execution_time / 1e9;

        return metrics;
    }

    size_t getComputeUnits() const { return compute_units; }
};

// ========================================
// Scenario-based initial conditions
// ========================================
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

// ========================================
// Main
// ========================================
int main(int argc, char** argv){
    try {
        size_t n_bodies = 1000;
        double dt = 3600.0;
        double t_max = 24*3600;
        std::string scenario = "auto";

        if(argc > 1) n_bodies = std::stoul(argv[1]);
        if(argc > 2) dt = std::stod(argv[2]);
        if(argc > 3) t_max = std::stod(argv[3]);
        if(argc > 4) scenario = argv[4];

        std::cout << "N-Body Simulation (SYCL Velocity Verlet)" << std::endl;
        std::cout << "Number of bodies: " << n_bodies << std::endl;
        std::cout << "Time step: " << dt << " s" << std::endl;
        std::cout << "Total time: " << t_max/3600 << " hours" << std::endl;
        std::cout << "Scenario: " << scenario << std::endl;

        std::vector<Body> bodies = createScenarioBodies(n_bodies, scenario);

        NBodySimulationSYCL simulation(bodies, dt, t_max, 1e3);
        PerformanceMetrics metrics = simulation.run();

        std::cout << "\nResults:" << std::endl;
        std::cout << "--------" << std::endl;
        std::cout << "Execution time: " << metrics.execution_time << " seconds" << std::endl;
        std::cout << "Performance: " << metrics.gflops << " GFLOP/s" << std::endl;
        std::cout << "Energy error: " << metrics.energy_error << std::endl;
        std::cout << "Steps completed: " << metrics.steps_completed << std::endl;
        std::cout << "Compute units: " << simulation.getComputeUnits() << std::endl;

        return 0;
    } catch (const sycl::exception& e) {
        std::cerr << "SYCL error: " << e.what() << std::endl;
        return 1;
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
}
