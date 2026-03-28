# Makefile for N-body Problem Project
# Supports: Serial, OpenMP, and SYCL implementations
# Cross-platform: Windows/WSL and Linux

# ============================================================================
# CONFIGURATION
# ============================================================================

# Compiler selection
CXX = g++
CXX_SYCL = icpx

# Compiler flags
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -fPIC
CXXFLAGS_DEBUG = -std=c++17 -Wall -Wextra -g -O0
CXXFLAGS_OMP = $(CXXFLAGS) -fopenmp -DENABLE_OPENMP
CXXFLAGS_SYCL = -std=c++17 -Wall -Wextra -O2 -fsycl

# Directories
COMMON_DIR = Common
NBODY_DIR = The N-body Problem Numerical Solution
TWOBODY_DIR = The Two-body Problem Analytical Solution
OBJ_DIR = obj
BUILD_DIR = build

# Include directories
COMMON_INCLUDE = -I$(COMMON_DIR)/include
NBODY_INCLUDE = -I$(NBODY_DIR)/include $(COMMON_INCLUDE)
TWOBODY_INCLUDE = -I$(TWOBODY_DIR)/include $(COMMON_INCLUDE)

# Source files
COMMON_SRCS = $(COMMON_DIR)/src/body.cpp $(COMMON_DIR)/src/Vector3.cpp
NBODY_SERIAL_SRC = $(NBODY_DIR)/src/nbody_serial.cpp
NBODY_OMP_SRC = $(NBODY_DIR)/src/nbody_openmp.cpp
NBODY_SYCL_SRC = $(NBODY_DIR)/src/nbody_sycl.cpp
TWOBODY_SRCS = $(TWOBODY_DIR)/src/two_body_solver.cpp $(TWOBODY_DIR)/src/test_main.cpp

# Object files
COMMON_OBJS = $(addprefix $(OBJ_DIR)/, $(notdir $(COMMON_SRCS:.cpp=.o)))
NBODY_SERIAL_OBJ = $(OBJ_DIR)/nbody_serial.o
NBODY_OMP_OBJ = $(OBJ_DIR)/nbody_openmp.o
NBODY_SYCL_OBJ = $(OBJ_DIR)/nbody_sycl.o
TWOBODY_OBJS = $(addprefix $(OBJ_DIR)/, $(notdir $(TWOBODY_SRCS:.cpp=.o)))

# Executable names
NBODY_SERIAL_EXE = nbody_serial
NBODY_OMP_EXE = nbody_openmp
NBODY_SYCL_EXE = nbody_sycl
TWOBODY_EXE = two_body_solver

# Build mode (Debug or Release)
BUILD_MODE ?= Release

# SYCL backend (can be: nvidia, opencl, etc.)
SYCL_BACKEND ?= nvidia

# ============================================================================
# TARGETS
# ============================================================================

.PHONY: all clean help setup

# Default target
all: setup $(NBODY_SERIAL_EXE) $(NBODY_OMP_EXE) $(TWOBODY_EXE)

# All targets including SYCL
all-sycl: all $(NBODY_SYCL_EXE)

# Setup build directories
setup:
	@mkdir -p $(OBJ_DIR) $(BUILD_DIR)

# ============================================================================
# COMMON LIBRARY OBJECTS
# ============================================================================

$(OBJ_DIR)/body.o: $(COMMON_DIR)/src/body.cpp $(COMMON_DIR)/include/body.h
	$(CXX) $(CXXFLAGS) $(COMMON_INCLUDE) -c $< -o $@

$(OBJ_DIR)/Vector3.o: $(COMMON_DIR)/src/Vector3.cpp $(COMMON_DIR)/include/vector3.h
	$(CXX) $(CXXFLAGS) $(COMMON_INCLUDE) -c $< -o $@

# ============================================================================
# N-BODY SERIAL VERSION
# ============================================================================

$(NBODY_SERIAL_OBJ): $(NBODY_SERIAL_SRC)
	$(CXX) $(CXXFLAGS) $(NBODY_INCLUDE) -c $< -o $@

$(NBODY_SERIAL_EXE): $(NBODY_SERIAL_OBJ) $(COMMON_OBJS)
	$(CXX) $(CXXFLAGS) $(NBODY_INCLUDE) $^ -o $@
	@echo "Built: $@"

# ============================================================================
# N-BODY OpenMP VERSION
# ============================================================================

$(NBODY_OMP_OBJ): $(NBODY_OMP_SRC)
	$(CXX) $(CXXFLAGS_OMP) $(NBODY_INCLUDE) -c $< -o $@

$(NBODY_OMP_EXE): $(NBODY_OMP_OBJ) $(COMMON_OBJS)
	$(CXX) $(CXXFLAGS_OMP) $(NBODY_INCLUDE) $^ -o $@
	@echo "Built: $@"

# ============================================================================
# N-BODY SYCL VERSION (with Intel oneAPI)
# ============================================================================

$(NBODY_SYCL_OBJ): $(NBODY_SYCL_SRC)
	$(CXX_SYCL) $(CXXFLAGS_SYCL) $(NBODY_INCLUDE) -c $< -o $@

$(NBODY_SYCL_EXE): $(NBODY_SYCL_OBJ) $(COMMON_OBJS)
	$(CXX_SYCL) $(CXXFLAGS_SYCL) $(NBODY_INCLUDE) $^ -o $@
	@echo "Built SYCL version: $@"

# ============================================================================
# TWO-BODY ANALYTICAL SOLUTION
# ============================================================================

$(OBJ_DIR)/two_body_solver.o: $(TWOBODY_DIR)/src/two_body_solver.cpp $(TWOBODY_DIR)/include/two_body_solver.h
	$(CXX) $(CXXFLAGS) $(TWOBODY_INCLUDE) -c $< -o $@

$(OBJ_DIR)/test_main.o: $(TWOBODY_DIR)/src/test_main.cpp
	$(CXX) $(CXXFLAGS) $(TWOBODY_INCLUDE) -c $< -o $@

$(TWOBODY_EXE): $(OBJ_DIR)/two_body_solver.o $(OBJ_DIR)/test_main.o $(COMMON_OBJS)
	$(CXX) $(CXXFLAGS) $(TWOBODY_INCLUDE) $^ -o $@
	@echo "Built: $@"

# ============================================================================
# UTILITY TARGETS
# ============================================================================

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(OBJ_DIR) $(BUILD_DIR)
	rm -f $(NBODY_SERIAL_EXE) $(NBODY_OMP_EXE) $(NBODY_SYCL_EXE) $(TWOBODY_EXE)
	@echo "Clean complete."

# Run all executables
run: all
	@echo "Running N-body Serial version..."
	./$(NBODY_SERIAL_EXE)
	@echo "\nRunning N-body OpenMP version..."
	./$(NBODY_OMP_EXE)
	@echo "\nRunning Two-body solver..."
	./$(TWOBODY_EXE)

# Run individual tests
run-serial: $(NBODY_SERIAL_EXE)
	./$(NBODY_SERIAL_EXE)

run-openmp: $(NBODY_OMP_EXE)
	./$(NBODY_OMP_EXE)

run-sycl: $(NBODY_SYCL_EXE)
	./$(NBODY_SYCL_EXE)

run-twobody: $(TWOBODY_EXE)
	./$(TWOBODY_EXE)

# Help message
help:
	@echo "N-body Problem Project Makefile"
	@echo "================================"
	@echo ""
	@echo "Available targets:"
	@echo "  all              - Build all main executables (serial, OpenMP, two-body)"
	@echo "  all-sycl         - Build all including SYCL version (requires Intel oneAPI)"
	@echo "  clean            - Remove all build artifacts and executables"
	@echo "  run              - Build and run all executables"
	@echo "  run-serial       - Build and run serial version"
	@echo "  run-openmp       - Build and run OpenMP version"
	@echo "  run-sycl         - Build and run SYCL version (requires Intel oneAPI)"
	@echo "  run-twobody      - Build and run Two-body solver"
	@echo ""
	@echo "Configuration variables:"
	@echo "  CXX              - C++ compiler (default: g++)"
	@echo "  CXX_SYCL         - SYCL compiler (default: icpx from Intel oneAPI)"
	@echo "  BUILD_MODE       - Release or Debug (default: Release)"
	@echo "  SYCL_BACKEND     - nvidia or opencl (default: nvidia)"
	@echo ""
	@echo "Examples:"
	@echo "  make all                              # Build all main versions"
	@echo "  make all-sycl                         # Build with SYCL support"
	@echo "  make run-serial                       # Run serial version"
	@echo "  make CXX=clang++ all                  # Use clang compiler"
	@echo "  make clean && make all                # Clean rebuild"

# ============================================================================
# COMPILER CHECK
# ============================================================================

.PHONY: check-compilers

check-compilers:
	@echo "Checking available compilers..."
	@which $(CXX) > /dev/null && echo "✓ $(CXX) found" || echo "✗ $(CXX) NOT found"
	@which $(CXX_SYCL) > /dev/null && echo "✓ $(CXX_SYCL) found" || echo "✗ $(CXX_SYCL) NOT found (SYCL support disabled)"
	@which icpx > /dev/null && echo "✓ Intel oneAPI found" || echo "✗ Intel oneAPI NOT found"

# ============================================================================
# PHONY TARGETS
# ============================================================================

.PHONY: all all-sycl clean run run-serial run-openmp run-sycl run-twobody help check-compilers
