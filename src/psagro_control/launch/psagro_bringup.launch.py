import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    desc_share = get_package_share_directory('psagro_description')

    urdf_file = os.path.join(desc_share, 'urdf', 'psagro.urdf')
    with open(urdf_file, 'r') as f:
        robot_description = f.read()

    rviz_config = os.path.join(desc_share, 'rviz', 'psagro.rviz')

    return LaunchDescription([
        DeclareLaunchArgument(
            'port',
            default_value='/dev/ttyUSB0',
            description='Arduino seri port'
        ),
        DeclareLaunchArgument(
            'baud',
            default_value='115200',
            description='Seri port baud hizi'
        ),

        # Arduino köprüsü — port yoksa reconnect döngüsüyle bekler
        Node(
            package='psagro_control',
            executable='arduino_bridge',
            name='arduino_bridge',
            output='screen',
            parameters=[{
                'port': LaunchConfiguration('port'),
                'baud': LaunchConfiguration('baud'),
            }],
        ),

        # Pompa interactive marker node'u
        Node(
            package='psagro_control',
            executable='pump_interactive',
            name='pump_interactive',
            output='screen',
        ),

        # Robot model yayıncısı (URDF → /robot_description)
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_description}],
        ),

        # RViz2 — RobotModel + TF + Grid + InteractiveMarkers
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', rviz_config],
        ),
    ])
