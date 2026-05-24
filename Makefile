# Makefile for N-body Problem Project
# Supports: Serial, OpenMP, and SYCL implementations
# SYCL provider: AdaptiveCpp (acpp), not Intel oneAPI/icpx
# Cross-platform: WSL/Linux

# ============================================================================
# CONFIGURATION
# ============================================================================

# Host compiler selection
CXX ?= g++

# AdaptiveCpp installation.
# If /opt/adaptivecpp/bin/acpp exists, this default works without editing PATH.
# You can override from CLI: make CXX_SYCL=acpp all-sycl
ACPP_HOME ?= /opt/adaptivecpp
CXX_SYCL ?= $(ACPP_HOME)/bin/acpp

# AdaptiveCpp targets.
# Recommended default for a full AdaptiveCpp installation:
#   generic
#
# Explicit NVIDIA + CPU example:
#   make all-sycl ACPP_TARGETS="omp.accelerated;cuda:sm_120"
#
# For RTX 5070 Laptop GPU, check compute capability with:
#   nvidia-smi --query-gpu=name,compute_cap --format=csv
ACPP_TARGETS ?= generic

# Optional runtime filtering for run-sycl:
#   make run-sycl ACPP_VISIBILITY_MASK=cuda
#   make run-sycl ACPP_VISIBILITY_MASK=omp
ACPP_VISIBILITY_MASK ?=
ACPP_DEBUG_LEVEL ?=

# Compiler flags
CXXFLAGS ?= -std=c++17 -Wall -Wextra -O2 -fPIC
CXXFLAGS_DEBUG ?= -std=c++17 -Wall -Wextra -g -O0
CXXFLAGS_OMP ?= $(CXXFLAGS) -fopenmp -DENABLE_OPENMP

# AdaptiveCpp does NOT use Intel's -fsycl flow here.
# acpp receives SYCL target selection via --acpp-targets.
CXXFLAGS_SYCL ?= -std=c++17 -Wall -Wextra -O2 -fPIC
ACPP_FLAGS ?= --acpp-targets="$(ACPP_TARGETS)"

# Tool checks
ACPP_CHECK = if ! command -v "$(CXX_SYCL)" >/dev/null 2>&1; then \
	echo "Error: AdaptiveCpp compiler not found: $(CXX_SYCL)"; \
	echo "Set CXX_SYCL=/path/to/acpp or export PATH=/opt/adaptivecpp/bin:\$$PATH"; \
	exit 127; \
fi

# Directories
COMMON_DIR = Common
NBODY_DIR = N-body-Numerical-Solution
TWOBODY_DIR = Two-body-Analytical-Solution
OBJ_DIR = obj
SYCL_OBJ_DIR = $(OBJ_DIR)/sycl
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

# Object files for host-only builds
COMMON_OBJS = $(addprefix $(OBJ_DIR)/, $(notdir $(COMMON_SRCS:.cpp=.o)))
NBODY_SERIAL_OBJ = $(OBJ_DIR)/nbody_serial.o
NBODY_OMP_OBJ = $(OBJ_DIR)/nbody_openmp.o
TWOBODY_OBJS = $(addprefix $(OBJ_DIR)/, $(notdir $(TWOBODY_SRCS:.cpp=.o)))

# Object files for SYCL build.
# Keep them separate from g++ objects so the SYCL executable is compiled/linked
# consistently through AdaptiveCpp.
COMMON_SYCL_OBJS = $(addprefix $(SYCL_OBJ_DIR)/, $(notdir $(COMMON_SRCS:.cpp=.o)))
NBODY_SYCL_OBJ = $(SYCL_OBJ_DIR)/nbody_sycl.o

# Executable names
NBODY_SERIAL_EXE = nbody_serial
NBODY_OMP_EXE = nbody_openmp
NBODY_SYCL_EXE = nbody_sycl
TWOBODY_EXE = two_body_solver

# Build mode (Debug or Release)
BUILD_MODE ?= Release

# ============================================================================
# TARGETS
# ============================================================================

.PHONY: all all-sycl clean run run-serial run-openmp run-sycl run-twobody gui gui-bg viewer visualize help \
	check-compilers check-acpp print-acpp-config benchmark benchmark-full plots \
	quick-benchmark quick-benchmark-sycl clean-benchmark clean-all setup obj

# Default target
all: setup $(NBODY_SERIAL_EXE) $(NBODY_OMP_EXE) $(TWOBODY_EXE)

# All targets including SYCL
all-sycl: all $(NBODY_SYCL_EXE)

# Create build directories
obj:
	mkdir -p $(OBJ_DIR) $(SYCL_OBJ_DIR)

setup: obj
	@mkdir -p $(OBJ_DIR) $(SYCL_OBJ_DIR) $(BUILD_DIR)

# ============================================================================
# COMMON LIBRARY OBJECTS - HOST BUILDS
# ============================================================================

$(OBJ_DIR)/body.o: $(COMMON_DIR)/src/body.cpp $(COMMON_DIR)/include/body.h | setup
	$(CXX) $(CXXFLAGS) $(COMMON_INCLUDE) -c $< -o $@

$(OBJ_DIR)/Vector3.o: $(COMMON_DIR)/src/Vector3.cpp $(COMMON_DIR)/include/vector3.h | setup
	$(CXX) $(CXXFLAGS) $(COMMON_INCLUDE) -c $< -o $@

# ============================================================================
# COMMON LIBRARY OBJECTS - SYCL BUILD
# ============================================================================

$(SYCL_OBJ_DIR)/body.o: $(COMMON_DIR)/src/body.cpp $(COMMON_DIR)/include/body.h | setup
	@$(ACPP_CHECK); $(CXX_SYCL) $(ACPP_FLAGS) $(CXXFLAGS_SYCL) $(COMMON_INCLUDE) -c $< -o $@

$(SYCL_OBJ_DIR)/Vector3.o: $(COMMON_DIR)/src/Vector3.cpp $(COMMON_DIR)/include/vector3.h | setup
	@$(ACPP_CHECK); $(CXX_SYCL) $(ACPP_FLAGS) $(CXXFLAGS_SYCL) $(COMMON_INCLUDE) -c $< -o $@

# ============================================================================
# N-BODY SERIAL VERSION
# ============================================================================

$(NBODY_SERIAL_OBJ): $(NBODY_SERIAL_SRC) $(COMMON_DIR)/include/trajectory_writer.h | setup
	$(CXX) $(CXXFLAGS) $(NBODY_INCLUDE) -c $< -o $@

$(NBODY_SERIAL_EXE): $(NBODY_SERIAL_OBJ) $(COMMON_OBJS)
	$(CXX) $(CXXFLAGS) $(NBODY_INCLUDE) $^ -o $@
	@echo "Built: $@"

# ============================================================================
# N-BODY OPENMP VERSION
# ============================================================================

$(NBODY_OMP_OBJ): $(NBODY_OMP_SRC) $(COMMON_DIR)/include/trajectory_writer.h | setup
	$(CXX) $(CXXFLAGS_OMP) $(NBODY_INCLUDE) -c $< -o $@

$(NBODY_OMP_EXE): $(NBODY_OMP_OBJ) $(COMMON_OBJS)
	$(CXX) $(CXXFLAGS_OMP) $(NBODY_INCLUDE) $^ -o $@
	@echo "Built: $@"

# ============================================================================
# N-BODY SYCL VERSION - ADAPTIVECPP
# ============================================================================

$(NBODY_SYCL_OBJ): $(NBODY_SYCL_SRC) $(COMMON_DIR)/include/trajectory_writer.h | setup
	@$(ACPP_CHECK); $(CXX_SYCL) $(ACPP_FLAGS) $(CXXFLAGS_SYCL) $(NBODY_INCLUDE) -c $< -o $@

$(NBODY_SYCL_EXE): $(NBODY_SYCL_OBJ) $(COMMON_SYCL_OBJS)
	@$(ACPP_CHECK); $(CXX_SYCL) $(ACPP_FLAGS) $(CXXFLAGS_SYCL) $(NBODY_INCLUDE) $^ -o $@
	@echo "Built SYCL version with AdaptiveCpp: $@"
	@echo "AdaptiveCpp targets: $(ACPP_TARGETS)"

# ============================================================================
# TWO-BODY ANALYTICAL SOLUTION
# ============================================================================

$(OBJ_DIR)/two_body_solver.o: $(TWOBODY_DIR)/src/two_body_solver.cpp $(TWOBODY_DIR)/include/two_body_solver.h | setup
	$(CXX) $(CXXFLAGS) $(TWOBODY_INCLUDE) -c $< -o $@

$(OBJ_DIR)/test_main.o: $(TWOBODY_DIR)/src/test_main.cpp | setup
	$(CXX) $(CXXFLAGS) $(TWOBODY_INCLUDE) -c $< -o $@

$(TWOBODY_EXE): $(OBJ_DIR)/two_body_solver.o $(OBJ_DIR)/test_main.o $(COMMON_OBJS)
	$(CXX) $(CXXFLAGS) $(TWOBODY_INCLUDE) $^ -o $@
	@echo "Built: $@"

# ============================================================================
# BENCHMARK TARGETS
# ============================================================================

benchmark: all
	@echo "Running benchmark suite..."
	@python3 benchmark.py --run --force

benchmark-full: all
	@echo "Running full benchmark suite with plots..."
	@python3 benchmark.py --force

plots:
	@echo "Generating plots from existing benchmark data..."
	@python3 benchmark.py --plot

quick-benchmark:
	@echo "Running quick benchmark suite..."
	@./run_benchmarks.sh

quick-benchmark-sycl:
	@echo "Running quick benchmark suite with SYCL..."
	@./run_benchmarks.sh --with-sycl

clean-benchmark:
	@echo "Cleaning benchmark results..."
	rm -rf benchmark_results

clean-all: clean clean-benchmark

# ============================================================================
# UTILITY TARGETS
# ============================================================================

clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(OBJ_DIR) $(BUILD_DIR)
	rm -f $(NBODY_SERIAL_EXE) $(NBODY_OMP_EXE) $(NBODY_SYCL_EXE) $(TWOBODY_EXE)
	@echo "Clean complete."

run: all
	@echo "Running N-body Serial version..."
	./$(NBODY_SERIAL_EXE)
	@echo "\nRunning N-body OpenMP version..."
	./$(NBODY_OMP_EXE)
	@echo "\nRunning Two-body solver..."
	./$(TWOBODY_EXE)

run-serial: $(NBODY_SERIAL_EXE)
	./$(NBODY_SERIAL_EXE)

run-openmp: $(NBODY_OMP_EXE)
	./$(NBODY_OMP_EXE)

run-sycl: $(NBODY_SYCL_EXE)
	ACPP_VISIBILITY_MASK="$(ACPP_VISIBILITY_MASK)" ACPP_DEBUG_LEVEL="$(ACPP_DEBUG_LEVEL)" ./$(NBODY_SYCL_EXE)

run-sycl-cuda: $(NBODY_SYCL_EXE)
	ACPP_VISIBILITY_MASK="cuda" ./$(NBODY_SYCL_EXE)

run-sycl-omp: $(NBODY_SYCL_EXE)
	ACPP_VISIBILITY_MASK="omp" ./$(NBODY_SYCL_EXE)

run-twobody: $(TWOBODY_EXE)
	./$(TWOBODY_EXE)

gui:
	python3 nbody_gui.py

gui-bg:
	nohup python3 nbody_gui.py >/tmp/nbody_gui.log 2>&1 &
	@echo "N-body GUI started in background. Log: /tmp/nbody_gui.log"

viewer visualize:
	python3 trajectory_viewer.py

print-acpp-config:
	@echo "CXX_SYCL       = $(CXX_SYCL)"
	@echo "ACPP_HOME      = $(ACPP_HOME)"
	@echo "ACPP_TARGETS   = $(ACPP_TARGETS)"
	@echo "ACPP_FLAGS     = $(ACPP_FLAGS)"
	@echo "CXXFLAGS_SYCL  = $(CXXFLAGS_SYCL)"

check-acpp:
	@$(ACPP_CHECK)
	@echo "✓ AdaptiveCpp compiler found: $(CXX_SYCL)"
	@$(CXX_SYCL) --acpp-version || true
	@echo ""
	@echo "Detected devices from a compiled SYCL executable are best checked with your test_acpp_devices program."

check-compilers:
	@echo "Checking available compilers..."
	@command -v "$(CXX)" >/dev/null 2>&1 && echo "✓ $(CXX) found" || echo "✗ $(CXX) NOT found"
	@$(ACPP_CHECK); echo "✓ $(CXX_SYCL) found"
	@echo "Note: Intel oneAPI/icpx is no longer required for the SYCL build."

help:
	@echo "N-body Problem Project Makefile"
	@echo "================================"
	@echo ""
	@echo "Available targets:"
	@echo "  all                  - Build serial, OpenMP, and two-body executables"
	@echo "  all-sycl             - Build all including SYCL version via AdaptiveCpp"
	@echo "  clean                - Remove build artifacts and executables"
	@echo "  run                  - Build and run serial, OpenMP, and two-body"
	@echo "  run-serial           - Build and run serial version"
	@echo "  run-openmp           - Build and run OpenMP version"
	@echo "  run-sycl             - Build and run SYCL version"
	@echo "  run-sycl-cuda        - Run SYCL version with only CUDA backend visible"
	@echo "  run-sycl-omp         - Run SYCL version with only OpenMP backend visible"
	@echo "  run-twobody          - Build and run two-body solver"
	@echo "  gui                  - Open the Tkinter launcher"
	@echo "  gui-bg               - Open the launcher in background and return the terminal"
	@echo "  viewer               - Open the trajectory viewer"
	@echo "  benchmark            - Run benchmark suite and save results"
	@echo "  benchmark-full       - Run benchmark suite and generate plots"
	@echo "  plots                - Generate plots from existing benchmark data"
	@echo "  quick-benchmark      - Quick benchmark runner"
	@echo "  quick-benchmark-sycl - Quick benchmark with SYCL support"
	@echo "  check-compilers      - Check host compiler and AdaptiveCpp"
	@echo "  check-acpp           - Check AdaptiveCpp compiler"
	@echo "  print-acpp-config    - Print AdaptiveCpp build variables"
	@echo ""
	@echo "Configuration variables:"
	@echo "  CXX                  - Host C++ compiler (default: g++)"
	@echo "  CXX_SYCL             - AdaptiveCpp compiler (default: /opt/adaptivecpp/bin/acpp)"
	@echo "  ACPP_HOME            - AdaptiveCpp prefix (default: /opt/adaptivecpp)"
	@echo "  ACPP_TARGETS         - AdaptiveCpp targets (default: generic)"
	@echo "  ACPP_VISIBILITY_MASK - Runtime backend filter: cuda, omp, etc."
	@echo ""
	@echo "Examples:"
	@echo "  make all"
	@echo "  make all-sycl"
	@echo "  make run-sycl"
	@echo "  make run-sycl-cuda"
	@echo "  make run-sycl-omp"
	@echo "  make all-sycl ACPP_TARGETS=generic"
	@echo "  make all-sycl ACPP_TARGETS=\"omp.accelerated;cuda:sm_120\""
	@echo "  make CXX_SYCL=acpp all-sycl"
