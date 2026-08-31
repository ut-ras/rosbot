"""Power-conscious D435IF RGB-D/IMU mapping based on the RealSense wiki.

The 2019 RealSense D435i wiki pipeline is adapted here for ROS 2 Humble:
RealSense -> Madgwick -> RTAB-Map RGB-D odometry -> robot_localization ->
RTAB-Map SLAM. All image and state-estimation nodes are compiled C++ nodes;
Python is used only to describe and supervise the launch graph.
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


def _launch_mapping(context):
    """Resolve map lifecycle and processing-rate arguments before inclusion."""
    rtabmap_launch = os.path.join(
        get_package_share_directory('rtabmap_launch'),
        'launch',
        'rtabmap.launch.py',
    )
    new_map = _as_bool(LaunchConfiguration('new_map').perform(context))
    detection_rate = LaunchConfiguration('detection_rate').perform(context)
    linear_update = LaunchConfiguration('linear_update').perform(context)
    angular_update = LaunchConfiguration('angular_update').perform(context)
    rtabmap_args = (
        f'--Rtabmap/DetectionRate {detection_rate} '
        f'--RGBD/LinearUpdate {linear_update} '
        f'--RGBD/AngularUpdate {angular_update}'
    )
    if new_map:
        rtabmap_args = f'-d {rtabmap_args}'

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(rtabmap_launch),
            launch_arguments={
                'stereo': 'false',
                'depth': 'true',
                'rgb_topic': '/camera/camera/color/image_raw',
                'depth_topic': (
                    '/camera/camera/aligned_depth_to_color/image_raw'
                ),
                'camera_info_topic': '/camera/camera/color/camera_info',
                'frame_id': LaunchConfiguration('frame_id'),
                'visual_odometry': 'false',
                'odom_topic': '/odometry/filtered',
                'odom_frame_id': 'odom',
                'imu_topic': '/imu/data',
                'wait_imu_to_init': 'true',
                'approx_sync': 'true',
                'approx_sync_max_interval': LaunchConfiguration(
                    'approx_sync_max_interval'
                ),
                'topic_queue_size': LaunchConfiguration('topic_queue_size'),
                'queue_size': LaunchConfiguration('sync_queue_size'),
                'qos': '1',
                'rtabmap_args': rtabmap_args,
                'rtabmap_viz': LaunchConfiguration('rtabmap_viz'),
                'rviz': 'false',
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }.items(),
        )
    ]


def generate_launch_description():
    color_profile = LaunchConfiguration('color_profile')
    depth_profile = LaunchConfiguration('depth_profile')
    frame_id = LaunchConfiguration('frame_id')
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
            'enable_color': True,
            'rgb_camera.color_profile': ParameterValue(
                color_profile, value_type=str
            ),
            'rgb_camera.enable_auto_exposure': True,
            'rgb_camera.auto_exposure_priority': False,
            'enable_depth': True,
            'depth_module.depth_profile': ParameterValue(
                depth_profile, value_type=str
            ),
            'depth_module.emitter_enabled': 1,
            'align_depth.enable': True,
            'enable_infra': False,
            'enable_infra1': False,
            'enable_infra2': False,
            'enable_accel': True,
            'enable_gyro': True,
            'accel_fps': 100,
            'gyro_fps': 200,
            'unite_imu_method': 1,
            'enable_sync': True,
            'enable_rgbd': False,
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
            'orientation_stddev': 0.05,
            'use_sim_time': ParameterValue(use_sim_time, value_type=bool),
        }],
        remappings=[
            ('imu/data_raw', '/camera/camera/imu'),
            ('imu/data', '/imu/data'),
        ],
    )

    rgbd_odometry = Node(
        package='rtabmap_odom',
        executable='rgbd_odometry',
        namespace='rtabmap',
        name='rgbd_odometry',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'frame_id': frame_id,
            'odom_frame_id': 'odom',
            'publish_tf': False,
            'wait_for_transform': 0.2,
            'approx_sync': True,
            'approx_sync_max_interval': ParameterValue(
                LaunchConfiguration('approx_sync_max_interval'),
                value_type=float,
            ),
            'topic_queue_size': ParameterValue(
                LaunchConfiguration('topic_queue_size'), value_type=int
            ),
            'sync_queue_size': ParameterValue(
                LaunchConfiguration('sync_queue_size'), value_type=int
            ),
            'qos': 1,
            'Vis/MaxFeatures': '400',
            'Vis/MinInliers': '15',
            'use_sim_time': ParameterValue(use_sim_time, value_type=bool),
        }],
        remappings=[
            ('rgb/image', '/camera/camera/color/image_raw'),
            (
                'depth/image',
                '/camera/camera/aligned_depth_to_color/image_raw',
            ),
            ('rgb/camera_info', '/camera/camera/color/camera_info'),
            ('odom', '/visual_odom'),
        ],
    )

    state_estimator = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[{
            'frequency': ParameterValue(
                LaunchConfiguration('ekf_frequency'), value_type=float
            ),
            'sensor_timeout': 0.5,
            'two_d_mode': False,
            'publish_tf': True,
            'map_frame': 'map',
            'odom_frame': 'odom',
            'base_link_frame': frame_id,
            'world_frame': 'odom',
            'odom0': '/visual_odom',
            'odom0_config': [
                True, True, True,
                False, False, True,
                False, False, False,
                False, False, False,
                False, False, False,
            ],
            'odom0_differential': False,
            'odom0_relative': False,
            'odom0_queue_size': 10,
            'imu0': '/imu/data',
            'imu0_config': [
                False, False, False,
                True, True, False,
                False, False, False,
                True, True, False,
                False, False, False,
            ],
            'imu0_differential': False,
            'imu0_relative': False,
            'imu0_queue_size': 50,
            'imu0_remove_gravitational_acceleration': False,
            'use_sim_time': ParameterValue(use_sim_time, value_type=bool),
        }],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'color_profile',
            default_value='640x480x6',
            description='RealSense color profile as WIDTHxHEIGHTxFPS.',
        ),
        DeclareLaunchArgument(
            'depth_profile',
            default_value='640x480x6',
            description='RealSense depth profile as WIDTHxHEIGHTxFPS.',
        ),
        DeclareLaunchArgument(
            'frame_id',
            default_value='camera_link',
            description='Tracking frame used by odometry, EKF, and RTAB-Map.',
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
            default_value='false',
            description=(
                'Start the RTAB-Map GUI; disable to save CPU and power.'
            ),
        ),
        DeclareLaunchArgument(
            'detection_rate',
            default_value='1.0',
            description='Maximum RTAB-Map graph-update rate in Hz.',
        ),
        DeclareLaunchArgument(
            'linear_update',
            default_value='0.1',
            description=(
                'Minimum translation in meters before adding a map update.'
            ),
        ),
        DeclareLaunchArgument(
            'angular_update',
            default_value='0.1',
            description=(
                'Minimum rotation in radians before adding a map update.'
            ),
        ),
        DeclareLaunchArgument(
            'ekf_frequency',
            default_value='30.0',
            description='Filtered odometry publication frequency in Hz.',
        ),
        DeclareLaunchArgument(
            'approx_sync_max_interval',
            default_value='0.10',
            description='Maximum RGB/depth synchronization interval.',
        ),
        DeclareLaunchArgument(
            'topic_queue_size',
            default_value='30',
            description='Per-topic subscription queue size.',
        ),
        DeclareLaunchArgument(
            'sync_queue_size',
            default_value='30',
            description='RGB-D synchronization queue size.',
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use the ROS simulation clock.',
        ),
        camera,
        imu_filter,
        rgbd_odometry,
        state_estimator,
        OpaqueFunction(function=_launch_mapping),
    ])
