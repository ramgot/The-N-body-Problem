#!/bin/bash
# Quick benchmark runner script
# Usage: ./run_benchmarks.sh [options]

set -e  # Exit on any error

echo "========================================"
echo "N-Body Problem Benchmark Suite"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "Makefile" ] || [ ! -f "benchmark.py" ]; then
    echo -e "${RED}Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Parse command line arguments
FORCE=""
PLOT_ONLY=""
BUILD_SYCL=""
DEVICE="auto"

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE="--force"
            shift
            ;;
        --plot-only)
            PLOT_ONLY="yes"
            shift
            ;;
        --with-sycl)
            BUILD_SYCL="yes"
            shift
            ;;
        --device)
            if [ -z "${2:-}" ]; then
                echo -e "${RED}Error: --device requires auto, cpu, or gpu${NC}"
                exit 1
            fi
            DEVICE="$2"
            shift 2
            ;;
        --device=*)
            DEVICE="${1#*=}"
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --force      Force re-run benchmarks (overwrite existing results)"
            echo "  --plot-only  Only generate plots from existing data"
            echo "  --with-sycl  Include SYCL version in benchmarks"
            echo "  --device DEV Select SYCL device: auto, cpu, or gpu"
            echo "  --help       Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Run full benchmark suite"
            echo "  $0 --force           # Force re-run all benchmarks"
            echo "  $0 --plot-only       # Generate plots only"
            echo "  $0 --with-sycl       # Include SYCL benchmarks"
            echo "  $0 --with-sycl --device gpu"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

if [[ "$DEVICE" != "auto" && "$DEVICE" != "cpu" && "$DEVICE" != "gpu" ]]; then
    echo -e "${RED}Error: --device must be auto, cpu, or gpu${NC}"
    exit 1
fi

# Check dependencies
echo -e "${YELLOW}Checking dependencies...${NC}"

# Check Python and matplotlib
if ! python3 -c "import matplotlib, sys; sys.exit(0 if matplotlib.__version__ else 1)" 2>/dev/null; then
    echo -e "${RED}Error: Python 3 with matplotlib is required${NC}"
    echo "Install with: pip install matplotlib numpy"
    exit 1
fi
echo -e "${GREEN}✓ Python 3 with matplotlib found${NC}"

# Check compilers
if ! command -v g++ &> /dev/null; then
    echo -e "${RED}Error: g++ compiler not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ g++ compiler found${NC}"

# Check OpenMP support
if ! echo | g++ -fopenmp -dM -E - | grep -q "_OPENMP"; then
    echo -e "${YELLOW}Warning: OpenMP support not detected in g++${NC}"
else
    echo -e "${GREEN}✓ OpenMP support detected${NC}"
fi

# Check SYCL if requested
if [ "$BUILD_SYCL" = "yes" ]; then
    CXX_SYCL="${CXX_SYCL:-/opt/adaptivecpp/bin/acpp}"
    if ! command -v "$CXX_SYCL" &> /dev/null; then
        echo -e "${RED}Error: AdaptiveCpp compiler not found: $CXX_SYCL${NC}"
        echo "Set CXX_SYCL=/path/to/acpp or export PATH=/opt/adaptivecpp/bin:\$PATH"
        exit 1
    fi
    echo -e "${GREEN}✓ AdaptiveCpp compiler found: $CXX_SYCL${NC}"
fi

echo ""

# Build phase
if [ "$PLOT_ONLY" != "yes" ]; then
    echo -e "${YELLOW}Building executables...${NC}"

    if [ "$BUILD_SYCL" = "yes" ]; then
        make clean && make all-sycl
    else
        make clean && make all
    fi

    if [ $? -ne 0 ]; then
        echo -e "${RED}Build failed!${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Build completed successfully${NC}"
    echo ""
fi

# Benchmark phase
echo -e "${YELLOW}Running benchmarks...${NC}"

if [ "$PLOT_ONLY" = "yes" ]; then
    if [ ! -f "benchmark_results/benchmark_results.csv" ]; then
        echo -e "${RED}Error: No benchmark data found. Run benchmarks first without --plot-only${NC}"
        exit 1
    fi
    python3 benchmark.py --plot
else
    python3 benchmark.py --run $FORCE --device "$DEVICE"
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}Benchmarking failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Benchmarking completed${NC}"
echo ""

# Results
echo "========================================"
echo "Benchmark Results Summary"
echo "========================================"

if [ -d "benchmark_results" ]; then
    echo "Results saved to: benchmark_results/"
    echo "CSV data: benchmark_results/benchmark_results.csv"
    echo "Plots: benchmark_results/plots/"

    # Show summary of results
    if [ -f "benchmark_results/benchmark_results.csv" ]; then
        echo ""
        echo "Quick summary:"
        python3 -c "
import csv
import os
csv_path = 'benchmark_results/benchmark_results.csv'
if os.path.exists(csv_path):
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if rows:
            methods = set(r['method'] for r in rows)
            n_values = sorted(set(int(r['n_bodies']) for r in rows))
            print(f'Methods tested: {sorted(methods)}')
            print(f'N values: {n_values}')
            print(f'Total runs: {len(rows)}')
        else:
            print('No results found')
"
    fi
else
    echo -e "${RED}No results directory found${NC}"
fi

echo ""
echo -e "${GREEN}All done! Check benchmark_results/ for detailed results.${NC}"
