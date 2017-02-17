# Under MIT License, see LICENSE.txt
import time

from RULEngine.Util.game_world import GameWorld
from ai.executors.regulator import PositionRegulator
from ai.states.world_state import WorldState
from ai.executors.debug_executor import DebugExecutor
from ai.executors.pathfinder_module import PathfinderModule
from ai.executors.play_executor import PlayExecutor
from ai.executors.command_executor import CommandExecutor
from ai.executors.movement_executor import MovementExecutor
# FIXME this thing!


class BBCoach(object):

    def __init__(self, mode_debug_active=True, pathfinder="astar", is_simulation=True):
        self.mode_debug_active = mode_debug_active
        # For the framework! TODO make this better!
        self.robot_commands = []

        self.world_state = WorldState()
        self.debug_executor = DebugExecutor(self.world_state)
        self.pathfinder_module = PathfinderModule(self.world_state, pathfinder)

        self.play_executor = PlayExecutor(self.world_state)
        self.movement_executor = MovementExecutor(self.world_state)
        self.regulator_executor = PositionRegulator(self.world_state, is_simulation)

        self.robot_command_executor = CommandExecutor(self.world_state)

    def main_loop(self):

        self._send_books()
        self.robot_commands.clear()
        self.debug_executor.exec()
        self.play_executor.exec()
        self.pathfinder_module.exec()
        self.movement_executor.exec()
        self.regulator_executor.exec()


        self.robot_commands = self.robot_command_executor.exec()

        return self.robot_commands

    def set_reference(self, world_reference: GameWorld)-> None:
        self.world_state.set_reference(world_reference)
        self.debug_executor.set_reference(world_reference)

    def _send_books(self):
        cmd_tactics = {'strategy': ["NONE"],
                       'tactic': self.world_state.play_state.tactic_book.
                       get_tactics_name_list(),
                       'action': ['NONE']}
        self.world_state.debug_interface.send_books(cmd_tactics)











    # ******************************************************************************************************************
    # TODO DELETE MAX
    # ******************************************************************************************************************
    # not used see if we can delete.
    def get_debug_status(self):
        return self.mode_debug_active

    # Throwback for the last coach! TODO see if we still need to implement
    # them! Or HOW!
    def halt(self):
        """ Hack pour sync les frames de vision et les itérations de l'IA """
        pass

    def stop(self, game_state):
        """ *Devrait* déinit pour permettre un arrêt propre. """
        pass
