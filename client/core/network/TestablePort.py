#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Handles testing bound ports for reachability."""

from twisted.internet import protocol

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import Scheduler
from common.events import GeneratorMixin
from core.network import NetworkState

class TestablePort(GeneratorMixin.GeneratorMixin):
  #maximum number of times to try testing the port.  We try multiple times
  #b/c circuits can fail for other reasons than that our port is not forwarded.
  MAX_TESTS = 15
  #how much time to wait between failed tests:
  SECONDS_BETWEEN_TESTS = 15.0
  
  def __init__(self, bbApp, trafficType, isBound):
    """
    name = string describing this port (ie, the purpose)
    port = int port number to try forwarding
    """
    assert trafficType in ("TCP", "UDP")
    
    GeneratorMixin.GeneratorMixin.__init__(self)
    self._add_events("reachability_unknown", "reachable", "unreachable")
    
    self.trafficType = trafficType
    #: a pointer to the BitBlinder application (necessary for launching circuit tests)
    self.bbApp = bbApp
    #: the type of test to do (what type of traffic, and whether the port is bound.  See EchoMixin)
    self.portTestType = trafficType
    if isBound:
      self.portTestType += "_reply"
    #: have we started testing the port?
    self.testsStarted = False
    #: have we detected that the port is reachable yet?  Will be None if result is unknown, True or False otherwise
    self.reachable = None
    #: are we currently testing the reachability of the port?
    self.probeRunning = False
    #: the circuit with which we are testing reachability
    self.circ = None
    #: the number of times that we've tried to test the reachability of the port
    self.numProbes = 0
    #: number of times that we failed because the circuit didnt build.  Doesnt count towards MAX_TESTS
    self.circuitFailures = 0
    #: event representing the next time we'll try testing the port
    self.nextScheduledTest = None
    
  def start_test(self):
    if not self.testsStarted:
      self.testsStarted = True
      #try the server test
      NetworkState.test_incoming_port(self.port, self._on_server_test_done, self.portTestType)
  
  def get_last_known_status(self):
    """accessor function"""
    return self.reachable
    
  def _on_server_test_done(self, isReachable):
    #server says that we are definitely reachable
    if isReachable is True:
      self._on_reachable()
      return
      
    #server says that we are definitely NOT reachable
    if isReachable is False:
      self._on_unreachable(isReachable)
      return
      
    #if the server test wasnt very helpful, try a circuit test is this is TCP:
    if self.trafficType == "TCP":
      self._start_circuit_test()
      return
      
    #otherwise, count as being unreachable:
    self._on_unreachable(isReachable)
    
  def _start_circuit_test(self):
    try:
      #reset variables:
      self.ignoreExits = []
      self.successes = 0
      self.attempts = 0
      self.failures = 0
      self.numProbes = 0
      self.circuitFailures = 0
      self.nextScheduledTest = None
      self.reachable = False
      self._start_probe()
    except Exception, error:
      log_ex(error, "Failed to start UPNP probe")
        
  def _schedule_next_test(self):
    self.nextScheduledTest = Scheduler.schedule_once(self.SECONDS_BETWEEN_TESTS, self._start_probe)
    
  def _start_probe(self):
    """Try to start up the external connection over some circuit to connect to ourselves"""
    #log_msg("start_probe", 4)
    if not self.probeRunning and self.testsStarted and not self.reachable:
      #log_msg("launch?", 4)
      #if we dont yet know our real IP address:
      if not NetworkState.get_external_ip(self.bbApp):
        #log_msg("no external ip  :(", 4)
        #then we should try back later
        #TODO:  not perfect, we're basically polling for an external IP (which comes from Tor sometimes)
        #the Twisted way would be to have some sort of deferred or callback or something.
        self._schedule_next_test()
        return
      if not self.bbApp.is_ready():
        self._schedule_next_test()
        return
      #find a circuit if we dont have one already or it is broken
      if not self.circ or self.circ.is_done():
        self.circ = self.bbApp.build_circuit(NetworkState.get_external_ip(self.bbApp), self.port, isFast=None, force=True, ignoreExits=self.ignoreExits)
      #if we cant find any suitable circuits
      if not self.circ:
        #try some of the relays that we tried before and failed with
        self.ignoreExits = []
        self.circ = self.bbApp.build_circuit(NetworkState.get_external_ip(self.bbApp), self.port, isFast=None, force=True, ignoreExits=self.ignoreExits)
      #if we STILL cant find any circuits:
      if not self.circ:
        #postpone the probe:
        log_msg("Delaying the PortTest probe due to lack of suitable circuits", 1)
        self._schedule_next_test()
        return
#      #dont send payments, since we dont actually care about this circuit, and it will be closed when we've started up
      self.circ.sendPayments = False
      #launch the connection
      self.probeRunning = True
      self.numProbes += 1
      self._handle_launch()
      
  def _handle_launch(self):
    """Actually launch the externally proxied connection to our forwarded port"""
    log_msg("Testing our %s through %s" % (self.name, self.circ.get_exit().desc.idhex))
    self.bbApp.launch_external_protocol(NetworkState.get_external_ip(self.bbApp), self.port, ProbeProtocol(self), self.circ.handle_stream, self._connection_failed, "%sTest" % (self.name))
    
  def _connection_failed(self, failure, *args, **kwargs):
    """Handle a probe failure (failure to connect to our supposedly forwarded port via external proxy)"""
    log_msg("Port test failed to connect:  %s" % (failure), 1)
    self.probeRunning = False
    self.ignoreExits.append(self.circ.get_exit())
    if not self.nextScheduledTest or not self.nextScheduledTest.active():
      #dont count as a failure if the circuit is the thing that failed, not the connection:
      if self.circ.status != "BUILT":
        self.circuitFailures += 1
      #otherwise, make sure we get a new circuit to try with
      else:
        self.circ.close()
        self.circ = None
      #dont retry more than self.MAX_TESTS times in a row:
      if self.numProbes - self.circuitFailures < self.MAX_TESTS:
        self._schedule_next_test()
      else:
        log_msg("Retried self testing of reachability too many times, stopping.", 1)
        self._on_unreachable(False)
    
  def _on_protocol_built(self):
    """Called when a ProbeProtocol instance connects successfully"""
    log_msg("I guess we connected successfully...", 2)
    self._on_reachable()
    
  def _on_test_done(self):
    """Called when testing is all done"""
    self.testsStarted = False
    self.probeRunning = False
    
  def _on_reachable(self):
    """Called when we have determined that we are reachable"""
    self.reachable = True
    self._on_test_done()
    self.on_reachable()
    self._trigger_event("reachable")
  
  def _on_unreachable(self, reachabilityResult):
    """Called when we have determined that we are unreachable
    @param reachabilityResult:  False (if definitely unreachable), or None (if state is really unknown but we cant test anymore)"""
    self.reachable = reachabilityResult
    self._on_test_done()
    self.on_unreachable(reachabilityResult)
    if reachabilityResult == False:
      self._trigger_event("unreachable")
    else:
      self._trigger_event("reachability_unknown")
  
  def on_reachable(self):
    """Override to handle the event that the port is found to be reachable"""
    return
  
  def on_unreachable(self, reachabilityResult):
    """Override to handle the event that the port is found to be unreachable
    @param reachabilityResult:  False (if definitely unreachable), or None (if state is really unknown but we cant test anymore)"""
    return
  
  def stop_test(self):
    """Unbind the UPNP port and cancel any currently running or scheduled tests"""
    if self.nextScheduledTest and self.nextScheduledTest.active():
      self.nextScheduledTest.cancel()
    self.nextScheduledTest = None

class ProbeProtocol(protocol.Protocol):
  """Extremely basic protocol.  Just connects, and informs client of success or failure"""
  def __init__(self, client):
    """client = TestableUPNPPort instance to handle results"""
    self.client = client
    
  def connectionMade(self):
    """Inform the TestableUPNPPort that we successfully connected, and close the connection"""
    self.client._on_protocol_built()
    self.transport.loseConnection()
    