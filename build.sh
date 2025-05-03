#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

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
west zephyr-export

# --- Clean and build the two halves ---
echo "Cleaning build directory..."
rm -rf build_right/
echo "Building..."
west build -b "nice_nano_v2" -d build_right/ -s zmk/app -- \
  -DZMK_CONFIG="$PWD/config" \
  -DSHIELD="kyria_rev3_right" \
  -DZMK_EXTRA_MODULES="$PWD/cirque-input-module"

rm -rf build_left/
echo "Building..."
west build -b "nice_nano_v2" -d build_left/ -s zmk/app -- \
  -DZMK_CONFIG="$PWD/config" \
  -DSHIELD="kyria_rev3_left dongle_display" \
  

# --- Copy output UF2 files ---
echo "Creating output directory..."
mkdir -p output

# Copy the UF2 files from each build, renaming them to avoid overwriting
echo "Copying UF2 files to output directory..."
cp build_right/zephyr/zmk.uf2 output/zmk_right.uf2
cp build_left/zephyr/zmk.uf2 output/zmk_left.uf2

echo "Build and copy operations complete."
