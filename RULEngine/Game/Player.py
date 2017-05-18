# Under MIT License, see LICENSE.txt
from RULEngine.Util.Position import Position
from RULEngine.Util.kalman_filter.enemy_kalman_filter import EnemyKalmanFilter
from config.config_service import ConfigService
from ..Util.Pose import Pose
from ..Util.constant import DELTA_T


class Player:

    def __init__(self, team, id):

        self.cmd = [0, 0, 0]

        self.id = id
        self.team = team
        self.pose = Pose()
        self.kf = EnemyKalmanFilter()

        self.pose = Pose()
        self.velocity = [0, 0, 0]
        self.update = self.__update
        if ConfigService().config_dict["IMAGE"]["kalman"] == "true":
            self.update = self.__kalman_update

    def has_id(self, pid):
        return self.id == pid

    def __update(self, pose, delta=DELTA_T):
        old_pose = self.pose
        self.pose = pose

    def __kalman_update(self, poses, delta):
        ret = self.kf.filter(poses, self.cmd, delta)
        self.pose = Pose(Position(ret[0], ret[1]), ret[4])
        self.velocity = [ret[2], ret[3], ret[5]]

    def set_command(self, cmd):
        self.cmd = [cmd.pose.position.x, cmd.pose.position.y, cmd.pose.orientation]

