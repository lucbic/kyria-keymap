#!/bin/bash
# Debug build script for ZMK keyboard firmware
# This script includes additional checks and verbose output

# Enable command echo and exit on error
set -ex

# --- Check prerequisites ---
echo "Checking prerequisites..."

# Check for python3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 is not installed or not in PATH"
    echo "Please install Python 3.x"
    exit 1
fi

# Check for homebrew installation
if ! command -v brew &> /dev/null; then
    echo "ERROR: Homebrew is not installed or not in PATH"
    echo "Please install Homebrew: https://brew.sh/"
    exit 1
fi

# Check for ARM toolchain
if ! command -v arm-none-eabi-gcc &> /dev/null; then
    echo "ERROR: arm-none-eabi-gcc not found"
    echo "Installing ARM toolchain..."
    brew install armmbed/formulae/arm-none-eabi-gcc
fi

# Check for required build tools
for tool in cmake ninja dtc; do
    if ! command -v $tool &> /dev/null; then
        echo "Installing $tool..."
        brew install $tool
    fi
done

# Print system information
echo "=== System Information ==="
echo "OS: $(uname -a)"
echo "Python: $(python3 --version)"
echo "ARM GCC: $(arm-none-eabi-gcc --version | head -n 1)"
echo "CMAKE: $(cmake --version | head -n 1)"
echo "Ninja: $(ninja --version)"
echo "Device Tree Compiler: $(dtc --version)"
echo "==========================="

# --- Setup virtual environment ---
# Create the virtual environment directory "env" if it doesn't exist
if [ ! -d "env" ]; then
    echo "Creating virtual environment in ./env ..."
    python3 -m venv env
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source env/bin/activate

# Install (or upgrade) west if needed
echo "Installing/upgrading west..."
pip install --upgrade west
pip install pyelftools

# Add protobuf dependencies
echo "Installing protobuf dependencies..."
pip install protobuf grpcio-tools

# --- Initialize and update west ---
# Only run 'west init' if the repository is not already initialized.
# (This creates the .west directory)
if [ ! -d ".west" ]; then
    echo "Initializing west..."
    west init -l ./config
fi

echo "Updating west repositories..."
west update

# Export Zephyr related environment variables
echo "Setting up build environment..."
export ZEPHYR_TOOLCHAIN_VARIANT=gnuarmemb
export GNUARMEMB_TOOLCHAIN_PATH=/opt/homebrew

# Export the Zephyr package for CMake
echo "Exporting Zephyr package..."
west zephyr-export

# Print current environment settings
echo "=== Build Environment Variables ==="
echo "ZEPHYR_TOOLCHAIN_VARIANT: $ZEPHYR_TOOLCHAIN_VARIANT"
echo "GNUARMEMB_TOOLCHAIN_PATH: $GNUARMEMB_TOOLCHAIN_PATH"
echo "PATH: $PATH"
echo "=================================="

# --- Clean and build the two halves ---
echo "Cleaning build directory..."
rm -rf build_right/
echo "Building right half..."
west build -b "nice_nano_v2" -d build_right/ -s zmk/app -S zmk-usb-logging -S cdc-acm-console -- \
  -DZMK_CONFIG="$PWD/config" \
  -DSHIELD="kyria_rev3_right" \
  -DZMK_EXTRA_MODULES="$PWD/cirque-input-module"

echo "Right half build complete."

rm -rf build_left/
echo "Building left half..."
west build -b "nice_nano_v2" -d build_left/ -s zmk/app -- \
  -DZMK_CONFIG="$PWD/config" \
  -DSHIELD="kyria_rev3_left dongle_display"

echo "Left half build complete."

# --- Copy output UF2 files ---
echo "Creating output directory..."
mkdir -p output

# Copy the UF2 files from each build, renaming them to avoid overwriting
echo "Copying UF2 files to output directory..."
cp build_right/zephyr/zmk.uf2 output/zmk_right.uf2
cp build_left/zephyr/zmk.uf2 output/zmk_left.uf2

# Print file sizes for verification
echo "=== Output File Information ==="
ls -lh output/
echo "============================="

echo "Build and copy operations complete." 