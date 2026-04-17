import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():

    config_dir = os.path.join(
        get_package_share_directory('rover_odometry'), 'config')

    # IMU filter — cleans raw IMU data from RealSense
    imu_filter = Node(
        package='imu_filter_madgwick',
        executable='imu_filter_madgwick_node',
        name='imu_filter_madgwick',
        output='screen',
        parameters=[os.path.join(config_dir, 'imu_filter.yaml')],
        remappings=[
            ('imu/data_raw', '/camera/camera/imu'),  # RealSense topic
            ('imu/data',     '/imu/filtered'),        # output
        ]
    )

    # Visual odometry — tracks features between RGB-D frames
    visual_odometry = Node(
        package='rtabmap_odom',
        executable='rgbd_odometry',
        name='rtabmap_odom',
        output='screen',
        parameters=[{
            'frame_id':        'base_link',
            'odom_frame_id':   'odom',
            'publish_tf':      True,
            'approx_sync':     True,
            'approx_sync_max_interval': 0.01,
        }],
        remappings=[
            ('rgb/image',        '/camera/camera/color/image_raw'),
            ('depth/image',      '/camera/camera/depth/image_rect_raw'),
            ('rgb/camera_info',  '/camera/camera/color/camera_info'),
        ]
    )

    # EKF — fuses visual odometry + IMU into /odometry/filtered
    ekf = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[os.path.join(config_dir, 'ekf.yaml')],
    )

    return LaunchDescription([
        imu_filter,
        visual_odometry,
        ekf,
    ])