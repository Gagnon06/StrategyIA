# Under MIT License, see LICENSE.txt
from enum import IntEnum
import numpy as np

from RULEngine.Util.Pose import Pose
from RULEngine.Util.Position import Position
from ai.Util.ai_command import AICommandType, AIControlLoopType, AICommand
from ai.executors.executor import Executor
from ai.states.world_state import WorldState
from config.config_service import ConfigService

TARGET_TRESHOLD = 0.1


class Pos(IntEnum):
    X = 0
    Y = 1
    THETA = 2


class DotDict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


class MotionExecutor(Executor):
    def __init__(self, p_world_state: WorldState):
        super().__init__(p_world_state)
        is_simulation = ConfigService().config_dict["GAME"]["type"] == "sim"
        self.robot_motion = [RobotMotion(p_world_state, player_id, is_sim=is_simulation) for player_id in
                             range(12)]

    def exec(self):
        for player in self.ws.game_state.my_team.available_players.values():
            if player.ai_command is None:
                continue

            cmd = player.ai_command
            r_id = player.id

            if cmd.command is AICommandType.MOVE:
                if cmd.control_loop_type is AIControlLoopType.POSITION:
                    cmd.speed = self.robot_motion[r_id].update(cmd)

                elif cmd.control_loop_type is AIControlLoopType.SPEED:
                    speed = fixed2robot(cmd.pose_goal.conv_2_np(), player.pose.orientation)
                    cmd.speed = Pose(Position(speed[Pos.X], speed[Pos.Y]), speed[Pos.THETA])

                elif cmd.control_loop_type is AIControlLoopType.OPEN:
                    cmd.speed = cmd.pose_goal

            elif cmd.command is AICommandType.STOP:
                cmd.speed = Pose(Position(0, 0), 0)
                self.robot_motion[r_id].stop()


class RobotMotion(object):
    def __init__(self, world_state: WorldState, robot_id, is_sim=True):
        self.ws = world_state
        self.id = robot_id

        self.dt = None

        self.setting = get_control_setting(is_sim)
        self.setting.translation.max_acc = None
        self.setting.translation.max_speed = None
        self.setting.rotation.max_speed = None

        self.current_position = np.zeros(3)
        self.current_orientation = 0
        self.current_velocity = np.zeros(3)
        self.current_acceleration = np.zeros(2)

        self.pos_error = np.zeros(3)
        self.translation_error = np.zeros(2)

        self.target_position = np.zeros(3)
        self.target_speed = np.zeros(1)
        self.target_acceleration = np.zeros(3)
        self.target_orientation = np.zeros(1)
        self.target_direction = np.zeros(2)

        self.last_translation_cmd = np.zeros(2)
        self.cruise_speed = np.zeros(1)

        self.target_reached = False

        self.x_controller = PID(self.setting.translation.kp,
                                self.setting.translation.ki,
                                self.setting.translation.kd,
                                self.setting.translation.antiwindup)

        self.y_controller = PID(self.setting.translation.kp,
                                self.setting.translation.ki,
                                self.setting.translation.kd,
                                self.setting.translation.antiwindup)

        self.angle_controller = PID(self.setting.rotation.kp,
                                    self.setting.rotation.ki,
                                    self.setting.rotation.kd,
                                    self.setting.rotation.antiwindup)

    def update(self, cmd: AICommand) -> Pose():
        self.update_states(cmd)
        self.target_reached = self.target_is_reached()

        # Rotation control
        rotation_cmd = np.array(self.angle_controller.update(self.pos_error[Pos.THETA]))
        rotation_cmd = np.clip(rotation_cmd,
                               -self.setting.rotation.max_speed,
                               self.setting.rotation.max_speed)
        if self.setting.rotation.sensibility < np.abs(rotation_cmd) < self.setting.rotation.deadzone:
                rotation_cmd = 0

        # Translation control
        translation_cmd = self.get_next_velocity()
        translation_cmd += np.array([self.x_controller.update(self.pos_error[Pos.X]),
                                     self.y_controller.update(self.pos_error[Pos.Y])])

        translation_cmd = self.limit_acceleration(translation_cmd)
        translation_cmd = np.clip(translation_cmd, -self.cruise_speed, self.cruise_speed)
        #translation_cmd = self.apply_deadzone(translation_cmd)

        # Send new command to robot
        translation_cmd = fixed2robot(translation_cmd, self.current_orientation)
        return Pose(Position(translation_cmd[Pos.X], translation_cmd[Pos.Y]), rotation_cmd)

    def get_next_velocity(self) -> np.ndarray:
        """Return the next velocity according to a constant acceleration model of a point mass.
           It try to produce a trapezoidal velocity path with the required cruising and target speed.
           The target speed is the speed that the robot need to reach at the target point."""

        alpha = 1

        current_speed = np.linalg.norm(self.current_velocity[0:2])
        next_speed = 0.0

        distance_to_reach_target_speed = 0.5 * (np.square(self.target_speed) - np.square(current_speed))
        distance_to_reach_target_speed /= self.setting.translation.max_acc

        distance_to_reach_target_speed = alpha * np.abs(distance_to_reach_target_speed)
        distance_to_target = np.linalg.norm(self.pos_error[0:2])

        if distance_to_target < distance_to_reach_target_speed:  # We need to go to target speed
            if current_speed < self.target_speed:  # Target speed is faster than current speed
                next_speed = current_speed + self.setting.translation.max_acc * self.dt
                if next_speed > self.target_speed:  # Next_speed is too fast
                    next_speed = self.target_speed
            else:  # Target speed is slower than current speed
                next_speed = current_speed - self.setting.translation.max_acc * self.dt

        else:  # We need to go to the cruising speed
            if current_speed < self.cruise_speed:  # Going faster
                next_speed = current_speed + self.setting.translation.max_acc * self.dt

        next_speed = np.clip(next_speed, 0, self.cruise_speed)  # We don't want to go faster than cruise speed

        next_velocity = next_speed * self.target_direction
        return next_velocity

    def apply_deadzone(self, translation_cmd):
        if self.setting.translation.sensibility < np.abs(translation_cmd[Pos.X]) < self.setting.translation.deadzone:
            translation_cmd[Pos.X] = self.setting.translation.deadzone
        else:
            translation_cmd[Pos.X] = 0
        if self.setting.translation.sensibility < np.abs(translation_cmd[Pos.Y]) < self.setting.translation.deadzone:
            translation_cmd[Pos.Y] = self.setting.translation.deadzone
        else:
            translation_cmd[Pos.Y] = 0

        return translation_cmd

    def limit_acceleration(self, translation_cmd: np.ndarray) -> np.ndarray:
        self.current_acceleration = (translation_cmd - self.last_translation_cmd) / self.dt
        self.current_acceleration = np.clip(self.current_acceleration,
                                            -np.abs(self.target_acceleration),
                                            np.abs(self.target_acceleration))
        translation_cmd = self.last_translation_cmd + self.current_acceleration * self.dt
        self.last_translation_cmd = translation_cmd
        return translation_cmd

    def target_is_reached(self):
        if np.square(self.pos_error).sum() <= TARGET_TRESHOLD ** 2:
            return True
        else:
            return False

    def update_states(self, cmd: AICommand):
        self.dt = self.ws.game_state.game.delta_t

        # Dynamics constraints
        self.setting.translation.max_acc = self.ws.game_state.get_player(self.id).max_acc
        self.setting.translation.max_speed = self.ws.game_state.get_player(self.id).max_speed
        self.setting.rotation.max_speed = self.ws.game_state.get_player(self.id).max_angular_speed

        # Current state of the robot
        self.current_position = self.ws.game_state.game.friends.players[self.id].pose.conv_2_np()
        self.current_position = self.current_position / np.array([1000, 1000, 1])
        self.current_orientation = self.current_position[Pos.THETA]
        self.current_velocity = np.array(self.ws.game_state.game.friends.players[self.id].velocity)
        self.current_velocity = self.current_velocity / np.array([1000, 1000, 1])

        self.pos_error = self.target_position - self.current_position
        self.translation_error = self.pos_error[0:2]
        if self.pos_error[Pos.THETA] > np.pi:  # Try to minimize the rotation angle
            self.pos_error[Pos.THETA] = self.pos_error[Pos.THETA] - 2 * np.pi

        # Desired parameters
        self.target_direction = normalized(self.translation_error)
        #self.target_position = cmd.pose_goal.conv_2_np()
        self.target_position = Pose(cmd.path[0], self.current_orientation).conv_2_np()
        self.target_position = self.target_position / np.array([1000, 1000, 1])
        self.target_speed = cmd.path_speeds[1]/1000
        self.target_acceleration = np.abs(self.setting.translation.max_acc * self.target_direction)
        self.target_acceleration[self.target_acceleration == 0] = 10 ** (-6)  # Avoid division by zero later
        self.cruise_speed = np.abs(cmd.cruise_speed)

    def stop(self):
        self.angle_controller.reset()
        self.x_controller.reset()
        self.y_controller.reset()
        self.last_translation_cmd = np.zeros(2)
        self.current_position = np.zeros(3)
        self.current_orientation = 0
        self.current_velocity = np.zeros(3)
        self.current_acceleration = np.zeros(2)
        self.pos_error = np.zeros(3)
        self.target_position = np.zeros(3)
        self.target_speed = np.zeros(1)
        self.target_acceleration = np.zeros(3)
        self.last_translation_cmd = np.zeros(2)
        self.cruise_speed = np.zeros(1)
        self.translation_error = np.zeros(2)
        self.target_direction = np.zeros(2)
        self.target_direction = np.zeros(2)


class PID(object):
    def __init__(self, kp: float, ki: float, kd: float, antiwindup_size=0):
        """
        Simple PID parallel implementation
        Args:
            kp: proportional gain
            ki: integral gain
            kd: derivative gain
            antiwindup_size: max error accumulation of the error integration
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.err_sum = 0
        self.last_err = 0

        self.antiwindup_size = antiwindup_size
        if self.antiwindup_size > 0:
            self.antiwindup_active = True
            self.old_err = np.zeros(self.antiwindup_size)
            self.antiwindup_idx = 0
        else:
            self.antiwindup_active = False

    def update(self, err: float) -> float:
        d_err = err - self.last_err
        self.last_err = err
        self.err_sum += err

        if self.antiwindup_active:
            self.err_sum -= self.old_err[self.antiwindup_idx]
            self.old_err[self.antiwindup_idx] = err
            self.antiwindup_idx = (self.antiwindup_idx + 1) % self.antiwindup_size

        return (err * self.kp) + (self.err_sum * self.ki) + (d_err * self.kd)

    def reset(self):
        if self.antiwindup_active:
            self.old_err = np.zeros(self.antiwindup_size)
        self.err_sum = 0


def get_control_setting(is_sim: bool):

    if is_sim:
        translation = {"kp": 0.1, "ki": 0, "kd": 1, "antiwindup": 0, "deadzone": 0, "sensibility": 0}
        rotation = {"kp": 1, "ki": 0, "kd": 0, "antiwindup": 0, "deadzone": 0, "sensibility": 0}
    else:
        translation = {"kp": 0.06, "ki": 0.01, "kd": 0, "antiwindup": 10, "deadzone": 0.005, "sensibility": 0.001}
        rotation = {"kp": 0.1, "ki": 0.01, "kd": 0, "antiwindup": 10, "deadzone": 0.1, "sensibility": 0.01}

    control_setting = DotDict()
    control_setting.translation = DotDict(translation)
    control_setting.rotation = DotDict(rotation)

    return control_setting


def robot2fixed(vector: np.ndarray, angle: float) -> np.ndarray:
    tform = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    return np.dot(tform, vector)


def fixed2robot(vector: np.ndarray, angle: float) -> np.ndarray:
    return robot2fixed(vector, -angle)


def normalized(vector: np.ndarray) -> np.ndarray:
    if np.linalg.norm(vector) > 0:
        vector /= np.linalg.norm(vector)
    return vector

def orientation(vector: np.ndarray) -> np.ndarray:
    """Return the rotation of the vector in radian"""
    return np.arctan2(vector[1], vector[0])