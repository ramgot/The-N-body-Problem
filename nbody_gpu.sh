#!/bin/bash
# GPU wrapper script for N-body SYCL simulation
# Automatically activates Intel oneAPI and runs SYCL executable
# Usage: ./nbody_gpu.sh <N_bodies> <dt> <t_max> [scenario]

set -e

# Check arguments
if [ $# -lt 3 ]; then
    echo "Usage: $0 <N_bodies> <dt> <t_max> [scenario]"
    echo ""
    echo "Examples:"
    echo "  $0 100 3600 21600                  # 100 bodies, 6 hours"
    echo "  $0 1000 3600 86400                 # 1000 bodies, 1 day"
    echo "  $0 10 3600 86400 solar-system      # Solar system"
    echo "  $0 3 3600 86400 sun-earth-moon     # Sun-Earth-Moon"
    exit 1
fi

# Store arguments
N_BODIES=$1
DT=$2
T_MAX=$3
SCENARIO=${4:-auto}

# Check if executable exists
if [ ! -f "nbody_sycl" ]; then
    echo "Error: nbody_sycl executable not found"
    echo "Please build it first with: make all-sycl"
    exit 1
fi

# Activate Intel oneAPI
source /opt/intel/oneapi/setvars.sh > /dev/null 2>&1 || {
    echo "Warning: Intel oneAPI not found at /opt/intel/oneapi/setvars.sh"
    echo "Make sure Intel oneAPI is installed and accessible"
    exit 1
}

# Set ONEAPI device selector for Level Zero backend
export ONEAPI_DEVICE_SELECTOR=level_zero

# Run the simulation
echo "N-Body Simulation (SYCL Velocity Verlet)"
echo "Number of bodies: $N_BODIES"
echo "Time step: $DT s"
echo "Total time: $T_MAX s"
echo "Scenario: $SCENARIO"
echo "Device: GPU (Level Zero backend)"
echo ""

./nbody_sycl "$N_BODIES" "$DT" "$T_MAX" "$SCENARIO"
