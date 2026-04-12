# Makefile for the N-body project
# Main workflow is intended for GNU Make inside Linux/WSL.

CXX = g++
CXX_SYCL = icpx

BUILD_MODE ?= Release
SYCL_BACKEND ?= nvidia

ifeq ($(BUILD_MODE),Debug)
CXXFLAGS = -std=c++17 -Wall -Wextra -g -O0 -fPIC
else ifeq ($(BUILD_MODE),Release)
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -fPIC
else
$(error Unsupported BUILD_MODE '$(BUILD_MODE)'. Use Release or Debug)
endif

CXXFLAGS_OMP = $(CXXFLAGS) -fopenmp -DENABLE_OPENMP
CXXFLAGS_SYCL = $(CXXFLAGS) -fsycl

COMMON_DIR = Common
NBODY_DIR = The\ N-body\ Problem\ Numerical\ Solution
TWOBODY_DIR = The\ Two-body\ Problem\ Analytical\ Solution
OBJ_DIR = obj
BUILD_DIR = build

COMMON_INCLUDE = -I$(COMMON_DIR)/include
NBODY_INCLUDE = -I$(NBODY_DIR)/include $(COMMON_INCLUDE)
TWOBODY_INCLUDE = -I$(TWOBODY_DIR)/include $(COMMON_INCLUDE)

COMMON_BODY_SRC = $(COMMON_DIR)/src/body.cpp
COMMON_VECTOR_SRC = $(COMMON_DIR)/src/Vector3.cpp
NBODY_SERIAL_SRC = $(NBODY_DIR)/src/nbody_serial.cpp
NBODY_OMP_SRC = $(NBODY_DIR)/src/nbody_openmp.cpp
NBODY_SYCL_SRC = $(NBODY_DIR)/src/nbody_sycl.cpp
TWOBODY_SOLVER_SRC = $(TWOBODY_DIR)/src/two_body_solver.cpp
TWOBODY_MAIN_SRC = $(TWOBODY_DIR)/src/test_main.cpp

COMMON_OBJS = $(OBJ_DIR)/body.o $(OBJ_DIR)/Vector3.o
NBODY_SERIAL_OBJ = $(OBJ_DIR)/nbody_serial.o
NBODY_OMP_OBJ = $(OBJ_DIR)/nbody_openmp.o
NBODY_SYCL_OBJ = $(OBJ_DIR)/nbody_sycl.o
TWOBODY_OBJS = $(OBJ_DIR)/two_body_solver.o $(OBJ_DIR)/test_main.o

NBODY_SERIAL_EXE = nbody_serial
NBODY_OMP_EXE = nbody_openmp
NBODY_SYCL_EXE = nbody_sycl
TWOBODY_EXE = two_body_solver

.DEFAULT_GOAL := all

.PHONY: all all-sycl benchmark benchmark-full plots quick-benchmark quick-benchmark-sycl
.PHONY: clean clean-all clean-benchmark run run-serial run-openmp run-sycl run-twobody
.PHONY: help setup check-compilers

all: setup $(NBODY_SERIAL_EXE) $(NBODY_OMP_EXE) $(TWOBODY_EXE)

all-sycl: all
	@if command -v $(CXX_SYCL) >/dev/null 2>&1; then \
		$(MAKE) --no-print-directory $(NBODY_SYCL_EXE) BUILD_MODE="$(BUILD_MODE)" CXX="$(CXX)" CXX_SYCL="$(CXX_SYCL)"; \
	else \
		echo "Skipping SYCL build: $(CXX_SYCL) not found."; \
	fi

setup: $(OBJ_DIR) $(BUILD_DIR)

$(OBJ_DIR):
	@mkdir -p "$@"

$(BUILD_DIR):
	@mkdir -p "$@"

$(OBJ_DIR)/body.o: $(COMMON_BODY_SRC) $(COMMON_DIR)/include/body.h $(COMMON_DIR)/include/common.h $(COMMON_DIR)/include/vector3.h | $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) $(COMMON_INCLUDE) -c "$<" -o "$@"

$(OBJ_DIR)/Vector3.o: $(COMMON_VECTOR_SRC) $(COMMON_DIR)/include/vector3.h | $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) $(COMMON_INCLUDE) -c "$<" -o "$@"

$(NBODY_SERIAL_OBJ): $(NBODY_SERIAL_SRC) $(COMMON_DIR)/include/body.h $(COMMON_DIR)/include/common.h $(COMMON_DIR)/include/vector3.h | $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) $(NBODY_INCLUDE) -c "$<" -o "$@"

$(NBODY_SERIAL_EXE): $(NBODY_SERIAL_OBJ) $(COMMON_OBJS)
	$(CXX) $(CXXFLAGS) $(NBODY_INCLUDE) $^ -o "$@"
	@echo "Built: $@"

$(NBODY_OMP_OBJ): $(NBODY_OMP_SRC) $(COMMON_DIR)/include/body.h $(COMMON_DIR)/include/common.h $(COMMON_DIR)/include/vector3.h | $(OBJ_DIR)
	$(CXX) $(CXXFLAGS_OMP) $(NBODY_INCLUDE) -c "$<" -o "$@"

$(NBODY_OMP_EXE): $(NBODY_OMP_OBJ) $(COMMON_OBJS)
	$(CXX) $(CXXFLAGS_OMP) $(NBODY_INCLUDE) $^ -o "$@"
	@echo "Built: $@"

$(NBODY_SYCL_OBJ): $(NBODY_SYCL_SRC) $(COMMON_DIR)/include/body.h $(COMMON_DIR)/include/common.h $(COMMON_DIR)/include/vector3.h | $(OBJ_DIR)
	$(CXX_SYCL) $(CXXFLAGS_SYCL) $(NBODY_INCLUDE) -c "$<" -o "$@"

$(NBODY_SYCL_EXE): $(NBODY_SYCL_OBJ) $(COMMON_OBJS)
	$(CXX_SYCL) $(CXXFLAGS_SYCL) $(NBODY_INCLUDE) $^ -o "$@"
	@echo "Built SYCL version: $@"

$(OBJ_DIR)/two_body_solver.o: $(TWOBODY_SOLVER_SRC) $(TWOBODY_DIR)/include/two_body_solver.h $(COMMON_DIR)/include/body.h $(COMMON_DIR)/include/common.h $(COMMON_DIR)/include/vector3.h | $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) $(TWOBODY_INCLUDE) -c "$<" -o "$@"

$(OBJ_DIR)/test_main.o: $(TWOBODY_MAIN_SRC) $(TWOBODY_DIR)/include/two_body_solver.h $(COMMON_DIR)/include/body.h $(COMMON_DIR)/include/common.h $(COMMON_DIR)/include/vector3.h | $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) $(TWOBODY_INCLUDE) -c "$<" -o "$@"

$(TWOBODY_EXE): $(TWOBODY_OBJS) $(COMMON_OBJS)
	$(CXX) $(CXXFLAGS) $(TWOBODY_INCLUDE) $^ -o "$@"
	@echo "Built: $@"

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
	@rm -rf "benchmark_results"

clean-all: clean clean-benchmark

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf "$(OBJ_DIR)" "$(BUILD_DIR)"
	@rm -f "$(NBODY_SERIAL_EXE)" "$(NBODY_OMP_EXE)" "$(NBODY_SYCL_EXE)" "$(TWOBODY_EXE)"
	@echo "Clean complete."

run: all
	@echo "Running N-body Serial version..."
	@./$(NBODY_SERIAL_EXE)
	@echo ""
	@echo "Running N-body OpenMP version..."
	@./$(NBODY_OMP_EXE)
	@echo ""
	@echo "Running Two-body solver..."
	@./$(TWOBODY_EXE)

run-serial: $(NBODY_SERIAL_EXE)
	@./$(NBODY_SERIAL_EXE)

run-openmp: $(NBODY_OMP_EXE)
	@./$(NBODY_OMP_EXE)

run-sycl: $(NBODY_SYCL_EXE)
	@./$(NBODY_SYCL_EXE)

run-twobody: $(TWOBODY_EXE)
	@./$(TWOBODY_EXE)

help:
	@echo "N-body Problem Project Makefile"
	@echo "==============================="
	@echo ""
	@echo "Available targets:"
	@echo "  all                   Build serial, OpenMP and two-body executables"
	@echo "  all-sycl              Build the main targets and try to add the SYCL binary"
	@echo "  clean                 Remove build artifacts and executables"
	@echo "  clean-all             Remove build artifacts and benchmark results"
	@echo "  run                   Build and run all main executables"
	@echo "  run-serial            Build and run the serial N-body executable"
	@echo "  run-openmp            Build and run the OpenMP N-body executable"
	@echo "  run-sycl              Build and run the SYCL N-body executable"
	@echo "  run-twobody           Build and run the analytical two-body solver"
	@echo "  benchmark             Run the benchmark suite without plots"
	@echo "  benchmark-full        Run the benchmark suite and build plots"
	@echo "  plots                 Build plots from existing benchmark data"
	@echo "  quick-benchmark       Run the helper benchmark shell script"
	@echo "  quick-benchmark-sycl  Run the helper benchmark shell script with SYCL"
	@echo "  check-compilers       Check whether g++ and icpx are available"
	@echo ""
	@echo "Variables:"
	@echo "  BUILD_MODE            Release (default) or Debug"
	@echo "  CXX                   C++ compiler for CPU targets (default: g++)"
	@echo "  CXX_SYCL              SYCL compiler (default: icpx)"
	@echo ""
	@echo "Examples:"
	@echo "  make all"
	@echo "  make BUILD_MODE=Debug all"
	@echo "  make all-sycl"
	@echo "  make run-openmp"

check-compilers:
	@echo "Checking available compilers..."
	@command -v $(CXX) >/dev/null 2>&1 && echo "[OK] $(CXX) found" || echo "[MISSING] $(CXX) NOT found"
	@command -v $(CXX_SYCL) >/dev/null 2>&1 && echo "[OK] $(CXX_SYCL) found" || echo "[MISSING] $(CXX_SYCL) NOT found"
