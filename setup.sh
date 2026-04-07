cat > ~/your-repo/setup.sh << 'EOF'
#!/bin/bash
# setup.sh — Run after cloning to build the workspace
set -e

# Check ROS 2 is installed
if [ ! -f /opt/ros/humble/setup.bash ]; then
  echo "ERROR: ROS 2 Humble not found. Run ./install_ros2.sh first."
  exit 1
fi

source /opt/ros/humble/setup.bash

echo "Pulling submodules..."
git submodule update --init --recursive

echo "Installing ROS 2 dependencies..."
rosdep install --from-paths src --ignore-src -r -y

echo "Building workspace..."
colcon build --symlink-install

echo ""
echo "Done! Run this in every new terminal:"
echo "  source install/setup.bash"
EOF

chmod +x setup.sh