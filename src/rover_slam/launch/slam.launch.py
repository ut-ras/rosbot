import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():

    config_dir = os.path.join(
        get_package_share_directory('rover_slam'), 'config')

    rtabmap = Node(
        package='rtabmap_slam',
        executable='rtabmap',
        name='rtabmap',
        output='screen',
        parameters=[os.path.join(config_dir, 'rtabmap.yaml')],
        remappings=[
            ('rgb/image',       '/camera/camera/color/image_raw'),
            ('depth/image',     '/camera/camera/depth/image_rect_raw'),
            ('rgb/camera_info', '/camera/camera/color/camera_info'),
            ('scan',            '/scan'),
            ('odom',            '/odometry/filtered'),
        ],
        arguments=['--delete_db_on_start']
    )

    rtabmap_viz = Node(
        package='rtabmap_viz',
        executable='rtabmap_viz',
        name='rtabmap_viz',
        output='screen',
        parameters=[os.path.join(config_dir, 'rtabmap.yaml')],
        remappings=[
            ('rgb/image',       '/camera/camera/color/image_raw'),
            ('depth/image',     '/camera/camera/depth/image_rect_raw'),
            ('rgb/camera_info', '/camera/camera/color/camera_info'),
            ('scan',            '/scan'),
            ('odom',            '/odometry/filtered'),
        ]
    )

    return LaunchDescription([
        rtabmap,
        rtabmap_viz,
    ])