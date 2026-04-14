import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
import xacro

def generate_launch_description():

    pkg_path = get_package_share_directory('rover_description')
    urdf_file = os.path.join(pkg_path, 'urdf', 'rover.urdf.xacro')

    # Process xacro into plain URDF
    robot_description = xacro.process_file(urdf_file).toxml()

    # robot_state_publisher reads the URDF and broadcasts TF transforms
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description}]
    )

    return LaunchDescription([
        robot_state_publisher
    ])