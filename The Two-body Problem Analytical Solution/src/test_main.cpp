#include "two_body_solver.h"
#include <iostream>

int main() {
    std::cout << "=== Testing Two-Body Solver ===\n";
    
    try {
        // Солнце и Земля
        Body sun(Vector3(0, 0, 0), Vector3(0, 0, 0), SOLAR_MASS);
        
        double v_earth = std::sqrt(G * SOLAR_MASS / AU);
        Body earth(Vector3(AU, 0, 0), Vector3(0, v_earth, 0), EARTH_MASS);
        
        TwoBodySolver solver(SOLAR_MASS, EARTH_MASS);
        solver.setInitialConditions(sun, earth);
        
        auto elem = solver.getElements();
        std::cout << "Period: " << elem.period / YEAR << " years\n";
        std::cout << "Eccentricity: " << elem.e << "\n";
        
        auto state = solver.computeStateAtTime(elem.period / 4);
        Vector3 r = state.second.position - state.first.position;
        std::cout << "Position after 1/4 period: ("
                  << r.x / AU << ", " << r.y / AU << ") AU\n";
        
        std::cout << "Test PASSED!\n";
        return 0;
        
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << "\n";
        std::cout << "Test FAILED!\n";
        return 1;
    }
}