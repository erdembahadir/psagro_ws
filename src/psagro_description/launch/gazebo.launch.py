import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    RegisterEventHandler,
    TimerAction,
)
from launch.event_handlers import OnProcessStart
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('psagro_description')
    gazebo_ros_share = get_package_share_directory('gazebo_ros')

    urdf_file = os.path.join(pkg_share, 'urdf', 'psagro.urdf')
    with open(urdf_file, 'r') as f:
        robot_description = f.read()

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(gazebo_ros_share, 'launch', 'gazebo.launch.py')
        ),
        launch_arguments={'world': ''}.items(),
    )

    rsp = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
    )

    # Spawn after a delay to ensure gzserver's /spawn_entity service is ready.
    # Gazebo Classic 11 registers /spawn_entity as a hidden service and can take
    # several seconds on first launch.
    spawn = TimerAction(
        period=10.0,
        actions=[
            Node(
                package='gazebo_ros',
                executable='spawn_entity.py',
                name='spawn_psagro',
                output='screen',
                arguments=[
                    '-entity', 'psagro',
                    '-topic', '/robot_description',
                    '-x', '0.0',
                    '-y', '0.0',
                    '-z', '0.0',
                ],
            )
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='Use Gazebo simulation time'
        ),

        gazebo,
        rsp,
        spawn,
    ])
