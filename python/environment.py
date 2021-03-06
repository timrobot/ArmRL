import numpy as np
import simulation
import physx
import time
import math
#from gym import Env, EnvSpec

class EnvSpec:
  def __init__(self, timestep_limit=1000):
    self.max_episode_steps = timestep_limit

  @property
  def timestep_limit(self):
    return self.max_episode_steps

#class BasketballVelocityEnv(gym.Env):
class BasketballVelocityEnv:
  """
  State:  [7 joint angular positions,
           7 joint angular velocities,
           release]
  Action: [7 joint angular velocities,
           release]
  """
  def __init__(self, goal=np.array([5, 0, 0]), \
      initialAngles=np.zeros([7], dtype=np.float32), \
      initialLengths=np.array([0, 0, 1, 1, 1, 0, 1], dtype=np.float32),
      timeInterval=1.0, fps=30.0):
    self.lengths = np.array(initialLengths, dtype=np.float32)
    self.initial_state = np.concatenate([
      np.array(initialAngles, dtype=np.float32),
      np.zeros([8], dtype=np.float32)]) # angpos, angvel, release
    self.angles = self.initial_state.copy()
    self.goal = goal
    self.armsim = None
    self.ballsim = None
    self.time_render = None
    self.fps = fps
    self.iter = 0
    self.spec = EnvSpec()
    self.time_interval = timeInterval

  def reset(self):
    self.iter = 0
    self.angles = self.initial_state.copy()
    self.time_render = None
    return self.angles.copy()

  def step(self, action):
    actionRange = np.array(self.action_range(), dtype=np.float32)
    action = np.array(action, dtype=np.float32)
    action = np.minimum(
        np.maximum(action, actionRange[:, 0]), actionRange[:, 1])
    t = self.time_interval
    A = np.concatenate([np.eye(7), np.eye(7) * t, np.zeros([7, 1])], axis=1)
    # solve for the next position and velocity
    nextState = self.angles.copy()
    nextState[7:] = action
    nextState[:7] = (np.dot(A, np.array([nextState]).T).T)[0]
    stateRange = np.array(self.state_range(), dtype=np.float32)
    nextState = np.minimum(
        np.maximum(nextState, stateRange[:, 0]), stateRange[:, 1])
    # find reward and termination
    reward = self.rewardFn(nextState, action)
    done = self.terminationFn(nextState, action)
    self.angles = nextState
    self.iter += 1
    return nextState, reward, done, {}

  def render(self, mode="human", close=False):
    pos = physx.forwardKinematics(self.lengths, self.angles[:7])
    if self.armsim == None:
      self.armsim = simulation.Arm()
      self.armsim.default_length = self.lengths
    self.armsim.setPositions(pos)

    #if self.ballsim == None:
    #  self.ballsim = simulation.Ball()
    #pos0 = pos[-1, :]
    #self.ballsim.setPosition(pos0)

    t = time.time()
    if self.time_render == None or self.time_render <= t:
      self.time_render = t + 1.0 / self.fps
    else:
      time.sleep(self.time_render - t)
      self.time_render += 1.0 / self.fps
    """
    if self.terminationFn(self.angles, None):
      # only calculate the last position of the ball, send that over to sim
      p0 = physx.forwardKinematics(self.lengths, state[:7] - 0.005 * joints)
      p1 = physx.forwardKinematics(self.lengths, state[:7] + 0.005 * joints)
      vel = (p1[-1,:3] - p0[-1,:3]) / 0.01

      g = np.array([0, 0, -4.9]).reshape([-1, 1])
      pos1 = pos0
      dt = 1.0 / self.fps
      t0 = time.time()
      t1 = t0 + dt
      while pos1[2] > self.goal[2]:
        pos1 = pos0 + vel * dt + g * dt * dt
        self.ballsim.setPosition(pos1)
        t = time.time()
        if t1 <= t:
          t1 = t + dt
        else:
          time.sleep(t1 - t)
          t1 += dt
    """

  def close(self):
    if self.armsim != None:
      del self.armsim
      self.armsim = None
    if self.ballsim != None:
      del self.ballsim
      self.ballsim = None

  def seed(self, seed=None):
    pass

  def rewardFn(self, state, action):
    if state[-1] < 0.5:
      return 0.0

    # compute the final position and velocity
    joints = state[7:-1]
    pos = physx.forwardKinematics(self.lengths, state[:7])[-1, :]
    p0 = physx.forwardKinematics(self.lengths, state[:7] - 0.005 * joints)
    p1 = physx.forwardKinematics(self.lengths, state[:7] + 0.005 * joints)
    vel = (p1[-1,:3] - p0[-1,:3]) / 0.01

    # compute the time it would take to reach the goal (kinematics equations)
    g = -4.9
    vz = vel[2]
    dz = pos[2] - self.goal[2]
    # quadratic formula (+/- sqrt)
    # the parabola doesn't even reach the line
    b2_4ac = vz * vz - 4 * g * dz
    if b2_4ac < 0:
      return -1.0
    dt1 = (-vz + math.sqrt(b2_4ac)) / (2 * g)
    dt2 = (-vz - math.sqrt(b2_4ac)) / (2 * g)
    dt = max(dt1, dt2)
    # the ball would have to go backwards in time to reach the goal
    if dt < 0:
      return -1.0

    # find the distance from the goal (in the xy-plane) that the ball has hit
    dp = self.goal[:2] - (pos[:2] + vel[:2] * dt)

    # use euclidean distance with the diameter of the hoop
    return max(-1.0, 1.0 - 0.001 * np.sqrt(np.dot(dp, dp)))

  def terminationFn(self, state, action=None, nextState=None):
    return state[-1] >= 0.5 or self.iter >= self.spec.timestep_limit

  def state_range(self):
    return [(-180.0, 180.0),  # positions
            (-180.0, 180.0),
            (-180.0, 180.0),
            (-180.0, 180.0),
            (-180.0, 180.0),
            (-180.0, 180.0),
            (-180.0, 180.0),
            (-25.0, 25.0),    # velocities (max RPM)
            (-100.0, 100.0),
            (-50.0, 50.0),
            (-100.0, 100.0),
            (-25.0, 25.0),
            (-50.0, 50.0),
            (0.0, 0.0),
            (0.0, 1.0)]       # release

  def action_range(self):
    return [(-25.0, 25.0),    # velocities (max RPM)
            (-100.0, 100.0),
            (-50.0, 50.0),
            (-100.0, 100.0),
            (-25.0, 25.0),
            (-50.0, 50.0),
            (0.0, 0.0),
            (0.0, 1.0)]

  def __del__(self):
    self.close()
