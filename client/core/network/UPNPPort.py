#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Requests traffic be forwarded to a port via UPnP (if available)"""

import re
import os

from twisted.internet import utils
from twisted.internet import defer

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Twisted
from common.system import System

class UPNPPort():
  """Handle UPNP forwarding and closing for a given port.
  Create the class, call start() to bind, stop() to unbind the port.
  Override upnp_succeeded and/or upnp_failed to handle result of attempting to bind"""
  upnpcEnabled = None
  upnpcTested = False
  def __init__(self, name, port, trafficType="TCP"):
    """
    name = string describing this port (ie, the purpose)
    port = int port number to try forwarding
    """
    #: string describing the purpose of this port
    self.name = name
    #: what type of traffic to forward (TCP or UDP)
    self.trafficType = trafficType
    #: port number to try forwarding
    self.port = port
    #: whether the UPNP program has been started yet
    self.startedUPNP = False
    #: whether UPNP succeeded
    self.usedUPNP = False
    if System.IS_WINDOWS:
      self.upnpcPath = os.path.join(Globals.WINDOWS_BIN, "upnp", "upnpc-static.exe")
      self.workingDir = os.path.join(Globals.WINDOWS_BIN, "upnp")
    else:
      self.upnpcPath = u"upnpc-static"
      self.workingDir = os.getcwd().decode('utf-8')
    #: the path to the upnp binary
    self.upnpcPath = System.encode_for_filesystem(self.upnpcPath)
    #: the path to the working directory for our binary
    self.workingDir = System.encode_for_filesystem(self.workingDir)
  
  def _test_upnpc(self):
    """tests to see if we can call upnpc-static
    this is mainly needed for the linux echosystem where some users will install from source, 
    and perhaps will not install or properly link the binary"""
    UPNPPort.upnpcTested = True
    results = self._start_upnp_exe("")
    def test_results(resultsString):
      if "miniupnpc library test client" in resultsString:
        log_msg("upnpc-static found and working!", 2)
        UPNPPort.upnpcEnabled = True
      log_msg("upnpc-static was not found or is not working: returned:\n%s" % (resultsString), 0)
      UPNPPort.upnpcEnabled = False
    results.addCallback(test_results)
    
  def get_port(self):
    return self.port
    
  def get_name(self):
    return self.name
    
  def start_upnp(self):
    """Start the attempt to forward the port.  This function is idempotent."""
    if not self.startedUPNP:
      self.startedUPNP = True
      #try to set the new ports for Tor:
      try:
        #try forwarding the new port from the router:
        self._upnp_request()
      except Exception, error:
        log_ex(error, "Failed to start UPNP")
        
  def _on_upnp_done(self):
    self.startedUPNP = False
    self.on_upnp_done()
    
  def upnp_succeeded(self, externalIPAddress):
    """Called when upnp finished successfully"""
    self._on_upnp_done()
    self.usedUPNP = True
    self.on_upnp_succeeded(externalIPAddress)
  
  def upnp_failed(self, failure):
    """Called when upnp finishes and failed"""
    self._on_upnp_done()
    self.usedUPNP = False
    self.on_upnp_failed(failure)
        
  def on_upnp_succeeded(self, externalIPAddress):
    """Override this function to handle UPNP success however you want
    ip = the external ip address, returned by the router on success"""
  
  def on_upnp_failed(self, failure):
    """Override this function to handle UPNP failure however you want
    failure = reason for failure (an exception, Failure, or string)"""
    
  def on_upnp_done(self):
    """This is called after UPnP has finished, one way or another"""
  
  #TODO:  not really sure how well this will work if called while the outside program is running
  def stop_upnp(self):
    """Call to unbind the port via UPNP"""
    #if we previously had successfully bound the port
    if self.usedUPNP:
      #undo that binding:
      stopDeferred = self._remove_upnp()
      #make sure that the binding is removed before shutting down:
      return stopDeferred
    return defer.succeed(True)
    
  def _start_upnp_exe(self, args):
    output = utils.getProcessOutput(self.upnpcPath, args=args, path=self.workingDir)
    return output

  def _upnp_request(self):
    """Actually start the program to do the UPNP forwarding"""
    try:
      #figure out our local IP address
      localIP = Twisted.get_lan_ip()
      #start the external UPNP forwarding program
      output = self._start_upnp_exe(("-m", localIP, "-a", localIP, str(self.port), str(self.port), self.trafficType))
      #handle results
      output.addCallback(self._upnp_response)
      output.addErrback(self.upnp_failed)
    except Exception, error:
      log_ex(error, "Failed to send UPNP request")
      self.upnp_failed("Never even sent the request  :(")
      
  def _upnp_response(self, response):
    """Checks to see if the UPNP program really succeeded.
    response = output of UPNP program"""
    #check if it successfully bound the port:
    regex = re.compile(".*external (.+?):(.+?) %s is redirected to internal (.+?):([0-9]+).*" % (self.trafficType), re.DOTALL | re.IGNORECASE)
    match = regex.match(response)
    if match:
      self.upnp_succeeded(match.group(1))
      return
    #otherwise we failed
    self.upnp_failed("UPNP program output:\n%s" % (response))
      
  def _remove_upnp(self):
    """Actually call the outside program to remove the UPNP binding.  Returns a
    deferred that will be triggered when the port binding has finished (either
    successfully or unsuccessfully)"""
    #failures just get printed out, because we cant really do anything about them
    def handle_failure(failure):
      log_msg("Failed to remove UPNP mapping on shutdown:  %s" % (failure), 1)
    try:
      #figure out our local IP address
      localIP = Twisted.get_lan_ip()
      #launch the program
      output = self._start_upnp_exe(("-m", localIP, "-d", str(self.port), self.trafficType))
      #handle results
      output.addCallback(self._upnp_removed)
      output.addErrback(handle_failure)
      return output
    except Exception, error:
      log_ex(error, "Failed send request to remove UPNP")
      handle_failure("Never even sent the request  :(")
      
  def _upnp_removed(self, response):
    """Checks if the UPNP unbind operation succeeded
    response = string output of the external program"""
    regex = re.compile(".*UPNP_DeletePortMapping\(\) returned : ([0-9]+).*", re.DOTALL | re.IGNORECASE)
    match = regex.match(response)
    if match:
      #success!
      if match.group(1) == "0":
        log_msg("Removed UPNP mapping for %s port %s" % (self.trafficType, self.port), 3)
        return True
      if match.group(1) == "714":
        log_msg("UPNP mapping for %s port %s was already gone" % (self.trafficType, self.port), 3)
        return True
    #will be caught be errback above
    raise Exception("UPNP program output:\n%s" % (response))
    
