#!/bin/bash
# setup.sh — Run once after cloning to initialize the workspace

set -e

echo "Installing rosdep dependencies..."
sudo rosdep init || true   # 'true' prevents error if already initialized
rosdep update
rosdep install --from-paths src --ignore-src -r -y

echo "Building workspace..."
colcon build --symlink-install

echo "Done! Run: source install/setup.bash"