cmake_minimum_required(VERSION 3.15)
project(NBodyProblem CXX)

# ============================================================================
# PROJECT CONFIGURATION
# ============================================================================

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Set default build type to Release
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# ============================================================================
# FIND PACKAGES
# ============================================================================

# OpenMP for parallel versions
find_package(OpenMP REQUIRED)

# Optional: Intel oneAPI for SYCL support
find_package(IntelDPCPP QUIET)

# ============================================================================
# DIRECTORIES
# ============================================================================

set(COMMON_DIR ${CMAKE_CURRENT_SOURCE_DIR}/Common)
set(NBODY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/The\ N-body\ Problem\ Numerical\ Solution)
set(TWOBODY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/The\ Two-body\ Problem\ Analytical\ Solution)
set(OBJ_DIR ${CMAKE_CURRENT_BINARY_DIR}/obj)

# ============================================================================
# COMMON LIBRARY
# ============================================================================

set(COMMON_SOURCES
    ${COMMON_DIR}/src/body.cpp
    ${COMMON_DIR}/src/Vector3.cpp
)

set(COMMON_HEADERS
    ${COMMON_DIR}/include/body.h
    ${COMMON_DIR}/include/common.h
    ${COMMON_DIR}/include/vector3.h
)

add_library(common OBJECT ${COMMON_SOURCES})
target_include_directories(common PUBLIC ${COMMON_DIR}/include)

# ============================================================================
# N-BODY SERIAL VERSION
# ============================================================================

add_executable(nbody_serial
    ${NBODY_DIR}/src/nbody_serial.cpp
    $<TARGET_OBJECTS:common>
)

target_include_directories(nbody_serial PRIVATE ${NBODY_DIR}/include ${COMMON_DIR}/include)
set_target_properties(nbody_serial PROPERTIES CXX_STANDARD 17)

# ============================================================================
# N-BODY OpenMP VERSION
# ============================================================================

add_executable(nbody_openmp
    ${NBODY_DIR}/src/nbody_openmp.cpp
    $<TARGET_OBJECTS:common>
)

target_include_directories(nbody_openmp PRIVATE ${NBODY_DIR}/include ${COMMON_DIR}/include)
target_link_libraries(nbody_openmp PRIVATE OpenMP::OpenMP_CXX)
target_compile_definitions(nbody_openmp PRIVATE ENABLE_OPENMP)
set_target_properties(nbody_openmp PROPERTIES CXX_STANDARD 17)

# ============================================================================
# N-BODY SYCL VERSION (Optional - requires Intel oneAPI)
# ============================================================================

if(IntelDPCPP_FOUND)
    message(STATUS "Intel oneAPI found - building SYCL version")
    
    add_executable(nbody_sycl
        ${NBODY_DIR}/src/nbody_sycl.cpp
        $<TARGET_OBJECTS:common>
    )
    
    target_include_directories(nbody_sycl PRIVATE ${NBODY_DIR}/include ${COMMON_DIR}/include)
    target_link_libraries(nbody_sycl PRIVATE IntelDPCPP::SYCL)
    set_target_properties(nbody_sycl PROPERTIES 
        CXX_STANDARD 17
        CXX_COMPILER_ID "IntelDPCPP"
    )
else()
    message(WARNING "Intel oneAPI not found - SYCL version will be skipped")
    message(STATUS "To install Intel oneAPI:")
    message(STATUS "  Windows: Visit https://www.intel.com/content/www/en/en/developer/tools/oneapi/hpc-toolkit-download.html")
    message(STATUS "  Linux/WSL: apt-get install intel-oneapi-compiler-dpcpp-cpp-and-cpp-classic")
endif()

# ============================================================================
# TWO-BODY ANALYTICAL SOLUTION
# ============================================================================

add_executable(two_body_solver
    ${TWOBODY_DIR}/src/two_body_solver.cpp
    ${TWOBODY_DIR}/src/test_main.cpp
    $<TARGET_OBJECTS:common>
)

target_include_directories(two_body_solver PRIVATE ${TWOBODY_DIR}/include ${COMMON_DIR}/include)
set_target_properties(two_body_solver PROPERTIES CXX_STANDARD 17)

# ============================================================================
# COMPILER FLAGS
# ============================================================================

if(MSVC)
    # Visual Studio
    target_compile_options(nbody_serial PRIVATE /W4 /O2)
    target_compile_options(nbody_openmp PRIVATE /W4 /O2)
    target_compile_options(two_body_solver PRIVATE /W4 /O2)
else()
    # GCC/Clang
    target_compile_options(nbody_serial PRIVATE -Wall -Wextra -O2)
    target_compile_options(nbody_openmp PRIVATE -Wall -Wextra -O2)
    target_compile_options(two_body_solver PRIVATE -Wall -Wextra -O2)
    
    if(IntelDPCPP_FOUND)
        target_compile_options(nbody_sycl PRIVATE -Wall -Wextra -O2)
    endif()
endif()

# ============================================================================
# OUTPUT DIRECTORIES
# ============================================================================

set_target_properties(nbody_serial PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)

set_target_properties(nbody_openmp PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)

set_target_properties(two_body_solver PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)

if(IntelDPCPP_FOUND)
    set_target_properties(nbody_sycl PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    )
endif()

# ============================================================================
# CUSTOM TARGETS FOR CONVENIENCE
# ============================================================================

# Target to build all
add_custom_target(all-targets DEPENDS nbody_serial nbody_openmp two_body_solver)

# Run targets
add_custom_target(run-serial
    COMMAND ${CMAKE_CURRENT_BINARY_DIR}/nbody_serial
    DEPENDS nbody_serial
    COMMENT "Running N-body Serial version..."
)

add_custom_target(run-openmp
    COMMAND ${CMAKE_CURRENT_BINARY_DIR}/nbody_openmp
    DEPENDS nbody_openmp
    COMMENT "Running N-body OpenMP version..."
)

add_custom_target(run-twobody
    COMMAND ${CMAKE_CURRENT_BINARY_DIR}/two_body_solver
    DEPENDS two_body_solver
    COMMENT "Running Two-body solver..."
)

if(IntelDPCPP_FOUND)
    add_custom_target(run-sycl
        COMMAND ${CMAKE_CURRENT_BINARY_DIR}/nbody_sycl
        DEPENDS nbody_sycl
        COMMENT "Running N-body SYCL version..."
    )
endif()

# ============================================================================
# PRINT BUILD SUMMARY
# ============================================================================

message(STATUS "")
message(STATUS "=== N-Body Problem Build Configuration ===")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "")
message(STATUS "Targets to build:")
message(STATUS "  ✓ nbody_serial      - Serial N-body simulation")
message(STATUS "  ✓ nbody_openmp      - Parallel N-body with OpenMP")
message(STATUS "  ✓ two_body_solver   - Two-body analytical solution")
if(IntelDPCPP_FOUND)
    message(STATUS "  ✓ nbody_sycl        - SYCL N-body (Intel oneAPI)")
else()
    message(STATUS "  ✗ nbody_sycl        - SYCL N-body (requires Intel oneAPI)")
endif()
message(STATUS "")
message(STATUS "Build with: cmake --build build")
message(STATUS "")
