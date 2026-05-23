#include "../../Common/include/body.h"
#include "../../Common/include/common.h"

#include <iostream>
#include <vector>
#include <cmath>
#include <chrono>
#include <stdexcept>
#include <string>
#include <algorithm>
#include <cctype>
#include <sycl/sycl.hpp>

std::string toLower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

sycl::queue createQueue(const std::string& device_choice) {
    std::string choice = toLower(device_choice);
    if (choice == "gpu") {
        return sycl::queue(sycl::gpu_selector_v, sycl::property::queue::in_order{});
    }
    if (choice == "cpu") {
        return sycl::queue(sycl::cpu_selector_v, sycl::property::queue::in_order{});
    }
    if (choice == "auto" || choice == "default") {
        return sycl::queue(sycl::default_selector_v, sycl::property::queue::in_order{});
    }
    throw std::invalid_argument("Unknown SYCL device choice '" + device_choice + "'. Use auto, cpu, or gpu.");
}

std::string syclDeviceTypeToString(sycl::info::device_type device_type) {
    if (device_type == sycl::info::device_type::gpu) {
        return "GPU";
    }
    if (device_type == sycl::info::device_type::cpu) {
        return "CPU";
    }
    if (device_type == sycl::info::device_type::accelerator) {
        return "ACCELERATOR";
    }
    return "UNKNOWN";
}

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

    sycl::queue q;

    // Device USM arrays for positions, velocities, accelerations, masses.
    double *pos_x, *pos_y, *pos_z;
    double *vel_x, *vel_y, *vel_z;
    double *acc_x, *acc_y, *acc_z;
    double *mass;

    std::string device_choice;
    std::string device_name;
    std::string device_type_str;
    size_t compute_units;

public:
    NBodySimulationSYCL(const std::vector<Body>& initial_bodies, double dt_, double t_max_, double soft_,
                        const std::string& device_choice_)
        : num_bodies(initial_bodies.size()), dt(dt_), t_max(t_max_), softening(soft_), bodies(initial_bodies),
          q(createQueue(device_choice_)),
          pos_x(sycl::malloc_device<double>(num_bodies, q)),
          pos_y(sycl::malloc_device<double>(num_bodies, q)),
          pos_z(sycl::malloc_device<double>(num_bodies, q)),
          vel_x(sycl::malloc_device<double>(num_bodies, q)),
          vel_y(sycl::malloc_device<double>(num_bodies, q)),
          vel_z(sycl::malloc_device<double>(num_bodies, q)),
          acc_x(sycl::malloc_device<double>(num_bodies, q)),
          acc_y(sycl::malloc_device<double>(num_bodies, q)),
          acc_z(sycl::malloc_device<double>(num_bodies, q)),
          mass(sycl::malloc_device<double>(num_bodies, q)),
          device_choice(toLower(device_choice_)),
          device_name(q.get_device().get_info<sycl::info::device::name>()),
          device_type_str(syclDeviceTypeToString(q.get_device().get_info<sycl::info::device::device_type>())),
          compute_units(q.get_device().get_info<sycl::info::device::max_compute_units>()) {
        if (!pos_x || !pos_y || !pos_z || !vel_x || !vel_y || !vel_z ||
            !acc_x || !acc_y || !acc_z || !mass) {
            throw std::runtime_error("Failed to allocate SYCL device USM memory.");
        }

        std::vector<double> host_pos_x(num_bodies), host_pos_y(num_bodies), host_pos_z(num_bodies);
        std::vector<double> host_vel_x(num_bodies), host_vel_y(num_bodies), host_vel_z(num_bodies);
        std::vector<double> host_mass(num_bodies);

        for(size_t i = 0; i < num_bodies; ++i){
            host_pos_x[i] = bodies[i].position.x;
            host_pos_y[i] = bodies[i].position.y;
            host_pos_z[i] = bodies[i].position.z;
            host_vel_x[i] = bodies[i].velocity.x;
            host_vel_y[i] = bodies[i].velocity.y;
            host_vel_z[i] = bodies[i].velocity.z;
            host_mass[i] = bodies[i].mass;
        }

        const size_t bytes = num_bodies * sizeof(double);
        q.memcpy(pos_x, host_pos_x.data(), bytes);
        q.memcpy(pos_y, host_pos_y.data(), bytes);
        q.memcpy(pos_z, host_pos_z.data(), bytes);
        q.memcpy(vel_x, host_vel_x.data(), bytes);
        q.memcpy(vel_y, host_vel_y.data(), bytes);
        q.memcpy(vel_z, host_vel_z.data(), bytes);
        q.memcpy(mass, host_mass.data(), bytes);
        q.memset(acc_x, 0, bytes);
        q.memset(acc_y, 0, bytes);
        q.memset(acc_z, 0, bytes);
        q.wait_and_throw();

        std::cout << "Initialization complete." << std::endl;
    }

    ~NBodySimulationSYCL() {
        sycl::free(pos_x, q);
        sycl::free(pos_y, q);
        sycl::free(pos_z, q);
        sycl::free(vel_x, q);
        sycl::free(vel_y, q);
        sycl::free(vel_z, q);
        sycl::free(acc_x, q);
        sycl::free(acc_y, q);
        sycl::free(acc_z, q);
        sycl::free(mass, q);
    }

    NBodySimulationSYCL(const NBodySimulationSYCL&) = delete;
    NBodySimulationSYCL& operator=(const NBodySimulationSYCL&) = delete;

    void computeAccelerations() {
        const size_t TILE = 128;
        size_t N = num_bodies;
        size_t global_size = ((N + TILE - 1) / TILE) * TILE;
        double soft = softening;
        double G_val = G;

        q.submit([&](sycl::handler& h) {

            const double* px = pos_x;
            const double* py = pos_y;
            const double* pz = pos_z;
            const double* m = mass;

            double* ax = acc_x;
            double* ay = acc_y;
            double* az = acc_z;

            sycl::local_accessor<double,1> tile_x(TILE,h);
            sycl::local_accessor<double,1> tile_y(TILE,h);
            sycl::local_accessor<double,1> tile_z(TILE,h);
            sycl::local_accessor<double,1> tile_m(TILE,h);

            h.parallel_for(
                sycl::nd_range<1>(sycl::range<1>(global_size), sycl::range<1>(TILE)),
                [=](sycl::nd_item<1> item){

                size_t i = item.get_global_id(0);
                bool active = i < N;

                double xi = active ? px[i] : 0.0;
                double yi = active ? py[i] : 0.0;
                double zi = active ? pz[i] : 0.0;

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
                    } else {
                        tile_x[item.get_local_id(0)] = 0.0;
                        tile_y[item.get_local_id(0)] = 0.0;
                        tile_z[item.get_local_id(0)] = 0.0;
                        tile_m[item.get_local_id(0)] = 0.0;
                    }

                    item.barrier();

                    if (active) {
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
                    }

                    item.barrier();
                }

                if (active) {
                    ax[i] = aix;
                    ay[i] = aiy;
                    az[i] = aiz;
                }
            });
        });
    }

    void integrationStep() {
        size_t N = num_bodies;
        double dt_local = dt;

        // First half of velocity update
        q.submit([&](sycl::handler& h){
            double* vx = vel_x;
            double* vy = vel_y;
            double* vz = vel_z;
            const double* ax = acc_x;
            const double* ay = acc_y;
            const double* az = acc_z;

            h.parallel_for(sycl::range<1>(N), [=](sycl::id<1> idx){
                size_t i = idx[0];
                vx[i] += 0.5*dt_local*ax[i];
                vy[i] += 0.5*dt_local*ay[i];
                vz[i] += 0.5*dt_local*az[i];
            });
        });

        // Update positions
        q.submit([&](sycl::handler& h){
            const double* vx = vel_x;
            const double* vy = vel_y;
            const double* vz = vel_z;
            double* px = pos_x;
            double* py = pos_y;
            double* pz = pos_z;

            h.parallel_for(sycl::range<1>(N), [=](sycl::id<1> idx){
                size_t i = idx[0];
                px[i] += dt_local*vx[i];
                py[i] += dt_local*vy[i];
                pz[i] += dt_local*vz[i];
            });
        });

        computeAccelerations();

        // Second half of velocity update
        q.submit([&](sycl::handler& h){
            double* vx = vel_x;
            double* vy = vel_y;
            double* vz = vel_z;
            const double* ax = acc_x;
            const double* ay = acc_y;
            const double* az = acc_z;

            h.parallel_for(sycl::range<1>(N), [=](sycl::id<1> idx){
                size_t i = idx[0];
                vx[i] += 0.5*dt_local*ax[i];
                vy[i] += 0.5*dt_local*ay[i];
                vz[i] += 0.5*dt_local*az[i];
            });
        });

        q.wait_and_throw();
    }

    PerformanceMetrics run() {
        PerformanceMetrics metrics;
        size_t steps = static_cast<size_t>(t_max / dt);

        std::cout << "Starting simulation on device:" << std::endl;
        std::cout << "  Requested Device: " << device_choice << std::endl;
        std::cout << "  Device Type: " << device_type_str << std::endl;
        std::cout << "  Device Name: " << device_name << std::endl;
        std::cout << "  Compute Units: " << compute_units << std::endl;
        std::cout << "Total steps: " << steps << std::endl;

        SystemState initial_state(bodies, 0.0);
        initial_state.computeConservedQuantities();

        auto start_time = std::chrono::high_resolution_clock::now();

        computeAccelerations();
        q.wait_and_throw();

        for(size_t step = 0; step < steps; ++step){
            integrationStep();

            if(steps > 100 && step % (steps/10) == 0){
                std::cout << "\rProgress: " << (step*100)/steps << "%" << std::flush;
            }
        }

        std::cout << "\rProgress: 100%" << std::endl;

        auto end_time = std::chrono::high_resolution_clock::now();
        metrics.execution_time = std::chrono::duration<double>(end_time - start_time).count();

        // Read back final state from device USM arrays.
        std::vector<double> host_pos_x(num_bodies), host_pos_y(num_bodies), host_pos_z(num_bodies);
        std::vector<double> host_vel_x(num_bodies), host_vel_y(num_bodies), host_vel_z(num_bodies);
        const size_t bytes = num_bodies * sizeof(double);
        q.memcpy(host_pos_x.data(), pos_x, bytes);
        q.memcpy(host_pos_y.data(), pos_y, bytes);
        q.memcpy(host_pos_z.data(), pos_z, bytes);
        q.memcpy(host_vel_x.data(), vel_x, bytes);
        q.memcpy(host_vel_y.data(), vel_y, bytes);
        q.memcpy(host_vel_z.data(), vel_z, bytes);
        q.wait_and_throw();

        for (size_t i = 0; i < num_bodies; ++i) {
            bodies[i].position = Vector3(host_pos_x[i], host_pos_y[i], host_pos_z[i]);
            bodies[i].velocity = Vector3(host_vel_x[i], host_vel_y[i], host_vel_z[i]);
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
    const std::string& getDeviceName() const { return device_name; }
    const std::string& getDeviceType() const { return device_type_str; }
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
        std::string device_choice = "auto";

        if(argc > 1) n_bodies = std::stoul(argv[1]);
        if(argc > 2) dt = std::stod(argv[2]);
        if(argc > 3) t_max = std::stod(argv[3]);
        if(argc > 4) scenario = argv[4];
        for (int i = 5; i < argc; ++i) {
            std::string arg = argv[i];
            if (arg == "--device" && i + 1 < argc) {
                device_choice = argv[++i];
            } else if (arg.rfind("--device=", 0) == 0) {
                device_choice = arg.substr(std::string("--device=").size());
            } else if (arg == "--help" || arg == "-h") {
                std::cout << "Usage: " << argv[0] << " [N] [dt] [t_max] [scenario] [--device auto|cpu|gpu]" << std::endl;
                return 0;
            } else {
                throw std::invalid_argument("Unknown argument '" + arg + "'");
            }
        }

        std::cout << "N-Body Simulation (SYCL Velocity Verlet)" << std::endl;
        std::cout << "Number of bodies: " << n_bodies << std::endl;
        std::cout << "Time step: " << dt << " s" << std::endl;
        std::cout << "Total time: " << t_max/3600 << " hours" << std::endl;
        std::cout << "Scenario: " << scenario << std::endl;
        std::cout << "Requested device: " << toLower(device_choice) << std::endl;

        std::vector<Body> bodies = createScenarioBodies(n_bodies, scenario);

        NBodySimulationSYCL simulation(bodies, dt, t_max, 1e3, device_choice);
        PerformanceMetrics metrics = simulation.run();

        std::cout << "\nResults:" << std::endl;
        std::cout << "--------" << std::endl;
        std::cout << "Execution time: " << metrics.execution_time << " seconds" << std::endl;
        std::cout << "Performance: " << metrics.gflops << " GFLOP/s" << std::endl;
        std::cout << "Energy error: " << metrics.energy_error << std::endl;
        std::cout << "Steps completed: " << metrics.steps_completed << std::endl;
        std::cout << "Device type: " << simulation.getDeviceType() << std::endl;
        std::cout << "Device name: " << simulation.getDeviceName() << std::endl;
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
