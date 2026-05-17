#!/bin/bash
# GPU wrapper script for N-body SYCL simulation
# Runs the AdaptiveCpp-built SYCL executable
# Usage: ./nbody_gpu.sh <N_bodies> <dt> <t_max> [scenario] [--device gpu|cpu|auto]

set -e

# Check arguments
if [ $# -lt 3 ]; then
    echo "Usage: $0 <N_bodies> <dt> <t_max> [scenario] [--device gpu|cpu|auto]"
    echo ""
    echo "Examples:"
    echo "  $0 100 3600 21600                  # 100 bodies, 6 hours"
    echo "  $0 1000 3600 86400                 # 1000 bodies, 1 day"
    echo "  $0 10 3600 86400 solar-system      # Solar system"
    echo "  $0 3 3600 86400 sun-earth-moon     # Sun-Earth-Moon"
    echo "  $0 1000 3600 86400 random --device gpu"
    exit 1
fi

# Store arguments
N_BODIES=$1
DT=$2
T_MAX=$3
SCENARIO=${4:-auto}
DEVICE="gpu"
shift 3
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then
    SCENARIO="$1"
    shift
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        --device)
            if [ -z "${2:-}" ]; then
                echo "Error: --device requires gpu, cpu, or auto"
                exit 1
            fi
            DEVICE="$2"
            shift 2
            ;;
        --device=*)
            DEVICE="${1#*=}"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 <N_bodies> <dt> <t_max> [scenario] [--device gpu|cpu|auto]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [[ "$DEVICE" != "gpu" && "$DEVICE" != "cpu" && "$DEVICE" != "auto" ]]; then
    echo "Error: --device must be gpu, cpu, or auto"
    exit 1
fi

# Check if executable exists
if [ ! -f "nbody_sycl" ]; then
    echo "Error: nbody_sycl executable not found"
    echo "Please build it first with: make all-sycl"
    exit 1
fi

# Run the simulation
echo "N-Body Simulation (SYCL Velocity Verlet)"
echo "Number of bodies: $N_BODIES"
echo "Time step: $DT s"
echo "Total time: $T_MAX s"
echo "Scenario: $SCENARIO"
echo "Requested device: $DEVICE"
echo ""

./nbody_sycl "$N_BODIES" "$DT" "$T_MAX" "$SCENARIO" --device "$DEVICE"
