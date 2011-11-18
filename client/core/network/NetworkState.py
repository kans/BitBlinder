#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Contains a bunch of functions for testing the state of our network connection.
Also stores that information for later use and debugging status messages."""

#TODO:  put this convention in our coding file--all booleans are really trinary values:
#True, False, and None, where None indicates that the value is currently unknown
#Implicitly, this means that the default value for any boolean is really False, 
#so consider that when naming them

#TODO:  rather than connecting with TCP a bunch of times for UDPBoundPortTest, just connect once, and send multiple messages?

#TODO: implement these
##test to see if we can get any incoming port to work, in case of blocking weird ports
#test_random_incoming_port()
##a test of 80/443, needs special work on linux to drop permissions, etc
#test_incoming_port(80)
#test_incoming_port(443)
##test if this process can bind any ports at all
#is_process_firewalled()

import time

from twisted.internet import defer, protocol
from twisted.names.client import getHostByName
from twisted.python import failure
from twisted.protocols.basic import Int32StringReceiver
from twisted.internet.error import CannotListenError, ConnectError
from twisted.internet.defer import TimeoutError

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Basic
from common.utils import Twisted
from common.classes.networking import EchoMixin
from common.classes.networking import MessageProtocol
from common.events import GlobalEvents
from core.tor import TorCtl
from core import ProgramState

#: how long to wait while connecting before we assume the test server is down, in seconds
CONNECTION_TIMEOUT = 7.5
#: how long before we assume that the test failed, in seconds
TEST_TIMEOUT = 15.0
#NOTE:  MUST be higher than CONNECTION_TIMEOUT for this to make any sense
assert TEST_TIMEOUT > CONNECTION_TIMEOUT
#: in seconds, time between sending requests
TEST_INTERVAL = 0.5
#: message to send back and forth to the server.  Change to random data, or no data, or tons of data (for bandwidth testing)
TEST_DATA = "HELLO"
#TODO:  allow there to be multiple test servers
TEST_SERVER_HOST = "174.143.240.110"
TEST_SERVER_PORT = 33351
  
_externalIP = None
_isTestServerReachable = None
_isProcessFirewalled = None
_isPort80Reachable = None
_isPort443Reachable = None
_isRandomPortReachable = None
_isPort80Bindable = None
_isPort443Bindable = None
_isUPnPAvailable = None
_isDNSWorking = None
_isUDPAllowed = None

def on_test_done(result, callback=None):
  if callback:
    try:
      callback(result)
    except Exception, e:
      log_ex(e, "Error during test callback: %s" % (callback))
  return result

def test_test_servers(callback=None):
  """Is the remote test server reachable?"""
  #start the test
  d = test_outgoing_port(TEST_SERVER_PORT, callback, TEST_SERVER_HOST)
  
  #add our callback
  def reachability_determined(isReachable):
    global _isTestServerReachable
    _isTestServerReachable = isReachable
    return isReachable
  d.addCallback(reachability_determined)

  return d
  
def test_outgoing_port(port, callback=None, testHost=None):
  if testHost is None:
    testHost = TEST_SERVER_HOST
    
  #make the test class
  factory = MessageProtocol.TCPMessageFactory("")
  
  #add our callbacks
  d = factory.get_deferred()
  d.addCallback(on_test_done, callback)
  def our_callback(result, port=port):
    if result is True:
      log_msg("Outgoing connection to port %s succeeded" % (port), 3)
    else:
      log_msg("Outgoing connection to port %s failed" % (port), 3)
    return result
  d.addCallback(our_callback)
  
  #and actually start the test
  Globals.reactor.connectTCP(testHost, port, factory, CONNECTION_TIMEOUT)
  return d
  
#TODO:  need a better list of outgoing ports.  Maybe get some from Tor?
def test_random_outgoing_port(callback=None, testHost=None):
  #try connecting to all authority server ports for now...
  deferreds = []
  for authority in ProgramState.Conf.AUTH_SERVERS:
    testHost = authority["address"]
    deferreds.append(test_outgoing_port(int(authority["orport"]), None, testHost))
    deferreds.append(test_outgoing_port(int(authority["dirport"]), None, testHost))
  
  #make the callbacks
  def all_test_done(results):
    global _isRandomPortReachable
    _isRandomPortReachable = False
    for test in results:
      if test[0] is True and test[1] is True:
        _isRandomPortReachable = True
    if _isRandomPortReachable is True:
      log_msg("Outgoing connection to random port succeeded", 3)
    else:
      log_msg("Outgoing connection to random port failed", 3)
    return _isRandomPortReachable
  deferredList = defer.DeferredList(deferreds)
  deferredList.addCallback(all_test_done)
  return deferredList
  
def test_dns(callback=None):
  """Can we lookup www.bitblinder.com and get a response?"""
  #resolve the address
  testAddress = "bitblinder.com"
  d = getHostByName(testAddress)
  
  #add our callbacks
  def dns_succeeded(address, testAddress=testAddress):
    log_msg("DNS for %s successfully resolved to %s" % (testAddress, address), 3)
    global _isDNSWorking
    _isDNSWorking = True
    return True
  d.addCallback(dns_succeeded)
  def dns_failed(reason, testAddress=testAddress):
    log_msg("DNS for %s failed: %s" % (testAddress, reason), 3)
    _isDNSWorking = False
    return False
  d.addErrback(dns_failed)
  
  return d

def test_network_state():
  try:
    #test network basics--are we firewalled, is dns working, are the test servers reachable?
    testServerDeferred = test_test_servers()
    test_dns()
    
    #then do the tests that require the test servers:
    
    #test outgoing ports
    d = test_outgoing_port(80)
    def is_port_80_reachable(isReachable):
      global _isPort80Reachable
      _isPort80Reachable = isReachable
      return isReachable
    d.addCallback(is_port_80_reachable)
    
    d = test_outgoing_port(443)
    def is_port_443_reachable(isReachable):
      global _isPort443Reachable
      _isPort443Reachable = isReachable
      return isReachable
    d.addCallback(is_port_443_reachable)
    
    test_random_outgoing_port()
    
    #test incoming connections
    test_udp()
    
    #what kind of speeds have we seen over this network?  upload vs download?
    #what interface should we be binding?
  except Exception, e:
    log_ex(e, "Error while testing network state")
    
def get_status():
  statusList = []
#  statusList.append(["_externalIP", _externalIP])
  statusList.append(["_isDNSWorking", _isDNSWorking])
  statusList.append(["_isUDPAllowed", _isUDPAllowed])
#  statusList.append(["_isProcessFirewalled", _isProcessFirewalled])
  statusList.append(["_isTestServerReachable", _isTestServerReachable])
  statusList.append(["_isRandomPortReachable", _isRandomPortReachable])
  statusList.append(["_isPort80Reachable", _isPort80Reachable])
  statusList.append(["_isPort443Reachable", _isPort443Reachable])
#  statusList.append(["_isPort80Bindable", _isPort80Bindable])
#  statusList.append(["_isPort443Bindable", _isPort443Bindable])
#  statusList.append(["_isUPnPAvailable", _isUPnPAvailable])
  statusString = ", ".join([":".join(str(r) for r in line) for line in statusList])
  return statusString
    
#REFACTOR:  I don't like the value "TCP_reply", etc
def test_incoming_port(port, callback, protocol="TCP"):
  """Make sure the port is properly bound and any required NAT forwarding is working"""
  #launch the actual test
  if protocol == "TCP":
    test = TestUnboundTCPPort(TEST_TIMEOUT)
  elif protocol == "TCP_reply":
    test = TestBoundTCPPort(TEST_TIMEOUT)
  elif protocol == "UDP":
    test = TestBoundUDPPort(TEST_TIMEOUT)
  else:
    raise NotImplementedError()
  d = test.start_test(port, TEST_SERVER_HOST, TEST_SERVER_PORT)
  
  #define the failure callback
  def _port_test_failure(reason):
    #is this one of the errors that corresponds to unreachability?
    if Basic.exception_is_a(reason, [CannotListenError, TimeoutError]):
      return False
    #otherwise, we do not know the state of reachability (None signals that)
    #and log the error if necessary
    unexpectedException = not Basic.exception_is_a(reason, [ConnectError])
    if unexpectedException:
      log_ex(reason, "Unexpected failure while testing port")
    return None
  d.addErrback(_port_test_failure)
  
  #add the success callbacks
  def port_test_done(result, port=port, protocol=protocol):
    if result is False:
      log_msg("Incoming port %s was NOT reachable with %s" % (port, protocol), 3)
      return False
    elif result is None:
      log_msg("Test servers appear to be down?", 1)
      return None
    else:
      log_msg("Incoming port %s was reachable with %s" % (port, protocol), 3)
      #NOTE:  this didnt work because result is a bool now  :(
#      global _externalIP
#      _externalIP = result
#      _update_ip(_externalIP, "TEST_SERVER")
      return True
  d.addCallback(port_test_done)
  d.addCallback(on_test_done, callback)
  
  return d
  
def test_udp(callback=None):
  """Can we send UDP messages and get replies?"""
  #start the test of UDP replies
  test = TestUDPReplies(TEST_TIMEOUT)
  udpDeferred = test.start_test(TEST_SERVER_HOST, TEST_SERVER_PORT)
  
  #define the failure callback
  def udp_test_failure(reason):
    if Basic.exception_is_a(reason, [TimeoutError]):
      return False
    log_ex(reason, "Unexpected failure while testing UDP")
    return None
  udpDeferred.addErrback(udp_test_failure)
  
  #add the success callbacks
  def udp_test_success(result):
    if result is True:
      log_msg("UDP replies are allowed in this network", 3)
    elif result is False:
      log_msg("UDP replies are NOT allowed in this network", 0)
      raise Exception("Found some network configuration that does NOT allow UDP replies, will not be suitable as a relay.")
    else:
      log_msg("Test servers are down?", 1)
    global _isUDPAllowed
    _isUDPAllowed = result
    return result
  udpDeferred.addCallback(udp_test_success)
  
  #also do a test of the test servers:
  testServerDeferred = test_test_servers()
  
  finalDeferred = defer.DeferredList([udpDeferred, testServerDeferred])
  def all_tests_done(results):
    bothResultsWereCallbacks = results[0][0] == True and results[1][0] == True
    if bothResultsWereCallbacks:
      udpTestFailed = results[0][1] == False
      testServerWasDown = results[1][1] == False
      #in this case, the state of the test is unknown
      if udpTestFailed and testServerWasDown:
        return None
    udpTestResult = results[0][1]
    return udpTestResult
  finalDeferred.addCallback(all_tests_done)
  finalDeferred.addCallback(on_test_done, callback)
  
  return finalDeferred
    
class TimeoutMixin:
  def __init__(self, timeout):
    self.timeout = timeout
    self.deferred = defer.Deferred()
    self.finished = False
    self.result = None
    self.timeoutEvent = Globals.reactor.callLater(timeout, self._on_timeout)
    
  def get_deferred(self):
    return self.deferred
      
  def succeed(self, result):
    if not self.finished:
      self.finished = True
      self.result = result
      d = self.on_done()
      def cleanup_finished(*args):
        self.deferred.callback(self.result)
      d.addCallback(cleanup_finished)
      self.cancel()
  
  def fail(self, reason):
    if not self.finished:
      self.finished = True
      self.result = reason
      d = self.on_done()
      def cleanup_finished(*args):
        self.deferred.errback(self.result)
      d.addCallback(cleanup_finished)
      self.cancel()
      
  def cancel(self):
    if not self.finished:
      self.finished = True
      self.on_done()
    if self.timeoutEvent and self.timeoutEvent.active():
      self.timeoutEvent.cancel()
    self.timeoutEvent = None
    
  def on_done(self):
    return defer.succeed("Cancelled")
      
  def _on_timeout(self):
    if not self.finished:
      self.fail(failure.Failure(defer.TimeoutError("Timed out")))
      
class ValidateDataMixin(TimeoutMixin):
  def __init__(self, timeout):
    TimeoutMixin.__init__(self, timeout)
    self.data = TEST_DATA
    
  def got_data(self, data):
    if self.data != data:
      self.fail(failure.Failure(AssertionError("Data recvd is not equal to test data:  %s != %s" % (data, self.data))))
    else:
      self.succeed(True)

class TCPTestProtocol(Int32StringReceiver, EchoMixin.EchoMixin):  
  def stringReceived(self, data):
    address = self.transport.getPeer()
    self.read_reply(data, address.host)
    
  def handle_reply(self, host, data):
    self.factory.got_data(data)
    self.transport.loseConnection()

  def connectionMade(self):
    self.factory.clientConnectionSucceeded(self)
    
#TODO:  untested
class TestUnboundTCPPort(protocol.ServerFactory, ValidateDataMixin):
  protocol = TCPTestProtocol
  
  def __init__(self, timeout):
    ValidateDataMixin.__init__(self, timeout)
    self.listener = None
    self.port = None
  
  def start_test(self, port, remoteHost, remotePort):
    self.port = port
    #listen for responses if necessary
    try:
      self.listener = Globals.reactor.listenTCP(port, self, interface="")
    except CannotListenError, e:
      self.cancel()
      return defer.fail(failure.Failure(e))

    #send off the request for a reply:
    self.outgoingProtocol = TCPTestProtocol()
    d = defer.Deferred()
    def on_connection_failed(reason):
      self.fail(reason)
    d.addErrback(on_connection_failed)
    outgoingFactory = protocol._InstanceFactory(Globals.reactor, self.outgoingProtocol, d)
    Globals.reactor.connectTCP(remoteHost, remotePort, outgoingFactory, CONNECTION_TIMEOUT)
    
    return self.get_deferred()
      
  def on_done(self):
    if self.listener:
      d = self.listener.stopListening()
      self.listener = None
    else:
      d = defer.succeed("done")
    return d
      
  def clientConnectionSucceeded(self, protocol):
    #if this is our outgoing protocol, send our message
    if protocol == self.outgoingProtocol:
      msg = protocol.write_request(self.data, "TCP", self.port)
      protocol.sendString(msg)
    #otherwise, wait for them to send a message and we'll handle it
    else:
      pass
    
class TestBoundTCPPort(protocol.ClientFactory, ValidateDataMixin):  
  protocol = TCPTestProtocol
  
  def __init__(self, timeout):
    ValidateDataMixin.__init__(self, timeout)
    self.port = None
  
  def start_test(self, port, remoteHost, remotePort):
    self.port = port
    #listen for responses if necessary
    d = self.get_deferred()
    
    #send off the request for a reply:
    Globals.reactor.connectTCP(remoteHost, remotePort, self, CONNECTION_TIMEOUT)
    return d
    
  def clientConnectionSucceeded(self, protocol):
    msg = protocol.write_request(self.data, "TCP_reply", self.port)
    protocol.sendString(msg)
    
  def clientConnectionFailed(self, connector, reason):
    self.fail(reason)
    
class UDPTestInterface(protocol.DatagramProtocol, EchoMixin.EchoMixin, ValidateDataMixin):  
  def __init__(self, timeout):
    ValidateDataMixin.__init__(self, timeout)
    self.listener = None
    self.nextSendEvent = None
    
  def start_test(self, port, remoteHost, remotePort):
    self.port = port
    self.remoteHost = remoteHost
    self.remotePort = remotePort
    d = self.get_deferred()
    try:
      self.listener = Globals.reactor.listenUDP(port, self, interface="")
    except CannotListenError, e:
      self.cancel()
      return defer.fail(failure.Failure(e))
    #send off the request for a reply:
    self.send_request()
    return d
    
  def send_request(self):
    raise NotImplementedError()
      
  def on_done(self):
    #stop the listener
    d = None
    if self.listener:
      d = self.listener.stopListening()
    if not d:
      d = defer.succeed("done")
    self.listener = None
    
    #stop the send event:
    if self.nextSendEvent and self.nextSendEvent.active():
      self.nextSendEvent.cancel()
    self.nextSendEvent = None
    
    return d

  def datagramReceived(self, datagram, address):
    if self.finished:
      return
    try:
      self.read_reply(datagram, address[0])
    except EchoMixin.BadEchoMessageFormat, e:
      log_msg("Got a bad UDP message (%s) while testing ports:  %s" % (e, repr(datagram)), 4)
    
  def handle_reply(self, host, data):
    self.got_data(data)
    
class TestBoundUDPPort(UDPTestInterface):
  def send_request(self):
    msg = self.write_request(self.data, "UDP", self.port)
    factory = MessageProtocol.TCPMessageFactory(msg)
    d = factory.get_deferred()
    def did_connection_complete(result):
      if result != True:
        self.fail(failure.Failure(ConnectError("Could not connect to test servers")))
    d.addCallback(did_connection_complete)
    Globals.reactor.connectTCP(self.remoteHost, self.remotePort, factory, CONNECTION_TIMEOUT)
    #and schedule the next request, if we're not done yet:
    if not self.finished:
      self.nextSendEvent = Globals.reactor.callLater(TEST_INTERVAL, self.send_request)
    
class TestUDPReplies(TimeoutMixin):
  class SingleUDPReplyTest(UDPTestInterface):    
    def start_test(self, remoteHost, remotePort):
      return UDPTestInterface.start_test(self, 0, remoteHost, remotePort)
      
    def send_request(self):
      msg = self.write_request(self.data, "UDP_reply", 0)
      self.transport.connect(self.remoteHost, self.remotePort)
      self.transport.write(msg)

  def __init__(self, timeout):
    TimeoutMixin.__init__(self, timeout)
    self.endTime = time.time() + timeout
    self.nextSendEvent = None
    
  def start_test(self, remoteHost, remotePort):
    self.remoteHost = remoteHost
    self.remotePort = remotePort
    #make the next test
    self.start_individual_test()
    #return the global deferred
    return self.get_deferred()
    
  def start_individual_test(self):
    #don't bother with a new test if we're done
    if self.finished:
      return
      
    #launch a new test:
    curTime = time.time()
    timeout = self.endTime - curTime
    if timeout <= 0:
      return
    test = self.SingleUDPReplyTest(timeout)
    d = test.start_test(self.remoteHost, self.remotePort)
    
    #handle results of the test:
    d.addCallback(self.succeed)
    def on_failure(reason):
      #is this an expected failure for a single UDP reply test?
      if Basic.exception_is_a(reason, [CannotListenError, ConnectError, TimeoutError]):
        return
      #otherwise, log the error
      log_ex(reason, "Unexpected failure while testing UDP replies")
    d.addErrback(on_failure)
    
    #schedule the next test:
    enoughTimeForMoreTests = curTime + TEST_INTERVAL < self.endTime
    if not self.finished and enoughTimeForMoreTests:
      self.nextSendEvent = Globals.reactor.callLater(TEST_INTERVAL, self.start_individual_test)

  def on_done(self):
    if self.nextSendEvent and self.nextSendEvent.active():
      self.nextSendEvent.cancel()
    self.nextSendEvent = None
    return defer.succeed("done")
    
def get_external_ip(bbApp):
  """Replies with the external IP address, or asks Tor for it and replies with None.
  In the second case, on_ip_update will be called when the IP address is learned."""
  if _externalIP:
    return _externalIP
  if not bbApp or not bbApp.is_tor_ready():
    return None
  def response(val):
    val = val["address"]
    _update_ip(val, "CONTROLLER")
  def error(failure):
    if issubclass(type(failure.value), TorCtl.ErrorReply):
      log_msg("Failed to get address from Tor, probably asking too early.  Oh well.")
    else:
      log_ex(failure, "Unhandled exception in get_external_ip")
  d = bbApp.torApp.conn.get_info("address")
  d.addCallback(response)
  d.addErrback(error)
  return None

def _update_ip(address, method):
  """Call this function when you learn about a new external IP address"""
  global _externalIP
  if not Twisted.is_local_ip(address):
    if not _externalIP:
      pass
    elif _externalIP != address:
      log_msg("%s reported a different external IP than we already knew about:  %s vs %s" % (method, Basic.clean(address), Basic.clean(_externalIP)), 3)
    else:
      return
    _externalIP = address
    GlobalEvents.throw_event("ip_update", address, method)
  else:
    log_msg("Learned about local address %s via %s, not very helpful..." % (Basic.clean(address), method), 4)
    