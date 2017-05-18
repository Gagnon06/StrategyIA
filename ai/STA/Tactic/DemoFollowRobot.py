# Under MIT licence, see LICENCE.txt
from RULEngine.Game.Player import Player
from ai.STA.Action.AllStar import AllStar
from ai.STA.Action.PathfindToPosition import PathfindToPosition
from ai.STA.Tactic.Tactic import Tactic
from ai.STA.Tactic.tactic_constants import DEFAULT_TIME_TO_LIVE
from ai.STA.Action.MoveToPosition import MoveToPosition
from ai.STA.Action.Idle import Idle
from RULEngine.Util.geometry import get_distance, get_angle
from RULEngine.Util.Pose import Pose
from RULEngine.Util.constant import POSITION_DEADZONE, ROBOT_RADIUS
from ai.STA.Tactic.tactic_constants import Flags
from ai.states.game_state import GameState

__author__ = 'RoboCupULaval'


FOLLOW_SPEED = 1.5


class DemoFollowRobot(Tactic):
    # TODO : Renommer la classe pour illustrer le fait qu'elle set une Pose et non juste une Position
    """
    méthodes:
        exec(self) : Exécute une Action selon l'état courant
    attributs:
        game_state: état courant du jeu
        player_id : Identifiant du joueur auquel est assigné la tactique
    """
    def __init__(self, game_state: GameState, player: Player, p_target: Pose=Pose(), args=None,
                 time_to_live=DEFAULT_TIME_TO_LIVE):
        Tactic.__init__(self, game_state, player, p_target, args, time_to_live=time_to_live)
        assert isinstance(player, Player)

        self.robot_to_follow_id = args[0].id
        self.current_state = self.halt
        self.next_state = self.halt

    def move_to_ball(self):
        self.status_flag = Flags.WIP
        self.target = self.game_state.get_player_pose(self.robot_to_follow_id)
        move = PathfindToPosition(self.game_state, self.player_id, self.target)

        if get_distance(self.game_state.get_player_pose(self.player_id).position, self.target.position) <\
           POSITION_DEADZONE + ROBOT_RADIUS:
            self.next_state = self.halt
        else:
            self.next_state = self.move_to_ball

        return move

    def halt(self, reset=False):
        self.status_flag = Flags.SUCCESS

        stop = Idle(self.game_state, self.player_id)

        if get_distance(self.game_state.get_player_pose(self.player_id).position, self.game_state.get_ball_position()) \
                < POSITION_DEADZONE + ROBOT_RADIUS:
            self.next_state = self.halt
        else:
            self.next_state = self.move_to_ball
        return stop
