from typing import Optional, List, Tuple

import itertools
from mapfmclient.solution import Solution

from src.Astar.ODProblem import ODProblem
from src.Astar.solver import Solver
from src.util.AgentPath import AgentPath
from src.util.CAT import CAT
from src.util.PathSet import PathSet
from src.util.Groups import Groups
from src.util.coord import Coord
from src.util.grid import Grid, HeuristicType
from src.util.group import Group


class IDProblem:

    def __init__(self, grid: Grid, heuristic_type: HeuristicType, group: Group):
        self.grid = grid
        self.groups = None
        self.assigned_goals = None
        self.heuristic_type = heuristic_type
        self.agent_ids = group.agent_ids

        if heuristic_type == HeuristicType.Exhaustive:
            goal_ids = []
            for agent_id in self.agent_ids:
                start = self.grid.starts[agent_id]
                ids = []
                for i, goal in enumerate(self.grid.goals):
                    if start.color == goal.color:
                        ids.append(i)
                ids.sort(key=lambda x: self.grid.get_heuristic(Coord(start.x, start.y), x))
                goal_ids.append(ids)
            self.assigned_goals = filter(lambda x: len(x) == len(set(x)), itertools.product(*goal_ids))

    def solve(self) -> Optional[List[AgentPath]]:
        if self.heuristic_type == HeuristicType.Exhaustive:
            best = float("inf")
            best_solution = None
            for goals in self.assigned_goals:
                print(f"Trying goal assignment of {goals} with maximum cost of {best}")
                solution = self.solve_matching(best, dict(zip(self.agent_ids, goals)))
                if solution is not None:
                    cost = sum(map(lambda x: x.get_cost(), solution))
                    if cost < best:
                        best = cost
                        best_solution = solution
            return best_solution
        else:
            solution = self.solve_matching()
            if solution is None:
                return None
            else:
                return solution

    def solve_matching(self, maximum=float("inf"), assigned_goals: dict = None) -> Optional[List[AgentPath]]:
        paths = PathSet(self.grid, self.agent_ids, self.heuristic_type, assigned_goals=assigned_goals)
        # Create initial paths for the individual agents. Very quick because of the heuristic used
        self.groups = Groups([Group([n]) for n in self.agent_ids])
        for group in self.groups.groups:
            problem = ODProblem(self.grid, group, CAT.empty(), assigned_goals=assigned_goals)
            solver = Solver(problem, max_cost=paths.get_remaining_cost(group.agent_ids, maximum))
            group_paths = solver.solve()
            if group_paths is None:
                return None
            # Update the path and CAT table
            paths.update(group_paths)

        # Start looking for conflicts
        avoided_conflicts = set()
        conflict = paths.find_conflict()
        while conflict is not None:
            combine_groups = True
            a, b = conflict
            a_group = self.groups.group_map[a]
            b_group = self.groups.group_map[b]

            # Check if the conflict has been solved before. If so it has clearly failed
            combo = (a_group.agent_ids, b_group.agent_ids)
            if combo not in avoided_conflicts:
                avoided_conflicts.add(combo)

                # Try rerunning a while the b moves are not possible
                problem = ODProblem(self.grid, a_group, paths.cat,
                                    illegal_moves=[paths[i] for i in b_group.agent_ids], assigned_goals=assigned_goals)

                # The maximum cost that it can have while still being optimal
                maximum_cost = paths[a].get_cost() + sum(paths[i].get_cost() for i in b_group.agent_ids)
                solver = Solver(problem, max_cost=maximum_cost)
                solution = solver.solve()
                if solution is not None:
                    # If a solution is found we can update the paths and we don't need to combine anything
                    combine_groups = False
                    paths.update(solution)
                else:
                    # Try redoing b by making a illegal
                    problem = ODProblem(self.grid, b_group, paths.cat,
                                        illegal_moves=[paths[i] for i in a_group.agent_ids],
                                        assigned_goals=assigned_goals)

                    # The maximum cost that it can have while still being optimal
                    maximum_cost = paths[b].get_cost() + sum(paths[i].get_cost() for i in a_group.agent_ids)
                    solver = Solver(problem, max_cost=maximum_cost)
                    solution = solver.solve()
                    if solution is not None:
                        # If a solution is found we can update the paths and we don't need to combine anything
                        combine_groups = False
                        paths.update(solution)

            # Combine groups
            if combine_groups:
                group = self.groups.combine_agents(a, b)
                print(f"Combining agents from groups of {a} and {b} into {group.agent_ids}")
                problem = ODProblem(self.grid, group, paths.cat, assigned_goals=assigned_goals)
                solver = Solver(problem, max_cost=paths.get_remaining_cost(group.agent_ids, maximum))
                group_paths = solver.solve()
                if group_paths is None:
                    return None
                paths.update(group_paths)

            # Find next conflict
            conflict = paths.find_conflict()
        return paths.paths