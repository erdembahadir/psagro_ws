import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('psagro_description')
    ros_gz_sim_share = get_package_share_directory('ros_gz_sim')

    urdf_file = os.path.join(pkg_share, 'urdf', 'psagro.urdf')
    with open(urdf_file, 'r') as f:
        robot_description = f.read()

    # Convert package:// → file:// absolute paths so Fortress can find meshes
    # without needing IGN_GAZEBO_RESOURCE_PATH to contain the share dir.
    robot_description_resolved = robot_description.replace(
        'package://psagro_description/',
        f'file://{pkg_share}/'
    )

    # Build resource path: prepend psagro_description share so that Fortress
    # can also resolve package:// URIs that go through the SDF/URDF converter.
    ign_resource_path = os.pathsep.join(filter(None, [
        pkg_share,
        os.environ.get('IGN_GAZEBO_RESOURCE_PATH', ''),
    ]))

    return LaunchDescription([
        # Must be set before gz_sim.launch.py's OpaqueFunction reads the env.
        SetEnvironmentVariable(
            name='IGN_GAZEBO_RESOURCE_PATH',
            value=ign_resource_path,
        ),

        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='Use Gazebo simulation time'
        ),

        # Start Ignition Gazebo Fortress (empty world, gui enabled)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(ros_gz_sim_share, 'launch', 'gz_sim.launch.py')
            ),
            launch_arguments={
                'gz_args': '-r empty.sdf',
                'on_exit_shutdown': 'true',
            }.items(),
        ),

        # Publish resolved URDF to /robot_description (file:// mesh paths)
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{
                'robot_description': robot_description_resolved,
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }],
        ),

        # Wait for gz server to register /world/empty/create service,
        # then spawn the model from the /robot_description topic.
        TimerAction(
            period=6.0,
            actions=[
                Node(
                    package='ros_gz_sim',
                    executable='create',
                    name='spawn_psagro',
                    output='screen',
                    arguments=[
                        '-world', 'empty',
                        '-name',  'psagro',
                        '-topic', '/robot_description',
                        '-x', '0.0', '-y', '0.0', '-z', '0.0',
                    ],
                ),
            ],
        ),

        # Bridge /clock (Ignition → ROS) for simulation time
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            name='gz_clock_bridge',
            output='screen',
            arguments=[
                '/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock',
            ],
        ),
    ])
