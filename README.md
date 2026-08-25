# Rover Autonomous Navigation

Autonomous exploration rover using ROS 2 Humble, Intel RealSense D435if, and RPLIDAR.
Designed to run on Jetson Orin Nano (Ubuntu 22.04). Development mimicked on Ubuntu 22.04 laptops.

For a complete Windows 11 + WSL 2 camera and stereo/IMU mapping setup, see
[Intel RealSense D435IF on ROS 2 Humble and WSL 2](docs/d435if_wsl_ros2_setup.md).

The repository provides two D435IF mapping modes:

- `d435if_stereo_slam.launch.py`: raw infrared stereo plus IMU.
- `d435if_rgbd_slam.launch.py`: power-conscious, wiki-derived RGB-D plus IMU and EKF.

## Hardware
- Jetson Orin Nano
- Intel RealSense D435if (RGB-D + IMU)
- RPLIDAR (model: A1/A2/A3 — update this)
- Rover chassis

## Stack
- ROS 2 Humble
- RTAB-Map (SLAM)
- Nav2 (navigation)
- explore_lite (autonomous frontier exploration)

## First Time Setup (Per Machine)

### 1. Install ROS 2 Humble
```bash
./install_ros2.sh
```

### 2. Install Intel RealSense SDK
Build from source (recommended for reliability):
```bash
git clone https://github.com/IntelRealSense/librealsense.git ~/librealsense
cd ~/librealsense
sudo apt install -y cmake build-essential libusb-1.0-0-dev libssl-dev libudev-dev pkg-config libgtk-3-dev
mkdir build && cd build
cmake ../ -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
sudo make install
```

### 3. Clone the Repo
```bash
git clone --recurse-submodules <your-repo-url>
cd your-repo
```

### 4. Build the Workspace
```bash
./setup.sh
```

## Every New Terminal
```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## Workspace Structure
src/
├── realsense-ros/       # RealSense ROS 2 driver (submodule)
├── rplidar_ros/         # RPLIDAR ROS 2 driver (submodule)
├── rover_description/   # URDF robot model (Phase 2)
├── rover_bringup/       # Launch files (Phase 7)
└── rover_navigation/    # Custom behavior (Phase 7)
build/                   # ignored by git
install/                 # ignored by git
log/                     # ignored by git
