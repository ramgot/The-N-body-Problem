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
NBODY_DIR = N-body-Numerical-Solution
TWOBODY_DIR = Two-body-Analytical-Solution
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

# Create obj directory
obj:
	mkdir -p obj

# Setup build directories
setup: obj
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
# BENCHMARK TARGETS
# ============================================================================

# Run benchmark suite
benchmark: all
	@echo "Running benchmark suite..."
	@python3 benchmark.py --run --force

# Run benchmark and generate plots
benchmark-full: all
	@echo "Running full benchmark suite with plots..."
	@python3 benchmark.py --force

# Run benchmark plots only (if CSV exists)
plots:
	@echo "Generating plots from existing benchmark data..."
	@python3 benchmark.py --plot

# Quick benchmark runner (uses shell script)
quick-benchmark:
	@echo "Running quick benchmark suite..."
	@./run_benchmarks.sh

# Quick benchmark with SYCL
quick-benchmark-sycl:
	@echo "Running quick benchmark suite with SYCL..."
	@./run_benchmarks.sh --with-sycl

# Clean benchmark results
clean-benchmark:
	@echo "Cleaning benchmark results..."
	rm -rf benchmark_results

# Full clean including benchmarks
clean-all: clean clean-benchmark

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
	@bash -c 'source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; ./$(NBODY_SYCL_EXE)'

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
	@echo "  benchmark        - Run benchmark suite and save results"
	@echo "  benchmark-full   - Run benchmark suite and generate plots"
	@echo "  plots            - Generate plots from existing benchmark data"
	@echo "  quick-benchmark  - Quick benchmark runner (build + run + plot)"
	@echo "  quick-benchmark-sycl - Quick benchmark with SYCL support"
	@echo "  clean-benchmark  - Remove benchmark results"
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
	@echo "  make benchmark-full                   # Run full benchmark with plots"
	@echo "  make quick-benchmark                  # Quick automated benchmark"
	@echo "  make quick-benchmark-sycl             # Quick benchmark with SYCL"
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

.PHONY: all all-sycl clean run run-serial run-openmp run-sycl run-twobody help check-compilers benchmark benchmark-full plots quick-benchmark quick-benchmark-sycl clean-benchmark clean-all setup
