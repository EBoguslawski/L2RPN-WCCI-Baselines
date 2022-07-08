from l2rpn_baselines.utils import GymEnvWithHeuristics
from typing import List
from grid2op.Action import BaseAction
import numpy as np
from grid2op.Chronics.multiFolder import Multifolder


class CustomGymEnv(GymEnvWithHeuristics):
  """This environment is slightly more complex that the other one.
  
  It consists in 2 things:
  
  #. reconnecting the powerlines if possible
  #. doing nothing is the state of the grid is "safe" (for this class, the notion of "safety" is pretty simple: if all
      flows are bellow 90% (by default) of the thermal limit, then it is safe)
  
  If for a given step, non of these things is applicable, the underlying trained agent is asked to perform an action
  
  .. warning::
      When using this environment, we highly recommend to adapt the parameter `safe_max_rho` to suit your need.
      
      Sometimes, 90% of the thermal limit is too high, sometimes it is too low.
      
  """
  def __init__(self, env_init, *args, reward_cumul="init", safe_max_rho=0.9, **kwargs):
    super().__init__(env_init, reward_cumul=reward_cumul, *args, **kwargs)
    self._safe_max_rho = safe_max_rho
    self.dn = self.init_env.action_space({})
    self.nb_reset = 0
        
  def heuristic_actions(self, g2op_obs, reward, done, info) -> List[BaseAction]:
    """To match the description of the environment, this heuristic will:
    
    - return the list of all the powerlines that can be reconnected if any
    - return the list "[do nothing]" is the grid is safe
    - return the empty list (signaling the agent should take control over the heuristics) otherwise

    Parameters
    ----------
    See parameters of :func:`GymEnvWithHeuristics.heuristic_actions`

    Returns
    -------
    See return values of :func:`GymEnvWithHeuristics.heuristic_actions`
    """
    
    to_reco = (g2op_obs.time_before_cooldown_line == 0) & (~g2op_obs.line_status)
    res = []
    if np.any(to_reco):
      # reconnect something if it can be
      reco_id = np.where(to_reco)[0]
      for line_id in reco_id:
          g2op_act = self.init_env.action_space({"set_line_status": [(line_id, +1)]})
          res.append(g2op_act)
    elif g2op_obs.rho.max() <= self._safe_max_rho:
      # play do nothing if there is "no problem" according to the "rule of thumb"
      res = [self.init_env.action_space()]
    return res

  def reset(self, seed=None, return_info=False, options=None):
    # shuffle the chronics from time to time (to change the order in which they are 
    # seen by the agent)
    if isinstance(self.init_env.chronics_handler.real_data, Multifolder):
      nb_chron = len(self.init_env.chronics_handler.real_data._order)
      if self.nb_reset % nb_chron == 1:
        self.init_env.chronics_handler.reset()
    return super().reset(seed, return_info, options)
  
  def fix_action(self, grid2op_action):
    # chose the best actio between do nothing and the proposed action
    _, sim_reward_act, _, _ = self.init_env.simulate(grid2op_action, 0)
    _, sim_reward_dn, _, _ = self.init_env.simulate(self.dn, 0)
    if sim_reward_dn >= sim_reward_act:
      res = self.dn
    else:
      res = grid2op_action
    return res
