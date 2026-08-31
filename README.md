# Rover Autonomous Navigation

Autonomous exploration rover using ROS 2 Humble, Intel RealSense D435IF, RTAB-Map, and RPLIDAR. The target computer is a Jetson Orin Nano running Ubuntu 22.04; camera development has also been validated under Ubuntu 22.04 on WSL 2.

For the complete Windows + WSL 2 camera procedure, use [Intel RealSense D435IF on ROS 2 Humble and WSL 2](docs/d435if_wsl_ros2_setup.md). That guide is authoritative for USB forwarding, the RSUSB librealsense build, dependencies, workspace layouts, verification, and troubleshooting.

## D435IF mapping modes

- `d435if_rgbd_slam.launch.py`: validated color + aligned depth + Madgwick + EKF + RTAB-Map pipeline. This is the recommended color-mapping mode.
- `d435if_stereo_slam.launch.py`: lower-bandwidth raw infrared stereo + Madgwick + RTAB-Map fallback.

The RGB-D launcher rejects stationary graph jitter by default and does not fuse magnetometer-free IMU yaw or Z angular velocity.

## First-time setup

```bash
./install_ros2.sh

source /opt/ros/humble/setup.bash
sudo apt update
sudo apt install -y \
  ros-humble-imu-filter-madgwick \
  ros-humble-rmw-cyclonedds-cpp \
  ros-humble-robot-localization \
  ros-humble-rtabmap-ros \
  ros-humble-rqt-image-view \
  ros-humble-tf2-tools \
  python3-colcon-common-extensions \
  python3-rosdep

git submodule update --init --recursive
rosdep install --from-paths src --ignore-src -r -y --skip-keys librealsense2
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

Under WSL, do not use a default native librealsense source build. Follow the linked guide to build the exact ROS-matched SDK version with `FORCE_RSUSB_BACKEND=ON` and install it under `/usr/local`.

## Every ROS terminal under WSL

```bash
source /opt/ros/humble/setup.bash
source ~/rosbot/install/setup.bash

export LD_LIBRARY_PATH="/usr/local/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
unset ROS_LOCALHOST_ONLY
unset ROS_DISCOVERY_SERVER
unset FASTRTPS_DEFAULT_PROFILES_FILE
unset CYCLONEDDS_URI
```

Every communicating process must use the same ROS domain and middleware.

## Validated RGB-D launch

Start a new map:

```bash
ros2 launch rover_slam d435if_rgbd_slam.launch.py \
  rtabmap_viz:=true \
  new_map:=true
```

Reopen and extend the existing map:

```bash
ros2 launch rover_slam d435if_rgbd_slam.launch.py \
  rtabmap_viz:=true \
  new_map:=false \
  linear_update:=0.1 \
  angular_update:=0.1
```

## Hardware

- Jetson Orin Nano
- Intel RealSense D435IF
- RPLIDAR; select the model-specific launch file and baud rate
- Rover chassis and wheel encoders

## Workspace packages

```text
src/
├── realsense-ros/       RealSense ROS 2 driver
├── rplidar_ros/         RPLIDAR ROS 2 driver
├── rover_description/   Robot model and sensor transforms
├── rover_odometry/      State-estimation configuration
└── rover_slam/          RTAB-Map launchers and configuration
```
