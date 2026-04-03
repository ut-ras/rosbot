#!/bin/bash
# setup.sh — Run after cloning to build the workspace
set -e

# Check ROS 2 is installed
if [ ! -f /opt/ros/humble/setup.bash ]; then
  echo "ERROR: ROS 2 Humble not found. Run ./install_ros2.sh first."
  exit 1
fi

source /opt/ros/humble/setup.bash

echo "Installing dependencies..."
rosdep install --from-paths src --ignore-src -r -y

echo "Building workspace..."
colcon build --symlink-install

echo "Done! Now run: source install/setup.bash"