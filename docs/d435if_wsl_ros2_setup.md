# Intel RealSense D435IF on ROS 2 Humble and WSL 2

This guide sets up an Intel RealSense D435IF on a Windows computer running Ubuntu 22.04 under WSL 2. It covers USB forwarding, a WSL-compatible librealsense build, the ROS 2 camera wrapper, infrared stereo odometry, IMU orientation filtering, RTAB-Map, optional RGB streaming, verification, and recovery procedures.

The tested mapping pipeline is:

```text
D435IF infrared stereo ──> RTAB-Map stereo odometry ──> RTAB-Map
          D435IF IMU ──> Madgwick orientation ────────────┘
          D435IF RGB ──> independent ROS image topic
```

> [!IMPORTANT]
> WSL 2 does not receive physical USB devices directly. The camera must be attached to WSL with `usbipd-win` after Windows, WSL, or the camera restarts. Native Ubuntu on the robot does not require the USB/IP steps.

## Contents

- [Requirements](#requirements)
- [1. Install WSL 2 and Ubuntu 22.04](#1-install-wsl-2-and-ubuntu-2204)
- [2. Install usbipd-win](#2-install-usbipd-win)
- [3. Attach the D435IF to WSL](#3-attach-the-d435if-to-wsl)
- [4. Install ROS 2 and clone this repository](#4-install-ros-2-and-clone-this-repository)
- [5. Install mapping dependencies](#5-install-mapping-dependencies)
- [6. Build a WSL-compatible librealsense](#6-build-a-wsl-compatible-librealsense)
- [7. Build the ROS workspace](#7-build-the-ros-workspace)
- [8. Verify the SDK and camera](#8-verify-the-sdk-and-camera)
- [How the mapping algorithm works](#how-the-mapping-algorithm-works)
- [Implementation roadmap](#implementation-roadmap)
- [9. Start the complete stereo, IMU, RGB, and RTAB-Map stack](#9-start-the-complete-stereo-imu-rgb-and-rtab-map-stack)
- [10. Expected topics and rates](#10-expected-topics-and-rates)
- [11. Saving and reopening a map](#11-saving-and-reopening-a-map)
- [12. RGB behavior](#12-rgb-behavior)
- [Troubleshooting](#troubleshooting)

## Requirements

- Windows 10 or Windows 11 with WSL 2 support
- Ubuntu 22.04 under WSL 2
- Intel RealSense D435IF
- A direct USB 3 port and USB 3 data cable
- ROS 2 Humble
- Internet access during installation
- Windows RealSense Viewer, recommended for native camera and firmware testing

Avoid USB hubs, docks, monitor USB ports, extension cables, and front-panel desktop ports until the setup is known to work.

## 1. Install WSL 2 and Ubuntu 22.04

Run from an Administrator PowerShell:

```powershell
wsl --install -d Ubuntu-22.04
```

Restart Windows if requested. Open Ubuntu and finish creating the Linux user.

Confirm the distribution uses WSL 2:

```powershell
wsl --list --verbose
```

The `VERSION` column should show `2` for Ubuntu 22.04.

## 2. Install usbipd-win

Try installing from PowerShell:

```powershell
winget install --interactive --exact dorssel.usbipd-win
```

If `winget` is unavailable or fails, download and run the current `.msi` installer from the [usbipd-win releases page](https://github.com/dorssel/usbipd-win/releases).

Restart PowerShell after installation, then verify:

```powershell
usbipd --version
usbipd list
```

Microsoft's current USB attachment instructions are available in [Connect USB devices under WSL](https://learn.microsoft.com/windows/wsl/connect-usb).

## 3. Attach the D435IF to WSL

Keep an Ubuntu terminal open. In an Administrator PowerShell, list USB devices:

```powershell
usbipd list
```

Find the `Intel(R) RealSense(TM) Depth Camera 435if` entry and note its `BUSID`, such as `2-1`.

Share the device once:

```powershell
usbipd bind --busid <BUSID>
```

Attach it to WSL:

```powershell
usbipd attach --wsl --busid <BUSID>
```

The attach command must normally be repeated after unplugging the camera, restarting WSL, resetting the device, or restarting Windows. Run `usbipd list` again because the bus ID can change.

Inside Ubuntu, install USB inspection tools and verify the camera:

```bash
sudo apt update
sudo apt install -y usbutils
lsusb | grep 8086
lsusb -t
```

Expected output includes product ID `8086:0b3a` and a `5000M` link:

```text
Intel Corp. Intel(R) RealSense(TM) Depth Camera 435if
Driver=vhci_hcd/... 5000M
```

`5000M` confirms that the camera is forwarded as a SuperSpeed USB device. `480M` indicates USB 2 and should be corrected before continuing.

## 4. Install ROS 2 and clone this repository

Clone into a directory that does not already contain an extracted copy of the project:

```bash
cd ~
git clone --recurse-submodules https://github.com/ut-ras/rosbot.git
cd ~/rosbot
```

Verify that this is the repository root:

```bash
pwd
test -d .git && echo "Git checkout found"
test -d src && echo "Source directory found"
```

If `.git` or `src` is missing, stop and locate the actual checkout before running `git submodule` or `rosdep` commands.

Install ROS 2 Humble using the repository script:

```bash
cd ~/rosbot
chmod +x install_ros2.sh
./install_ros2.sh
```

Open a new Ubuntu terminal or source ROS manually:

```bash
source /opt/ros/humble/setup.bash
```

Initialize the submodules:

```bash
cd ~/rosbot
git submodule update --init --recursive
```

## 5. Install mapping dependencies

```bash
source /opt/ros/humble/setup.bash

sudo apt update
sudo apt install -y \
  ros-humble-librealsense2 \
  ros-humble-rtabmap-ros \
  ros-humble-imu-filter-madgwick \
  ros-humble-rqt-image-view \
  python3-rosdep \
  python3-colcon-common-extensions

sudo rosdep init 2>/dev/null || true
rosdep update
```

Install workspace dependencies. `librealsense2` is skipped because the WSL-compatible copy is built in the next section:

```bash
cd ~/rosbot
rosdep install \
  --from-paths src \
  --ignore-src \
  -r -y \
  --skip-keys librealsense2
```

## 6. Build a WSL-compatible librealsense

The normal Linux librealsense backend expects direct kernel camera access. Under USB/IP, the `FORCE_RSUSB_BACKEND` build is more reliable and exposes the camera through libusb. It also avoids the `No HID info provided, IMU is disabled` condition seen with an incompatible backend.

### 6.1 Determine the required SDK version

The librealsense runtime version must match the version against which `realsense2_camera` is compiled. First inspect any ROS-provided version:

```bash
dpkg -l | grep -E 'librealsense|realsense2'
apt-cache policy ros-humble-librealsense2
```

Capture the upstream version portion automatically. For example, a Debian package version beginning with `2.58.3-` produces `2.58.3`:

```bash
LIBREALSENSE_VERSION="$(
  dpkg-query -W -f='${Version}\n' ros-humble-librealsense2 | cut -d- -f1
)"
echo "${LIBREALSENSE_VERSION}"
```

The exact value may change as ROS packages are updated.

### 6.2 Build that version with RSUSB

Use that exact version when checking out librealsense:

```bash
sudo apt install -y \
  build-essential \
  cmake \
  git \
  libgtk-3-dev \
  libssl-dev \
  libusb-1.0-0-dev \
  libudev-dev \
  pkg-config

cd ~
git clone https://github.com/IntelRealSense/librealsense.git
cd ~/librealsense
git fetch --tags
git checkout "v${LIBREALSENSE_VERSION}"

cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DFORCE_RSUSB_BACKEND=ON \
  -DBUILD_EXAMPLES=ON \
  -DBUILD_GRAPHICAL_EXAMPLES=OFF

cmake --build build -j"$(nproc)"
sudo cmake --install build
sudo ldconfig
```

Confirm the local SDK version:

```bash
pkg-config --modversion realsense2
find /usr/local/lib -maxdepth 1 -name 'librealsense2.so*' -ls
```

Do not leave an older librealsense in `/usr/local/lib`. An older local runtime can override the newer ROS package at launch and cause an API version mismatch.

## 7. Build the ROS workspace

Build the source RealSense wrapper against the selected SDK:

```bash
source /opt/ros/humble/setup.bash
export LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH:-}

cd ~/rosbot
rm -rf build/realsense2_camera build/realsense2_camera_msgs
rm -rf install/realsense2_camera install/realsense2_camera_msgs

colcon build --symlink-install \
  --cmake-args -DCMAKE_BUILD_TYPE=Release
```

The targeted `rm` commands only remove generated build products for the two RealSense ROS packages. They do not remove source files.

Source the finished workspace:

```bash
source /opt/ros/humble/setup.bash
source ~/rosbot/install/setup.bash
export LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH:-}
```

Verify which librealsense the source wrapper loads:

```bash
ldd ~/rosbot/install/realsense2_camera/lib/librealsense2_camera.so \
  | grep librealsense2
```

The result should point to `/usr/local/lib/librealsense2.so.<matching-version>`.

> [!NOTE]
> A symlinked install can cause `find -type f` to miss installed package libraries and executables. Inspect the known path directly or allow symlinks in the search.

## 8. Verify the SDK and camera

Stop the native Windows RealSense Viewer before attaching the camera to WSL. Verify without `sudo`:

```bash
source /opt/ros/humble/setup.bash
source ~/rosbot/install/setup.bash
export LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH:-}

rs-enumerate-devices
```

The command should report the D435IF, its serial number, firmware version, and stream profiles.

Do not run `sudo rs-enumerate-devices`. Running it as root changes configuration paths and can produce a harmless but confusing missing `/root/.realsense-config.json` warning.

For firmware updates, detach the camera from WSL and use the native Windows RealSense Viewer. Do not force an unsigned firmware image through WSL. A message such as `Unsupported firmware binary image (unsigned)` means the selected image or update path is not accepted; it does not mean that the camera must be forcibly updated.

## How the mapping algorithm works

1. **Sensor acquisition:** The D435IF publishes two rectified monochrome images from its infrared stereo pair. Their camera-info messages contain the calibrated projection models, and the camera's static transforms describe the fixed baseline between the imagers.
2. **IMU orientation:** The gyroscope measures short-term angular motion and the accelerometer observes gravity plus linear acceleration. Madgwick integrates the gyroscope and uses gravity to correct roll and pitch drift. Because the D435IF has no magnetometer, absolute yaw remains unobservable and can drift over time.
3. **Stereo geometry:** RTAB-Map finds visual features in the left and right images and matches them across the known stereo baseline. Disparity between a matched pair triangulates a three-dimensional landmark. Nearby or incorrectly matched features are rejected by geometric checks.
4. **Visual odometry:** Features are matched again across consecutive time steps. RTAB-Map estimates the six-degree-of-freedom camera transform that best explains the 3D correspondences. The IMU orientation provides gravity alignment and a rotational prior; it does not replace visual translation estimation.
5. **Keyframe graph:** Selected frames become graph nodes. Short-range odometry constraints connect neighboring nodes. RTAB-Map manages recent, working, and long-term memories so the graph can grow without comparing every frame against every previous frame.
6. **Loop closure:** A visual place-recognition stage proposes previously visited locations. RTAB-Map verifies each proposal geometrically before adding a loop-closure constraint, reducing the risk of corrupting the map with a false match.
7. **Graph optimization:** When constraints are added, RTAB-Map optimizes the pose graph. The `odom` frame remains locally continuous, while the `map` to `odom` transform absorbs global corrections from loop closures.
8. **Map output:** Optimized poses place the stereo-derived 3D observations into a consistent global map. The current stereo pipeline uses infrared imagery, so its visual map is grayscale. The optional RGB topic is published independently and is not automatically fused into standard stereo RTAB-Map.

This is stereo visual odometry aided by a filtered IMU orientation. It is not a tightly coupled visual-inertial optimizer: the camera remains responsible for translation and most tracking constraints, while the IMU primarily supplies gravity alignment and a rotation estimate.

The main transforms are conceptually:

```text
map ──loop-closure correction──> odom ──stereo odometry──> camera_link
                                                              │
                                                              └── static sensor transforms
                                                                  ├── infra1 optical frame
                                                                  ├── infra2 optical frame
                                                                  └── IMU optical frame
```

## Implementation roadmap

1. **Repeatable sensor bringup — implemented:** Forward the camera into WSL, use the RSUSB librealsense backend, enforce matching SDK versions, and verify both infrared images plus the combined IMU.
2. **Single-command mapping — implemented:** `d435if_stereo_slam.launch.py` starts the camera, Madgwick, RTAB-Map stereo odometry, mapping, and visualization with the tested topic names and synchronization settings.
3. **Repeatable datasets — next:** Record stereo, camera-info, IMU, and TF topics in rosbag2. Use a fixed indoor route and compare frame gaps, odometry inliers, drift, loop closures, and CPU load after every parameter change.
4. **Robot-frame integration — next:** Add the measured static transform from `base_link` to `camera_link`, change the mapper's tracking frame to `base_link`, and verify that only one component publishes each dynamic TF edge.
5. **Wheel odometry — next:** Feed calibrated wheel odometry into the robot state estimator. Use it as a motion prior or external odometry source without allowing two nodes to publish competing `odom` transforms.
6. **LiDAR and navigation — later:** Add the RPLIDAR scan after visual mapping is stable, generate a 2D occupancy grid, and connect the resulting `map -> odom -> base_link` tree to Nav2.
7. **RGB products — optional:** Keep RGB independent for detection or logging, or validate a separate aligned RGB-D mapping mode when a colored map is required.

## 9. Start the complete stereo, IMU, RGB, and RTAB-Map stack

### Unified launch file (recommended)

After rebuilding the workspace, start the known-good stereo/IMU mapper with one command:

```bash
source /opt/ros/humble/setup.bash
source ~/rosbot/install/setup.bash
export LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH:-}
unset RMW_IMPLEMENTATION
unset ROS_LOCALHOST_ONLY

ros2 launch rover_slam d435if_stereo_slam.launch.py
```

RGB is disabled by default because the stereo mapper does not consume it. Enable the independent RGB stream when needed:

```bash
ros2 launch rover_slam d435if_stereo_slam.launch.py enable_rgb:=true
```

Continue the existing `~/.ros/rtabmap.db` instead of deleting it:

```bash
ros2 launch rover_slam d435if_stereo_slam.launch.py new_map:=false
```

Useful launch arguments are:

| Argument | Default | Meaning |
| --- | --- | --- |
| `enable_rgb` | `false` | Publish the optional RGB stream. |
| `infra_profile` | `424x240x6` | Left/right infrared resolution and rate. |
| `color_profile` | `640x480x6` | Optional RGB resolution and rate. |
| `frame_id` | `camera_link` | RTAB-Map tracking frame. Use the robot base frame only after its static transform is available. |
| `new_map` | `true` | Delete the old database and start a new graph. |
| `rtabmap_viz` | `true` | Start the RTAB-Map GUI. |

### Manual launch for debugging

The following separate-terminal procedure exposes each pipeline stage individually. Use it when diagnosing topic rates or synchronization. Start the terminals in order. The environment setup is intentionally repeated so that each terminal is self-contained.

### Terminal 1: RealSense camera

```bash
source /opt/ros/humble/setup.bash
source ~/rosbot/install/setup.bash
export LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH:-}
unset RMW_IMPLEMENTATION
unset ROS_LOCALHOST_ONLY

ros2 launch realsense2_camera rs_launch.py \
  initial_reset:=false \
  enable_color:=true \
  rgb_camera.color_profile:=640x480x6 \
  rgb_camera.enable_auto_exposure:=true \
  enable_depth:=false \
  enable_infra1:=true \
  enable_infra2:=true \
  depth_module.infra_profile:=424x240x6 \
  depth_module.emitter_enabled:=0 \
  enable_accel:=true \
  enable_gyro:=true \
  accel_fps:=100 \
  gyro_fps:=200 \
  unite_imu_method:=1 \
  enable_sync:=false \
  pointcloud.enable:=false
```

Wait for `RealSense Node Is Up!`. When RGB is enabled, use another terminal to prevent auto exposure from lowering its frame rate:

```bash
ros2 param set /camera/camera rgb_camera.auto_exposure_priority false
```

This sensor option is set directly by the unified `rover_slam` launch file. It is not a declared command-line argument in the pinned `rs_launch.py`, so the manual launch configures it after the camera node starts.

Occasional `control_transfer returned error` warnings can be tolerated only if all required topics continue publishing at stable rates.

If simultaneous RGB causes instability under WSL, set `enable_color:=false` and establish reliable stereo/IMU mapping first. RGB is not required by the stereo RTAB-Map configuration.

### Terminal 2: Madgwick IMU orientation

The RealSense combined IMU topic contains angular velocity and acceleration but no usable absolute orientation. Madgwick adds a gravity-referenced orientation for RTAB-Map.

```bash
source /opt/ros/humble/setup.bash
source ~/rosbot/install/setup.bash
export LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH:-}
unset RMW_IMPLEMENTATION
unset ROS_LOCALHOST_ONLY

ros2 run imu_filter_madgwick imu_filter_madgwick_node \
  --ros-args \
  -p use_mag:=false \
  -p world_frame:=enu \
  -p publish_tf:=false \
  -r imu/data_raw:=/camera/camera/imu \
  -r imu/data:=/imu/data
```

Keep the camera stationary for several seconds while the filter initializes.

### Terminal 3: RTAB-Map stereo mapping

```bash
source /opt/ros/humble/setup.bash
source ~/rosbot/install/setup.bash
export LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH:-}
unset RMW_IMPLEMENTATION
unset ROS_LOCALHOST_ONLY

ros2 launch rtabmap_launch rtabmap.launch.py \
  stereo:=true \
  left_image_topic:=/camera/camera/infra1/image_rect_raw \
  right_image_topic:=/camera/camera/infra2/image_rect_raw \
  left_camera_info_topic:=/camera/camera/infra1/camera_info \
  right_camera_info_topic:=/camera/camera/infra2/camera_info \
  frame_id:=camera_link \
  imu_topic:=/imu/data \
  wait_imu_to_init:=true \
  approx_sync:=true \
  approx_sync_max_interval:=0.10 \
  topic_queue_size:=30 \
  queue_size:=30 \
  qos:=1 \
  rtabmap_args:="-d" \
  rviz:=false \
  rtabmap_viz:=true
```

`rtabmap_args:="-d"` deletes the previous RTAB-Map database and starts a new map. See [Saving and reopening a map](#11-saving-and-reopening-a-map) before collecting important data.

Move the camera slowly through a well-lit, textured scene. Sideways motion provides better stereo parallax than fast forward motion. Blank walls, reflections, darkness, motion blur, and rapid rotation reduce visual odometry quality.

### Terminal 4: Monitoring

```bash
source /opt/ros/humble/setup.bash
source ~/rosbot/install/setup.bash
unset RMW_IMPLEMENTATION
unset ROS_LOCALHOST_ONLY

ros2 node list

timeout 15s ros2 topic hz /camera/camera/infra1/image_rect_raw
timeout 15s ros2 topic hz /camera/camera/infra2/image_rect_raw
timeout 15s ros2 topic hz /camera/camera/color/image_raw
timeout 15s ros2 topic hz /camera/camera/imu
timeout 15s ros2 topic hz /imu/data
timeout 15s ros2 topic hz /rtabmap/odom
```

To view RGB:

```bash
ros2 run rqt_image_view rqt_image_view
```

Select `/camera/camera/color/image_raw` in the topic selector.

## 10. Expected topics and rates

With the launch configuration above:

| Topic | Purpose | Expected rate |
| --- | --- | ---: |
| `/camera/camera/infra1/image_rect_raw` | Left rectified infrared image | about 6.7 Hz |
| `/camera/camera/infra2/image_rect_raw` | Right rectified infrared image | about 6.7 Hz |
| `/camera/camera/color/image_raw` | RGB image | about 6.7 Hz |
| `/camera/camera/imu` | Combined raw accelerometer and gyroscope | about 200-220 Hz |
| `/imu/data` | Madgwick-filtered IMU with orientation | about 200-220 Hz |
| `/rtabmap/odom` | Stereo visual odometry | about 6.7 Hz |

Expected nodes include:

```text
/camera/camera
/imu_filter_madgwick
/rtabmap/rtabmap
/rtabmap/stereo_odometry
```

The first warning from `ros2 topic hz` may say that the topic has not appeared yet. If rates are then printed continuously, the topic is publishing.

## 11. Saving and reopening a map

RTAB-Map stores its default database at:

```text
~/.ros/rtabmap.db
```

Stop RTAB-Map normally with Ctrl+C and wait for `Saving database/long-term memory...done!` before closing the terminal.

For a new map, use:

```bash
rtabmap_args:="-d"
```

To reopen and extend the existing database, use:

```bash
rtabmap_args:=""
```

Shut down the stack in reverse order: RTAB-Map, Madgwick, then RealSense.

## 12. RGB behavior

RGB is published independently at:

```text
/camera/camera/color/image_raw
/camera/camera/color/camera_info
```

The standard RTAB-Map stereo mode consumes only the left and right infrared images. Enabling RGB does **not** make the stereo map colored. The RGB stream is available for recording, object detection, semantic processing, or a separate visualization.

A colored RTAB-Map configuration should instead use RGB-D input:

```text
color/image_raw + aligned_depth_to_color/image_raw + IMU
```

The D435IF depth remains stereo-derived, but RTAB-Map consumes the camera's depth result rather than the two raw infrared images. This is a different mapping configuration and should be tested separately from the known-good raw-stereo pipeline.

## Troubleshooting

### `fatal: not a git repository` or `given path 'src' does not exist`

The shell is not in the repository root. Find the checkout and confirm both `.git` and `src` exist:

```bash
find ~ -maxdepth 4 -type d -name .git -print
cd /path/to/the/checkout
test -d .git && test -d src && echo "Repository root confirmed"
```

Avoid cloning the repository inside an already-created `~/rosbot` directory, which can accidentally produce `~/rosbot/rosbot`.

### `No device detected` after the camera worked previously

USB/IP attachments do not persist through resets and restarts. In PowerShell:

```powershell
usbipd list
usbipd detach --busid <BUSID>
usbipd attach --wsl --busid <BUSID>
```

Then verify in WSL:

```bash
lsusb | grep 8086
rs-enumerate-devices
```

If necessary, unplug the camera for ten seconds, reconnect it, obtain its new bus ID, and attach it again.

### `failed to set power state` or `requested device ... is NOT found`

The USB-forwarded device is stuck or detached. The accompanying null-pointer messages are cleanup errors, not the root cause. Stop all camera processes and reattach with `usbipd`. If reattachment fails:

```powershell
usbipd detach --busid <BUSID>
wsl --shutdown
```

Reopen Ubuntu, attach the camera again, and verify with `rs-enumerate-devices` before starting ROS.

### API version mismatch

An error such as the following means that the wrapper and runtime use different librealsense versions:

```text
API version mismatch: librealsense.so was compiled with API version 2.x.y
but the application was compiled with 2.a.b
```

Inspect all three versions:

```bash
pkg-config --modversion realsense2
dpkg -l | grep -E 'librealsense|realsense2'
ldd ~/rosbot/install/realsense2_camera/lib/librealsense2_camera.so \
  | grep librealsense2
```

Rebuild and install the required librealsense tag with `FORCE_RSUSB_BACKEND=ON`, run `sudo ldconfig`, then clean and rebuild the two RealSense ROS packages as described above.

### `No HID info provided, IMU is disabled`

The wrapper is using a backend that cannot access the motion interface through the current WSL USB path. Confirm that the wrapper loads the RSUSB librealsense from `/usr/local/lib`. A healthy RSUSB startup normally reports a USB physical ID rather than a `/video4linux/video0` physical path.

### `Frames didn't arrived within 5 seconds`

The stream opened but frames stopped arriving. Check:

```bash
lsusb -t
timeout 15s ros2 topic hz /camera/camera/infra1/image_rect_raw
timeout 15s ros2 topic hz /camera/camera/infra2/image_rect_raw
```

Use low-bandwidth profiles first, close the Windows Viewer, connect directly to a USB 3 port, and reattach the camera if either stream remains at zero.

### `control_transfer returned error`

Under USB/IP, occasional messages such as these may be non-fatal:

```text
Resource temporarily unavailable, number: 11
error: Success, number: 0
```

Treat them as a problem only when accompanied by frame timeouts, device disconnection, odometry loss, or topic rates dropping to zero.

### Low RGB frame rate

First prevent color auto-exposure from reducing the frame rate:

```bash
ros2 param set /camera/camera rgb_camera.auto_exposure_priority false
ros2 param get /camera/camera rgb_camera.auto_exposure_priority
timeout 20s ros2 topic hz /camera/camera/color/image_raw
```

Test RGB by itself if the combined stream is slow. If RGB is stable in the native Windows Viewer but slow only under WSL, the camera, cable, and firmware are probably healthy; USB/IP or local ROS transport is the remaining bottleneck.

### Fast DDS shared-memory errors

An error such as:

```text
RTPS_TRANSPORT_SHM Error: Failed init_port fastrtps_port....
```

usually indicates a stale shared-memory lock after a crashed ROS process. Parameters may still be set successfully, but image performance can suffer if DDS falls back to UDP. Stop all ROS processes, run `wsl --shutdown` from PowerShell, reopen Ubuntu, reattach the camera, and restart the stack.

### ROS CLI appears to freeze

The first ROS 2 CLI invocation may spend time importing Python plugins or waiting for DDS discovery. Allow it to finish or bound diagnostic commands:

```bash
timeout 30s ros2 node list
timeout 30s ros2 topic list
```

Do not switch DDS implementations while diagnosing the camera. All terminals must use compatible ROS domain and middleware settings.

### RTAB-Map reports that it did not receive data

The standalone RTAB-Map command does not launch the RealSense driver. Keep the camera running in its own terminal and verify all four stereo inputs:

```bash
timeout 15s ros2 topic hz /camera/camera/infra1/image_rect_raw
timeout 15s ros2 topic hz /camera/camera/infra2/image_rect_raw
timeout 15s ros2 topic hz /camera/camera/infra1/camera_info
timeout 15s ros2 topic hz /camera/camera/infra2/camera_info
```

The provided launch uses approximate synchronization because exact synchronization did not reliably invoke the callback through WSL.

### `Not enough inliers` or odometry quality is zero

This is visual tracking loss, not a crash. Confirm both infrared images are sharp and synchronized, disable the infrared emitter, use a textured and well-lit scene, keep the camera motion slow, and test stereo without IMU guesses if necessary. Do not tune mapping parameters until both image streams are stable.

Inspect odometry information with:

```bash
timeout 15s ros2 topic echo /rtabmap/odom_info
```

Healthy tracking should have nonzero matches and inliers and should not repeatedly report a lost state.

## References

- [ROS 2 Humble documentation](https://docs.ros.org/en/humble/)
- [Microsoft: Connect USB devices under WSL](https://learn.microsoft.com/windows/wsl/connect-usb)
- [usbipd-win](https://github.com/dorssel/usbipd-win)
- [librealsense](https://github.com/IntelRealSense/librealsense)
- [RealSense ROS wrapper](https://github.com/IntelRealSense/realsense-ros)
- [RTAB-Map ROS](https://github.com/introlab/rtabmap_ros)
