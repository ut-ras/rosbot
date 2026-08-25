"""Bring up D435IF stereo/IMU mapping with RTAB-Map.

This launch file reproduces the known-good WSL configuration while keeping RGB
optional because RTAB-Map's stereo pipeline does not consume the color stream.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _as_bool(value):
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _launch_rtabmap(context):
    """Create the RTAB-Map include after resolving the new_map argument."""
    rtabmap_launch = os.path.join(
        get_package_share_directory('rtabmap_launch'),
        'launch',
        'rtabmap.launch.py',
    )
    new_map = _as_bool(LaunchConfiguration('new_map').perform(context))

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(rtabmap_launch),
            launch_arguments={
                'stereo': 'true',
                'left_image_topic': '/camera/camera/infra1/image_rect_raw',
                'right_image_topic': '/camera/camera/infra2/image_rect_raw',
                'left_camera_info_topic': '/camera/camera/infra1/camera_info',
                'right_camera_info_topic': '/camera/camera/infra2/camera_info',
                'frame_id': LaunchConfiguration('frame_id'),
                'imu_topic': '/imu/data',
                'wait_imu_to_init': 'true',
                'approx_sync': 'true',
                'approx_sync_max_interval': LaunchConfiguration(
                    'approx_sync_max_interval'
                ),
                'topic_queue_size': LaunchConfiguration('topic_queue_size'),
                'queue_size': LaunchConfiguration('sync_queue_size'),
                'qos': '1',
                'rtabmap_args': '-d' if new_map else '',
                'rtabmap_viz': LaunchConfiguration('rtabmap_viz'),
                'rviz': 'false',
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }.items(),
        )
    ]


def generate_launch_description():
    enable_rgb = LaunchConfiguration('enable_rgb')
    color_profile = LaunchConfiguration('color_profile')
    infra_profile = LaunchConfiguration('infra_profile')
    use_sim_time = LaunchConfiguration('use_sim_time')

    camera = Node(
        package='realsense2_camera',
        executable='realsense2_camera_node',
        namespace='camera',
        name='camera',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'camera_name': 'camera',
            'camera_namespace': 'camera',
            'initial_reset': False,
            'enable_color': ParameterValue(enable_rgb, value_type=bool),
            'rgb_camera.color_profile': ParameterValue(
                color_profile, value_type=str
            ),
            'rgb_camera.enable_auto_exposure': True,
            'rgb_camera.auto_exposure_priority': False,
            'enable_depth': False,
            'enable_infra1': True,
            'enable_infra2': True,
            'depth_module.infra_profile': ParameterValue(
                infra_profile, value_type=str
            ),
            'depth_module.emitter_enabled': 0,
            'enable_accel': True,
            'enable_gyro': True,
            'accel_fps': 100,
            'gyro_fps': 200,
            'unite_imu_method': 1,
            'enable_sync': False,
            'pointcloud.enable': False,
        }],
    )

    imu_filter = Node(
        package='imu_filter_madgwick',
        executable='imu_filter_madgwick_node',
        name='imu_filter_madgwick',
        output='screen',
        parameters=[{
            'use_mag': False,
            'world_frame': 'enu',
            'publish_tf': False,
            'gain': 0.1,
            'zeta': 0.0,
            'use_sim_time': ParameterValue(use_sim_time, value_type=bool),
        }],
        remappings=[
            ('imu/data_raw', '/camera/camera/imu'),
            ('imu/data', '/imu/data'),
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'enable_rgb',
            default_value='false',
            description=(
                'Publish RGB alongside stereo mapping (not used by RTAB-Map).'
            ),
        ),
        DeclareLaunchArgument(
            'color_profile',
            default_value='640x480x6',
            description='RealSense color profile as WIDTHxHEIGHTxFPS.',
        ),
        DeclareLaunchArgument(
            'infra_profile',
            default_value='424x240x6',
            description='RealSense infrared profile as WIDTHxHEIGHTxFPS.',
        ),
        DeclareLaunchArgument(
            'frame_id',
            default_value='camera_link',
            description='Tracking frame used by RTAB-Map.',
        ),
        DeclareLaunchArgument(
            'new_map',
            default_value='true',
            description=(
                'Delete the previous RTAB-Map database before starting.'
            ),
        ),
        DeclareLaunchArgument(
            'rtabmap_viz',
            default_value='true',
            description='Start the RTAB-Map desktop visualization.',
        ),
        DeclareLaunchArgument(
            'approx_sync_max_interval',
            default_value='0.10',
            description='Maximum stereo synchronization interval in seconds.',
        ),
        DeclareLaunchArgument(
            'topic_queue_size',
            default_value='30',
            description='Per-topic subscription queue size.',
        ),
        DeclareLaunchArgument(
            'sync_queue_size',
            default_value='30',
            description='Stereo synchronization queue size.',
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use the ROS simulation clock.',
        ),
        camera,
        imu_filter,
        OpaqueFunction(function=_launch_rtabmap),
    ])
