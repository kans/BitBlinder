#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Application class wrapper for Tor"""

import os
import re
import time
import random
import struct
import copy
import types
import warnings
import socket

from twisted.internet import defer
from twisted.internet import utils
from twisted.internet.error import ConnectionDone, ConnectionLost
from common.classes.networking import SpawnProcess
from twisted.internet.abstract import isIPAddress

try:
  import win32process
except ImportError:
  pass

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import TorUtils
from common.utils import Basic
from common.system import System
from common.system import LaunchProcess
from common.system import Process
from common.events import GlobalEvents
from common.events import ListenerMixin
from common.classes import PublicKey
from common.classes import Scheduler
from common import Globals
from core.tor import ServerPaymentHandler
from core.tor import TorMessages
from core.tor import TorCtl
from core.tor import EventHandler
from core.tor import Relay
from core.network import dht
from core.network import ForwardedPort
from core.bank import Bank
from core import ClientUtil
from core import ProgramState
from gui import GUIController
from Applications import BitBlinder
from Applications import Application
from Applications import Settings
  
#: for matching data from descriptors
EXIT_POLICY_REGEX = re.compile(r"^(\S+):([^-]+)(?:-(\d+))?")
PLATFORM_REGEX = re.compile(r"^Tor (\S+).*on (\S+)")
RELAY_HEX_ID_RE = re.compile(r"^[A-F0-9]{40}$")
#: what's the lowest relaybwrate that we will allow?
MIN_BW_RATE = 21
#: if there are FEWER than this many relays that will exit to a given address, and we allow exits there, allow our own relay as an exit:
RARE_EXIT_POLICY_CUTOFF = 4

_instance = None
def get():
  return _instance
  
def start():
  global _instance
  if not _instance:
    _instance = Tor()

class TorSettings(Settings.Settings):
  """Settings class for Tor.  Responsible for generating the tor.conf file
  Also handles applying settings while Tor is running."""
  #: filename for saving the settings file
  defaultFile = "torSettings.ini"
  #: name to show in the Settings dialog
  DISPLAY_NAME = "Relay"
  def __init__(self):
    """Add defaults, values, ranges, etc for all Tor settings that we care about"""
    Settings.Settings.__init__(self)
    try:
      #Just make a random name because we dont want to give anything away about this computer
      name = os.urandom(8).encode("hex").upper()
    except:
      name = "Unnamed"
      
    self.beRelay = self.add_attribute("beRelay", False, "bool", "Be a relay?", "You must turn this on to earn credits for BitBlinder!")
    self.wasRelay = self.add_attribute("wasRelay", False, "bool", "Have you ever been a relay before", "For internal use, deciding when to show settings.", isVisible=False)
    self.promptedAboutRelay = self.add_attribute("promptedAboutRelay", False, "bool", "Did we ask you about being a relay yet?", "For internal use, deciding when to show settings.", isVisible=False)
    self.completedServerSetup = self.add_attribute("completedServerSetup", False, "bool", "Did you complete the server setup dialog and forward the OR port successfully?", "For internal use, deciding when to show settings.", isVisible=False)
    self.monthlyCap = self.add_attribute("monthlyCap", 0, "GB", "Monthly Bandwidth Cap", "Use this option to prevent Tor from using more than the given number of GB in a single month.  Useful if your ISP limits your connection (sadness).  0 means unlimited.")
    self.bwRate = self.add_attribute("bwRate", 2000, "KBps", "Relayed Rate Limit", "Prevent relayed traffic from using more than this many KB per second, on average.  If you want to limit your contribution to the network, please use the above option instead of this one if you can.  0 means unlimited.")
    self.bwSchedule = self.add_attribute("bwSchedule", '', "scheduler", "Bandwidth Scheduler", "Limit the amount of Internet traffic sent by the server based on the time of day during the week.")
    self.name = self.add_attribute("name", name, r"^[a-zA-Z0-9]{3,20}$", "Relay Name", "The name of your Tor relay.  This is the name that other people will see when they send traffic through your relay.")
    self.orPort = self.add_attribute("orPort", Globals.TOR_DEFAULT_OR_PORT, (1, 65535), "OR Port", "You MUST forward this port (or enable UPnP) in your router!  It must be open if you want to be a relay.  BitBlinder uses this port to connect securely to other people's computers.")
    self.dhtPort = self.add_attribute("dhtPort", Globals.TOR_DEFAULT_OR_PORT, Globals.PORT_RANGE, "DHT Port", "This allows you to participate in DHT on behalf of other users (to help them find peers).  You must forward UDP traffic for this port if it is enabled (set 0 to disable)")
    self.dirPort = self.add_attribute("dirPort", Globals.TOR_DEFAULT_DIR_PORT, Globals.PORT_RANGE, "Directory Port", "Forwarding this port helps distribute network information to other BitBlinder users and helps take the load off of the central servers.")
    self.socksPort = self.add_attribute("socksPort", Globals.TOR_DEFAULT_SOCKS_PORT, Globals.PORT_RANGE, "SOCKS Port", "Configure your applications to use this port as the SOCKS proxy port (and 127.0.0.1 as the SOCKS host)")
    self.controlPort = self.add_attribute("controlPort", Globals.TOR_DEFAULT_CONTROL_PORT, (1, 65535), "Control Port", "InnomiTor and BitBlinder communicate using this port", isVisible=False)
    self.address = self.add_attribute("address", "", "ip", "IP Address", "Only use this option if you have a very strange network setup, and the outgoing IP address is not being correctly detected by Tor.")
    self.assumeReachable = self.add_attribute("assumeReachable", False, "bool", "Skip self-testing for reachability?", "This should basically only be used by the developers.  Setting this to true means that you might not be informed of problems with your firewall!", category="DEV", isVisible=ProgramState.DEBUG)
    self.exitType = self.add_attribute("exitType", "Both", ("Both", "BitTorrent", "Web", "None"), "Exit traffic allowed", 
"""By default, BitBlinder allows peers to send Internet traffic from your computer.  This means that you might have to deal with abuses or complaints.  

If you do not want to ever have to defend free speech while using BitBlinder, select None for the exit type.  In this mode, there is zero risk of abuse while running BitBlinder, but you will gain credits very slowly.

You can also restrict the traffic to a certain type (to only allow web browsing or BitTorrent traffic from other users to come from your computer)
""")
    return
    
  def get_bw_rate(self):
    """Figure out the current bw for this hour.
    @return:  the number of KBps, or None if unlimited"""
    vals = time.localtime()
    hour = vals[3]
    rate = self.bwRate
    if self.bwSchedule:
      #figure out the value
      days, limits = self.bwSchedule.rsplit("||", 1)
      days = days.split("|")
      day = days[vals[6]]
      hours = day.split(',')
      hour = hours[vals[3]]
      #full speed
      if hour == '0':
        rate = self.bwRate
      #limited speed:
      elif hour == '1':
        #get the rates for this hour
        upRate, downRate = limits.split(',')
        upRate = int(upRate)
        downRate = int(downRate)
        
        #use the lowest rate as the cap, since we're a proxy, so we have to upload anything we download and vice versa
        rate = min(upRate, downRate)
        
        #and make sure the rate is high enough for us to still be a valid relay
        if rate < MIN_BW_RATE:
          rate = MIN_BW_RATE
      #off:
      elif hour == '2':
        rate = None
      else:
        raise Exception("Unexpected value for this hour:  %s" % (hour))
#    #0 means unlimited, None means disable
#    if rate == 0:
#      rate = 5000
    return rate
  
  #TODO:  have to prevalidate Tor input now, since the results are deferred...
  def on_apply(self, app, category):
    # pylint: disable-msg=C0111
    if category == "":
      #check that no ports are duplicated:
      allPorts = [self.orPort, self.dirPort, self.controlPort, self.socksPort]
      for port, portName in ((self.orPort, "ORPort"), (self.dirPort, "Dir Port"), (self.controlPort, "Control Port"), (self.socksPort, "SOCKS Port")):
        if allPorts.count(port) > 1:
          #inform the user
          GUIController.get().show_msgbox("Tor %s was set to the same value (%s) as another port!  Reverting to default ports." % (portName, port))
          #then reset to safe values:
          self.orPort = self.defaults["orPort"]
          self.dirPort = self.defaults["dirPort"]
          self.controlPort = self.defaults["controlPort"]
          self.socksPort = self.defaults["socksPort"]
          #and we're done:
          break
      #check that bwRate is high enough:
      if self.bwRate < MIN_BW_RATE:
        GUIController.get().show_msgbox("Bandwidth rate must be at least %s KBps, was %s" % (MIN_BW_RATE, self.bwRate))
        self.bwRate = MIN_BW_RATE
      #if we're a server, note that we have been a server before (now) in the settings to avoid prompts
      if self.beRelay:
        self.wasRelay = True
      app.forward_ports()
      GlobalEvents.throw_event("settings_changed")
      #TODO:  this is wrong, wont apply while you are starting up
      if not app.is_ready():
        return True
      try:
        options = self.generate_text()
        options = "SETCONF %s\r\n" % (options)
        app.set_options(options)
      except Exception, error:
        log_ex(error, "Failed to apply settings:")
        return False
    return True
    
  def get_data_directory(self):
    """@returns: string (path where Tor will store its data)"""
    return os.path.join(os.getcwdu(), Globals.USER_DATA_DIR, u"tor_data")
  
  def get_relay_torrc_data(self):
    """Create the data for tor.conf  
    @return: a string of the settings, formatted correctly"""
    defaultOptions = copy.copy(Globals.TORRC_DATA) + [
      #email for reporting abuse
      ("ContactInfo", "abuse@mail.bitblinder.com"),
      #Do not try to use entry guards for now, network is too unstable
      ("UseEntryGuards", "0"),
      #let circuits get very dirty for now, otherwise people have to make lots of payments
      ("MaxCircuitDirtiness", "60 minutes"),
      #Want warnings about bad protocol info in the logs
      ("ProtocolWarnings", "1"),
      #no need for Tor predicted circuits, we make our own:
      ("__DisablePredictedCircuits", "1"),
      #this means that we are responsible for attaching any and all streams to circuits
      ("__LeaveStreamsUnattached", "1"),
      #we want Tor to die unless we periodically send KEEPALIVE events to it
      ("RequiresKeepAlives", "1"),
      #what port to open for local application connections
      ("SocksPort", str(self.socksPort)),
      #accept connections only from localhost
      ("SocksListenAddress", "127.0.0.1"),
      #the port on which to send commands to Tor
      ("ControlPort", str(self.controlPort)),
      #whether to create test circuits for measuring bw I think
      ("RunTesting", "1"),
      ("DataDirectory", System.encode_for_filesystem(self.get_data_directory())),
      #based on the password for connecting to Tor
      ("HashedControlPassword", "16:DE37EC9567C1D89D60648F805A61527C9AA6C211EDAE5DA5A9A0F14FE6"), 
      #For IP resolves\
      ("GeoIPFile", System.encode_for_filesystem(os.path.join(os.getcwdu(), Globals.DATA_DIR, "ip-to-country.csv")))]
    defaultOptions += [("Log", "debug file %s" % (System.encode_for_filesystem(os.path.join(os.getcwdu(), Globals.LOG_FOLDER, 'tor.out'))))]
    if self.exitType == "Both":
      defaultOptions += copy.copy(Globals.DEFAULT_EXIT_POLICY_ALL)
    elif self.exitType == "None":
      defaultOptions += copy.copy(Globals.DEFAULT_EXIT_POLICY_NONE)
    elif self.exitType == "BitTorrent":
      defaultOptions += copy.copy(Globals.DEFAULT_EXIT_POLICY_BITTORRENT)
    elif self.exitType == "Web":
      defaultOptions += copy.copy(Globals.DEFAULT_EXIT_POLICY_WEB)
    else:
      raise Exception("Bad value for exitType:  %s" % (self.exitType))
    torrcData = self.generate_text("\n", " ", defaultOptions)
    torrcData = TorUtils.make_auth_lines(ProgramState.Conf.AUTH_SERVERS) + torrcData
    torrcData = "#DO NOT MODIFY THIS FILE, IT IS AUTOMATICALLY GENERATED!\n" + torrcData
    return torrcData
  
  def generate_text(self, lineSeparator=" ", entrySeparator="=", baseOptions=None):
    """Create a string from your own options and baseOptions.
    @param lineSeparator: used to separate options from one another
    @type lineSeparator: str
    @param entrySeparator: used to separate option names from their values
    @type entrySeparator: str
    @param baseOptions:  the additional options (not defined in our Settings class) to include in the string
    @type baseOptions:   list of (name, value) tuples"""
    if not baseOptions:
      baseOptions = []
    options = copy.copy(baseOptions)
    bwRate = self.get_bw_rate()
    options.append(("Nickname", self.name))
    if self.beRelay:
      if bwRate == None:
        options.append(("ORPort", "0"))
      else:
        options.append(("ORPort", str(self.orPort)))
      options.append(("DirPort", str(self.dirPort)))
    else:
      options.append(("ORPort", "0"))
      options.append(("DirPort", "0"))
    if self.monthlyCap:
      options.append(("AccountingMax", '"%s GB"' % (self.monthlyCap)))
    if bwRate != None:
      options.append(("RelayBandwidthRate", '"%s KB"' % (bwRate)))
      options.append(("RelayBandwidthBurst", '"%s KB"' % (bwRate * 2)))
    if self.assumeReachable:
      options.append(("AssumeReachable", '1'))
    if self.address != "":
      options.append(("Address", self.address))
    return lineSeparator.join(entrySeparator.join([str(x), str(y)]) for x, y in options)

class Tor(Application.Application, ListenerMixin.ListenerMixin):
  """Application wrapper for Tor.  Can be started, stopped, tracks circuits, etc"""
  def __init__(self):
    """Tor Application constructor"""
    Application.Application.__init__(self, "Tor", TorSettings, "The anonymizing network program")
    #TODO:  Application should really inherit from ListenerMixin, not here
    ListenerMixin.ListenerMixin.__init__(self)
    #update the gui about a port
    self._add_events("server_started", "server_status", "server_stopped", "ip_update")
    #: Handles the callbacks from TorCtl
    self.eventHandler = None
    #: Set by EventHandler during it's constructor
    self.conn = None
    #: dictionary mapping from desc.hexid -> obj for all Relays
    self.relays = {}
    #: process ID for Tor (so we can shut it down when we quit, or at will)
    self._set_tor_id(0)
    #: will be triggered when Tor finishes starting up and is ready to use.  Is None when Tor is not in the process of starting up
    self.startupDeferred = None
    #: whether Tor has finished bootstrapping:
    self.isReady = False
    #: whether we are definitely in the consensus or not.
    self.inConsensus = None
    #: set when Tor is first launched
    self.settingsFileName = None
    #: whether we've already tried relaunching Tor by resetting the settings:
    self.alreadyResetSettings = False
    #: to help debug when Tor doesnt start correctly:
    self.alreadyCapturedTorOutput = False
    #TODO:  yeah, this is a little silly...
    self.torApp = self
    #: the forwarded ports that we require (orPort and dirPort)
    self.orPort = None
    self.dirPort = None
    #: our DHT node for clients to use if they want us to get peers on their behalf
    self.dhtPort = None
    #: version number of Tor (according to Tor project)
    self.torVersion = "0.2.2.0-alpha-dev"
    #: version number of innomitor (which build of ours it is)
    self.innomitorVersion = "0.4.9"
    #: the next time _set_bw_from_schedule is called
    self.nextBWUpdateEvent = None
    #: the process id of the Tor process to which we are connected/connecting
    self.torId = 0
    #: how many ports need to be opened before we connect to Tor?
    self.numPortsNecessary = 0
    #: of those, how many are open already?
    self.numPortsReady = 0
    #: for when clients make OR Circuits through us
    self.orCircuits = {}
    #: the public keys of other relays and clients:
    self.relayKeys = {}
    #: if is_server, the time that we were most recently marked as reachable, otherwise, None
    self.relayReachableTime = None
    #: whether your descriptor has ever been accepted by the authority servers
    self.descriptorAccepted = True
    #: did we ever successfully connect to Tor?
    self.connectedSuccessfully = False
    
  def get_status(self):
    statusString = Application.Application.get_status(self)
    if self.is_running():
      statusString += " torId=%s isServer=%s" % (self.torId, self.is_server())
    return statusString
    
  def forward_ports(self):
    """Handle starting and stopping forwarded ports"""
    
    #if you are not a relay, you have no forwarded ports, so just return
    if not self.settings.beRelay:
      self.stop_forwarded_port("orPort")
      self.stop_forwarded_port("dirPort")
      self.stop_forwarded_port("dhtPort")
      return
      
    #otherwise, stop all old and start all new ports
    bbApp = BitBlinder.get()
    orPort = ForwardedPort.ForwardedPort("orPort", self.settings.orPort, bbApp)
    self.start_forwarded_port(orPort)
    self._start_listening_for_event("reachable", self.orPort, self._on_orport_reachable)
    self._start_listening_for_event("unreachable", self.orPort, self._on_orport_unreachable)
    dirPort = ForwardedPort.ForwardedPort("dirPort", self.settings.dirPort, bbApp)
    self.start_forwarded_port(dirPort)
    #check if we're supposed to be a DHT node:
    if self.settings.dhtPort != 0:
      dataFileName = os.path.join(self.settings.get_data_directory(), u"remote_dht.table")
      newDHTPort = dht.Port.DHTPort("dhtPort", self.settings.dhtPort, bbApp, dataFileName)
      self._start_listening_for_event("started", newDHTPort, self._on_dht_started)
      self._start_listening_for_event("stopped", newDHTPort, self._on_dht_stopped)
      self.start_forwarded_port(newDHTPort)
    else:
      self.stop_forwarded_port("dhtPort")
      
  def _on_orport_reachable(self, orPort):
    if orPort == self.orPort:
      self.relayReachableTime = time.time()
    
  def _on_orport_unreachable(self, orPort):
    if orPort == self.orPort:
      self.relayReachableTime = None
      
  def get_all_port_status(self):
    """returns the status of all relay related ports"""
    #query ports for their status
    portStatus = {}
    for port in [self.dhtPort, self.dirPort, self.orPort]:
      if port:
        number = port.port
        status = port.get_last_known_status()
        portStatus[port.name] = [status, number]
    return portStatus
  
  def get_relay_status(self):
    #are we even configured to be a relay?
    if not self.is_server():
      return (None, _("Not a relay"))
    if not self.orPort:
      return (None, _("No relay port yet"))
      
    #are we still testing reachability?
    reachable = self.orPort.get_last_known_status()
    if reachable == None:
      return (None, _("Testing..."))
      
    #is our port known to be unreachable?
    reachable = self.orPort.get_last_known_status()
    if reachable == False:
      return (False, _("Relay port is unreachable!"))
      
    #this shouldnt be very frequent:
    if not self.descriptorAccepted:
      return (True, _("Waiting for Tor to upload our descriptor..."))
      
    #are we still waiting to be in the consensus?
    if self.inConsensus != True:
      timeLeft = self._get_estimated_time_until_in_consensus()
      minutesLeft = (int(timeLeft) / 60) + 1
      return (True, _("%s minutes until we are in the consensus" % (minutesLeft)))
    
    #have we earned any credits recently?
    if self._has_earned_credits_recently():
      return (True, _("Earning credits!"))
    else:
      return (True, _("Waiting for traffic from other users..."))
      
  def on_server_status(self, status, address=None, reason=None):
    log_msg("%s %s %s" % (status, address, reason), 1)
    if status == "ACCEPTED_SERVER_DESCRIPTOR":
      self.descriptorAccepted = True
    self._trigger_event("server_status", status, address, reason)
      
  #TODO:  make this more accurate--we know when we got the last consensus, we 
  #can probably trigger retrieval of a new consensus, we know when Tor learned 
  #that it was reachable and uploaded the descriptor, as well as the configured 
  #cutoffs for the auth servers
  def _get_estimated_time_until_in_consensus(self):
    """approximated as time since we learned that we were reachable, plus a few consensus interval times
    @returns:  the time until you should be visible to other relays, or None if that cannot be known (presumably because your relay isnt completely set up yet)"""
    if self.relayReachableTime == None:
      return None
    numIntervals = 3
    waitTime = numIntervals * ProgramState.Conf.INTERVAL_MINUTES * 60.0
    consensusETA = self.relayReachableTime + waitTime
    timeLeft = consensusETA - time.time()
    if timeLeft <= 0:
      timeLeft = 0.0
    return timeLeft
    
  def _get_relay_reachable_time(self):
    return self.relayReachableTime
    
  def on_entered_consensus(self):
    self.inConsensus = True
    
  #TODO:  properly stop/start the ports here to re-test for reachability
  def on_exited_consensus(self):
    self.inConsensus = False
    
    #NOTE:  not sure whether to set this--we might have been down temporarily, then back up, so this would be wrong
    #if we relaunch tests here, it makes more sense
    #self.relayReachableTime = None
    #trigger a port test:
    if self.orPort:
      self.orPort.start()
    if self.dirPort:
      self.dirPort.start()
    
  def _has_earned_credits_recently(self):
    RECENT_EARNING_CUTOFF = 2 * 60.0 * 60.0
    lastEarnedTime = Bank.get().get_time_of_last_earning()
    curTime = time.time()
    earnedCreditsSinceRelayStart = lastEarnedTime > self._get_relay_reachable_time()
    earnedCreditsWithinCutoff = lastEarnedTime > (curTime - RECENT_EARNING_CUTOFF)
    return earnedCreditsSinceRelayStart and earnedCreditsWithinCutoff
      
  def _on_dht_started(self, dhtObject):
    """Called when the DHTPort is found to be reachable and the DHTNode service is started"""
    self._update_dht()
    
  def _on_dht_stopped(self, dhtObject):
    """Called when the DHTNode service is stopped"""
    self._update_dht()
      
  #TODO:  need to reorganize so that this is setting is done before the descriptor is uploaded
  def _update_dht(self):
    """Update the router descriptor flag in Tor that indicates whether we are a DHT exit or not"""
    if self.is_ready():
      useDHT = "0"
      if self.settings.dhtPort != 0 and self.dhtPort and self.dhtPort.is_ready():
        useDHT = "1"
      self.conn.sendAndRecv('SETCONF AllowDHTExits=%s\r\n' % (useDHT))
      
  def _get_dht_node(self):
    """Return the dhtPort's DHTNode"""
    if self.dhtPort:
      return self.dhtPort.get_node()
    return None
      
  def set_options(self, optionString):
    """Send an options string to Tor
    @returns:  Deferred (for when the options have been set)"""
    if not self.is_ready():
      return
    optionsDeferred = self.conn.sendAndRecv(optionString)
    optionsDeferred.addErrback(self._silent_tor_errback)
    return optionsDeferred

  def on_new_stream(self, stream):
    # pylint: disable-msg=C0111
    log_msg("Stream %d is internal" % (stream.id), 4)
    
  def make_or_circuit(self, event):
    """Create a BaseCircuit to represent someone else's circuit through us"""
    
    #make the BaseCircuit object
    entry = TorMessages.BaseCircuit(self.torApp, event.prevHexId, event.nextHexId, event.prevCircId, event.nextCircId)
    
    #and add the handlers
    paymentHandler = ServerPaymentHandler.ServerPaymentHandler(Bank.get(), entry)
    entry.add_handler(paymentHandler)
    dhtNode = self._get_dht_node()
    if dhtNode:
      dhtHandler = dht.Provider.DHTProvider(entry, dhtNode)
      entry.add_handler(dhtHandler)
      
    return entry
    
  def _set_bw_from_schedule(self):
    """Set bandwidth limits from the hourly schedule and schedule the next update"""
    
    #set the bandwidth rate in Tor based on our settings
    try:
      if self.is_ready():
        bwRate = self.settings.get_bw_rate()
        if bwRate != None:
          self.conn.sendAndRecv("SETCONF RelayBandwidthBurst=\"%s KB\" RelayBandwidthRate=\"%s KB\"\r\n" % (2 * bwRate, bwRate))
        #no traffic allowed
        else:
          self.conn.set_option("ORPort", "0")
    except Exception, error:
      log_ex(error, "Error while setting BW for scheduler")
    
    #Schedule this function to be called again at the end of the hour
    if not self.nextBWUpdateEvent:
      timeTuple = time.localtime()
      currentMinute = timeTuple[4]
      currentSecond = timeTuple[5]
      wholeMinutesLeft = 60 - currentMinute
      secondsUntilEndOfHour = (60.0 * wholeMinutesLeft) - currentSecond
      self.nextBWUpdateEvent = Scheduler.schedule_once(secondsUntilEndOfHour + 30.0, self._set_bw_from_schedule)
  
  def stop(self):
    # pylint: disable-msg=C0111
    
    #return immediately if we are already stopping
    if self.is_stopping():
      return self.shutdownDeferred
      
    #otherwise, note that we are stopping
    log_msg("Trying to shut Tor down nicely...", 2)
    self.isReady = False
    
    #politely ask Tor to shutdown
    try:
      if self.conn:
        #try nicely to shutdown Tor:
        self.conn.sendAndRecv("SIGNAL HALT\r\n")
        #ensure that the connection to tor is closed: 
        self.conn.close()
    except Exception, error:
      log_ex(error, "Failed to close Tor control connection cleanly:", [ConnectionLost, ConnectionDone])
      
    #shutdown upnp if necessary
    dList = []
    if self.dirPort:
      dList.append(self.dirPort.stop())
    if self.orPort:
      dList.append(self.orPort.stop())
    if self.dhtPort:
      dList.append(self.dhtPort.stop())
      
    #make sure the Tor process stops (if it's running)
    if len(self.processes) > 0:
      dList.append(self.processes[0].get_deferred())
      
    self._trigger_event("stopped")
      
    #if shutdown is going to take some time, make and return the deferred
    if len(dList) > 0:
      self.shutdownDeferred = defer.DeferredList(dList)
      self.shutdownDeferred.addCallback(self._on_process_done)
      #in case it's triggered immediately from defer.succeeds
      if self.shutdownDeferred:
        self.shutdownDeferred.addErrback(self._on_process_done)
        #and return our deferred
        return self.shutdownDeferred
      else:
        return defer.succeed(True)
        
    #otherwise, everything is already shutdown:
    self._on_process_done(True)
    return defer.succeed(True)
      
  def force_stop(self):
    """Forcibly kill the Tor process"""
    
    #kill the process if it exists
    if self.processes and self.processes[0].poll() is None:
      log_msg("Forced to kill Tor.", 1)
      System.kill_process(self.torId)
      
    #and handle the shutdown.  
    #NOTE:  this code would normally be triggered when the process dies, but we 
    #are calling it explicitly here in case you don't have permissions to kill 
    #the process, the process is zombied, etc
    if self.shutdownDeferred:
      #NOTE:  necessary because the callback sets self.shutdownDeferred to None
      shutdownDeferred = self.shutdownDeferred
      shutdownDeferred.callback(True)
      #to prevent any later triggering from the process actually finishing...
      shutdownDeferred.pause()
    else:
      self._on_process_done(True)
    
  def _on_process_done(self, result):
    """Called when the Tor process has finally exited.  Responsible for appropriate cleanup"""
    
    #make sure that either the deferreds finished cleanly, or that we log an exception
    if result is True:
      pass
    elif type(result) == type([]):
      for callbackResultTuple in result:
        if callbackResultTuple[0] != True:
          log_ex(callbackResultTuple[0], "Error during Tor shutdown proccess")
    else:
      log_ex(result, "Unexpected value while waiting for Tor process to end")
     
    #clear state and note that we have shutdown 
    log_msg("The Tor process is supposedly finished:  %d" % (self.torId), 2)
    self._set_tor_id(0)
    self.shutdownDeferred = None
    if self.nextBWUpdateEvent and self.nextBWUpdateEvent.active():
      self.nextBWUpdateEvent.cancel()
    self.nextBWUpdateEvent = None
    self.relays = {}
    self.eventHandler = None
    self.conn = None
    #TODO:  standardize this?
    self._cleanup()
    self._trigger_event("finished")
    
    return True
      
  def _do_keepalive(self):
    """Send a keepalive message to the Tor control connection to prevent Tor from exiting"""
    try:
      if self.conn and not self.conn.is_closed():
        self.conn.sendAndRecv("KEEPALIVE 300\r\n")
        log_msg("Keeping Tor alive", 4)
    except Exception, error:
      log_ex(error, "Failed while sending keepalive to Tor")
    return True
    
  def is_ready(self):
    """Return True iff we have a valid Tor control connection"""
    if self.isReady and self.conn and not self.conn.is_closed():
      return True
    return False

  def start(self):
    """The goal of this function is to have exactly one Tor process running at 
    the end, with torId containing the PID of that process.  All other Tor processes 
    will be killed."""  
    if self.is_ready():
      return defer.succeed(True)
    if self.is_starting():
      return self.startupDeferred
    self.startupDeferred = defer.Deferred()
    self._find_or_launch_tor_process()
    #tries, repeatedly, forever, to connect to Tor
    Globals.reactor.connectTCP("127.0.0.1", self.settings.controlPort, TorCtl.TorClientFactory(self, self._startup_on_control_connection_made))
    self._trigger_event("launched")
    return self.startupDeferred
    
  def launch(self):
    # pylint: disable-msg=C0111
    raise NotImplementedError()
    
  def _find_tor_process(self):
    """Returns exactly one tor process id.  Will kill any other running Tors, 
    unless Globals.ALLOW_MULTIPLE_INSTANCES is True"""
    
    #if this flag is set, we NEVER find Tor processes, we always launch a new one
    if Globals.ALLOW_MULTIPLE_INSTANCES:
      return None

    #check how many tors are running:
    newIds = System.get_process_ids_by_name(Globals.TOR_RE)
    #None?
    if len(newIds) <= 0:
      return None
    #One?
    if len(newIds) == 1:
      #TODO: if there is a zombie process, this will fail
      if newIds[0] != self.torId:
        log_msg("Tor process ID changed, I have no idea why that would happen.", 0)
      return newIds[0]
    #Many?
    log_msg("WTF?  There are apparently %s tor processes running.  Trying to kill the others." % (len(newIds)), 0)
    
    #pick one of them
    if self.torId in newIds:
      #if our previously known torId is among the processes found, use that
      newIds.remove(self.torId)
      selectedTorId = self.torId
    else:
      #guess we can pick one of these as our tor:
      selectedTorId = newIds.pop()
      
    #kill everything except the selectedTorId
    while len(newIds) > 0:
      pid = newIds.pop(0)
      log_msg("Trying to kill tor process %s" % (pid), 2)
      System.kill_process(pid)
      
    return selectedTorId
    
  def _launch_tor_process(self):
    """Launch a new Tor process"""
    
    log_msg("Launching Tor...", 2)
    
    #generate the tor configuration file:
    torrcData = self.settings.get_relay_torrc_data()
    self.settingsFileName = os.path.join(Globals.USER_DATA_DIR, Globals.TOR_CONFIG_FILE_NAME)
    settingsFile = open(self.settingsFileName, "wb")
    settingsFile.write(torrcData)
    settingsFile.close()
    
    #determine which ports we need to check
    #these ports must always be open for Tor to start correctly:
    portList = [self.settings.controlPort, self.settings.socksPort]
    #if we are going to be a relay, check those ports as well:
    if self.settings.beRelay:
      portList += [self.settings.orPort]
      if self.settings.dirPort != 0:
        portList += [self.settings.dirPort]
    
    #check that none of the ports are in use
    self.numPortsReady = 0
    self.numPortsNecessary = len(portList)
    def on_port_ready():
      """Called when another required port is found to be open"""
      self.numPortsReady += 1
      if self.numPortsReady >= self.numPortsNecessary:
        #launch the correct tor binary depending on the users System
        self._make_tor_process(self.settingsFileName)
        self.numPortsReady = 0
    for portNum in portList:
      ClientUtil.check_port(portNum, on_port_ready)
      
  def _make_tor_process(self, settingsFile):
    """Attempts to launch 'innomitor -f (settingsFile)
    We assume that it is on the $PATH
    NOTE: this function was moving over to using the native twisted method for 
    spawning processes- the others in System should follow suit as they sometimes
    cause some esoteric problems"""
    if System.IS_WINDOWS:
      torProcess = LaunchProcess.LaunchProcess([os.path.join(Globals.WINDOWS_BIN, "Tor.exe"), "-f", settingsFile], creationflags=win32process.CREATE_NO_WINDOW, cwd=Globals.WINDOWS_BIN)
      self._set_tor_id(torProcess.pid)
      return
    elif System.IS_LINUX:
      d = defer.Deferred()
      torProcess = SpawnProcess.SpawnProcess(d, madeCallback=self._set_tor_id)
      #TODO:  is there no better way to fix this warning?
      #suppress PotentialZombieProcessWarning
      warnings.simplefilter("ignore")
      Globals.reactor.spawnProcess(torProcess, "innomitor", ["innomitor", "-f", settingsFile])
      #reinstate warnings
      warnings.resetwarnings()
      return
    raise NotImplementedError()
    
  def _find_or_launch_tor_process(self):
    """Update our existing process id by finding one running on the system, or
    if there are none, launch a new Tor"""
    
    existingTorId = self._find_tor_process()
    if existingTorId and ProgramState.USE_EXISTING_TOR:
      self._set_tor_id(existingTorId)
    else:
      self._launch_tor_process()
    
  def _set_tor_id(self, pid):
    """Called when we learn/decide on the tor process ID.
    Creates the PseudoProcess object representing our Tor process.
    @param pid:  the pid of the Tor process that we will connect to.
    @type pid:   int (process id)
    """
    
    self.torId = pid
    
    #if there is a process
    if pid != 0:
      processObj = Process.Process(pid)
      self.processes = [processObj]
      exitDeferred = processObj.get_deferred()
      exitDeferred.addCallback(self._on_tor_process_died)
      exitDeferred.addErrback(log_ex, "Unexpected error while handling Tor death")
      
    #otherwise we're just clearing self.torId because we have no process anymore
    else:
      self.processes = []
      
  def _on_tor_process_died(self, result):
    """Called when a tor process THAT WE LAUNCHED dies.  Only bothers trying anything
    if we never managed to connect to Tor.  In that case, this function 
    tries to reset our tor settings file to all defaults, in case bad settings
    are preventing Tor from starting up.  Failing that, will launch an attempt
    to capture Tor's process output, to be logged and displayed to the user.
    @param result:  the callback return value from PseudoProcess
    @returns result:  passthrough for callback"""
    
    #if Tor died before we could even connect to it, try to recover
    if not self.conn and not self.connectedSuccessfully:
      
      #first, try resetting our settings
      if not self.alreadyResetSettings:
        self.alreadyResetSettings = True
        log_ex("reason:  %s\nconfig: %s" % (result, self.settings.get_relay_torrc_data()), "Tor died before we could even connect to it")
        GUIController.get().show_msgbox("Tor failed to start up correctly!\n\nWe are resetting all options to default values.  Make sure you go correct the new Tor settings!")
        #try to recover by going back to a safe state of settings
        self.settings.reset_defaults()
        self.settings.save()
        #and try launching Tor again...
        self._launch_tor_process()
        
      #if we already tried resetting settings, and that failed too, then try getting the Tor process output
      else:
        if not self.alreadyCapturedTorOutput:
          self.alreadyCapturedTorOutput = True
          self._DEBUG_capture_tor_output()
        #tell the user they have to come see us.  :(
        log_ex("reason:  %s" % (result), "Tor died again before we could even connect to it")
        GUIController.get().show_msgbox("Tor is not working properly on your computer.  Please submit an error report (Help menu -> Report and issue...) or go to the chat room.  Sorry!")
      return result
      
    #otherwise, just try launching Tor again, unless we're stopping, in which case this is expected)
    if not self.is_stopping():
      self._launch_tor_process()
    return result
    
  def _DEBUG_capture_tor_output(self):
    """This is just for when we've tried to start Tor and failed a few times, 
    and we need to see the program output to be able to recover from the problem.
    """
    
    #try relaunching Tor specifically to capture its output
    try:
      if System.IS_WINDOWS:
        encodedBin = System.encode_for_filesystem(Globals.WINDOWS_BIN)
        process = os.path.join(encodedBin, "Tor.exe")
        output = utils.getProcessOutput(process, args=("-f", self.settingsFileName), path=encodedBin)
      else:
        output = utils.getProcessOutput("innomitor", args=("-f", self.settingsFileName), path=os.getcwd())
      
      def tor_output(response):
        """If we actually get some output, log it"""
        log_ex("Tor startup output:  %s" % (response), "Tor output successful")
        lines = response.replace("\r", "").split("\n")
        finalMsg = ""
        for line in lines:
          if " [err] " in line or " [warn] " in line:
            finalMsg += line + "\n\n"
        GUIController.get().show_msgbox(finalMsg, width=500)
      output.addCallback(tor_output)
      
      def tor_failure(reason):
        """Log the reason that we could not get any output"""
        log_ex(reason, "Failed to start Tor to get debugging output")
      output.addErrback(tor_failure)
      
    except Exception, error:
      log_ex(error, "_DEBUG_capture_tor_output failed")
      
  def is_server(self):
    return self.settings.beRelay
        
  def start_server(self):
    """Start being a relay.  Is synchronous, even though it actually takes a little while for Tor settings to be applied.
    @returns:  True"""
    if not self.settings.beRelay:
      self.settings.beRelay = True
      self.settings.on_apply(self, "")
      self.settings.save()
      #also apply the BitBlinder settings for the TCP-Z stuff
      BitBlinder.get().settings.on_apply(BitBlinder.get(), "")
      self._trigger_event("server_started")
    return True
    
  def stop_server(self):
    """Stop Tor from being a relay.  Is synchronous.
    @returns:  True"""
    if self.settings.beRelay:
      self.settings.beRelay = False
      self.settings.on_apply(self, "")
      self.settings.save()
      self._trigger_event("server_stopped")
    return True
    
  def get_par_handler(self, hexId, circId):
    """Figure out which BaseCircuit object should deal with a message"""
    if hexId not in self.orCircuits:
      return None
    if circId not in self.orCircuits[hexId]:
      return None
    return self.orCircuits[hexId][circId]
    
  def set_par_handler(self, hexId, circId, handler):
    """Set the BaseCircuit object that should deal with messages for circId from hexId"""
    if hexId not in self.orCircuits:
      self.orCircuits[hexId] = {}
    self.orCircuits[hexId][circId] = handler
    
  def remove_par_handler(self, hexId, circId):
    """Remove the BaseCircuit object that handles messages for circId from hexId"""
    if hexId in self.orCircuits and circId in self.orCircuits[hexId]:
      log_msg("Removed orcircuit mapping:  %s:%s" % (Basic.clean(hexId[:4]), Basic.clean(circId)), 4)
      self.orCircuits[hexId][circId].close()
      del self.orCircuits[hexId][circId]
    
  def _startup_on_control_connection_made(self, conn):
    """Called when the control socket has actually connected.
    @param conn:  the control connection
    @type conn:  TorCtl.TorControlProtocol"""
    
    #make the event handler and set it up
    self.conn = conn
    self.connectedSuccessfully = True
    self.eventHandler = EventHandler.EventHandler(self)
    self.conn.set_close_handler(self.eventHandler.closed_event)
    self.conn.set_event_handler(self.eventHandler)
    
    #send initialization messages to the Tor control connection
    #TODO:  not very secure to have the authentication key right here like this, go copy w/e vidalia does
    self.conn.authenticate("slothking")
    #standardize the format for names from event callbacks to the form nick~$hex or something
    self.conn.sendAndRecv("USEFEATURE VERBOSE_NAMES\r\n")
    self.eventHandler.listen_for_startup_errors()
    #starts sending KEEPALIVE events to Tor.  If Tor goes a few minutes without hearing one, it will shutdown.  This prevents zombied Tor processes in our network.
    self._do_keepalive()
    Scheduler.schedule_repeat(30.0, self._do_keepalive)
    self._check_version()
    
    #continue the startup process
    self._startup_on_learned_fingerprint()
    
  def _check_version(self):
    """Check the version of the Tor/innomitor binary"""
    versionDeferred = self.conn.get_info("version")
    
    #add callbacks
    def on_learned_version(data):
      """Handles version response from Tor"""
      
      #parse the version
      versionLine = data["version"]
      regex = re.compile("^(.*)_for_BitBlinder_([0-9\\.]+).*$")
      matches = regex.match(versionLine)
      
      #this means that innomitor is an outdated version
      if not matches:
        GUIController.get().show_msgbox("Your version of innomitor is out of date.  Please go update it:  %s/download/" % (ProgramState.Conf.BASE_HTTP))
        return
        
      #set the current versions
      self.torVersion = matches.group(1)
      self.innomitorVersion = matches.group(2)
      log_msg("InnomiTor version:  %s" % (self.innomitorVersion), 2)
      return self.innomitorVersion
    versionDeferred.addCallback(on_learned_version)
    
    #add errback
    versionDeferred.addErrback(self._silent_tor_errback, "Failed to get version from Tor")
    
    return versionDeferred
        
  def _startup_on_learned_fingerprint(self):
    """Called when the fingerprint has been loaded"""
    #make sure that the fingerprint is loaded:
    if not Globals.FINGERPRINT:
      Scheduler.schedule_once(0.2, self._startup_on_learned_fingerprint)
      return
    #ports are probably ready for testing and UPnP forwarding
    self.forward_ports()
    #have to wait for Tor to load the network statuses before we can then load it from Tor
    self._check_progress(0, 80, self._startup_get_relay_data)
    
  def _check_progress(self, progressOrResult, checkPoint, callback):
    """Wait until Tor has bootstrapped to a certain point before continuing with the load process
    @param progressOrResult:  current level of progress in the Tor bootstrap process.
    @type progressOrResult:  float or torctl result
    @param checkPoint:  the level of bootstrap progress to wait until.
    @type checkPoint:  float
    @param callback:  the function to call when progress is sufficient.
    @type callback:  function"""
    
    #convert to an int if this is a complicated deferred result
    if type(progressOrResult) == types.ListType:
      progress = progressOrResult[0][1]
    else:
      progress = progressOrResult
      
    #are we bootstrapped enough to call the next callback?
    if progress >= checkPoint:
      callback()
      return
      
    #otherwise, need to check for progress again
    progressDeferred = self.eventHandler.get_progress()
    #a timeout, so that we dont spam this function.  Caused CPU to hang in pubuntu
    timeoutDeferred = defer.Deferred()
    timeoutDeferred.addCallback(defer.succeed)
    Scheduler.schedule_once(0.1, timeoutDeferred.callback, True)
    
    #schedule the next check of progress
    nextProgressCheckDeferred = defer.DeferredList([progressDeferred, timeoutDeferred])
    nextProgressCheckDeferred.addCallback(self._check_progress, checkPoint, callback)
    nextProgressCheckDeferred.addErrback(Basic.log_ex, "Unhandled exception while waiting for progress %s to call %s" % (checkPoint, callback), [TorCtl.TorCtlClosed])
    
  def _startup_get_relay_data(self):
    """Called when Tor has loaded some descriptors and NS statuses"""
    networkStatusDeferred = self.conn.get_network_status("all")
    descriptorDeferred = self.conn.sendAndRecv("GETINFO desc_short/all-recent\r\n")
    dList = defer.DeferredList([networkStatusDeferred, descriptorDeferred])
    dList.addCallback(self._startup_handle_relay_data)
    
  def _startup_handle_relay_data(self, responses):
    """Called when we have learned about some descriptors and NS statuses
    @param responses:  the result of Tor control queries for NS list and descriptors
    @type responses:  complicated"""
    
    #check that the data was loaded correctly:
    networkStatusList = responses[0][1]
    descriptorResponse = responses[1][1]
    if not descriptorResponse[0][2]:
      log_msg("No relays known while first starting up, waiting a bit...", 0)
      Scheduler.schedule_once(5.0, self._startup_get_relay_data)
      return
    if not networkStatusList:
      log_msg("No network statuses known while starting up, waiting a bit...", 0)
      Scheduler.schedule_once(5.0, self._startup_get_relay_data)
      return
      
    #parse the TorCtl response:
    #removing leading DESC:\n and trailing \n
    descriptorDataString = descriptorResponse[0][2].replace("DESC:\n", "", 1)[:-1]
    descriptorDataLines = descriptorDataString.split("\nDESC:\n")
    #make a mapping from idhex to network status
    networkStatusMapping = {}
    for networkStatus in networkStatusList:
      networkStatusMapping[networkStatus.idhex] = networkStatus
    
    #create a Relay for each of the descriptors
    relayList = []
    for descriptorData in descriptorDataLines:
      descriptor = self._build_descriptor(descriptorData, networkStatusMapping)
      if descriptor:
        relay = Relay.Relay()
        relay.set_descriptor(descriptor)
        relayList.append(relay)
      else:
        log_msg("Relay descriptor had no matching network status.", 1)
    self._add_relays(relayList)
    
    #make a fake relay for us if we dont have one and we should:
    val = Globals.FINGERPRINT
    if val not in self.relays:
      nick = str(self.settings.name)
      exitPolicyMatches = TorCtl.rjre_.match("reject *:*")
      fakeExitPolicy = [TorCtl.ExitPolicyLine(False, *exitPolicyMatches.groups())]
      desc = TorCtl.Router(val, nick, 0, False, fakeExitPolicy, [], "0.0.0.0", "2.0.0.0", "Windows", 0, "??", False, self.settings.dhtPort != 0)
      relay = Relay.Relay()
      relay.set_descriptor(desc)
      self._add_relays([relay])
      
    self.relayKeys[Globals.FINGERPRINT] = Globals.PUBLIC_KEY
        
    #set the types of events that we will recieve, and start listening
    self.eventHandler.start_listening_basic()
    
    #see if Tor is ready yet:
    self.eventHandler.check_ready()
    
  def on_ready(self):
    """Called when Tor is basically 100% ready (specifically after it has 
    successfully negotiated an OR connection for the first hop of a circuit"""
    self.isReady = True
    
    #can reduce log level to something reasonable now:
    log_msg("Reducing Tor log levels...", 2)
    fileName = os.path.join(os.getcwdu(), Globals.LOG_FOLDER, 'tor.out')
    if System.IS_WINDOWS:
      fileName = fileName.replace("\\", "\\\\")
    fileName = System.encode_for_filesystem(fileName)
    self.conn.sendAndRecv('SETCONF Log="notice file %s"\r\n' % (fileName))
    
    #set more Tor options now that it is completely ready
    self.eventHandler.start_listening_all()
    self._set_bw_from_schedule()
    #NOTE:  cant put this option in the torrc file because it prevents proper bootup the first time Tor is run (bug in Tor)
    self.conn.set_option("FastFirstHopPK", "0")
    GlobalEvents.throw_event("tor_ready")
    self._update_dht()
    if self.settings.beRelay:
      self._trigger_event("server_started")
      
    #inform any listeners that we are done starting up
    tempDeferred = self.startupDeferred
    self.startupDeferred = None
    tempDeferred.callback(True)
    
    self._trigger_event("started")
       
  def on_done(self):
    """Called when the control connection is closed"""
    self.isReady = False
    #if we're not done, try reconnecting
    if not self.shutdownDeferred:
      log_msg("Trying to reconnect to Tor...")
      #make sure Tor gets shut down:
      self.force_stop()
      #try to reconnect soon:
      Scheduler.schedule_once(3.0, self.start)
      GlobalEvents.throw_event("tor_done")

  def _build_descriptor(self, descriptorData, networkStatusMapping):
    """Given a descriptor and list of networks statuses, create a TorCtl.Router and corresponding Relay.
    We've modified the descriptor to be a much shorter form so that hundreds can be sent through the control connection with Python being slowed to a crawl.
    @param descriptorData:  information describing the Router, from the Tor Control connection
    @type descriptorData:  string
    @param networkStatusMapping: all of the known network statuses
    @type networkStatusMapping:  a mapping from hexid to NetworkStatus objects
    @return: Router instance or None if there was no proper NetworkStatus"""
    
    #load the public key
    publicKey, descriptorData = PublicKey.load_public_key(descriptorData)
    
    #the rest of the data is delimited by "|"
    vals = descriptorData.split("|")
    
    #load each field from the descriptor
    name = vals.pop(0)
    ipAddress = vals.pop(0)
    country = vals.pop(0)
    orPort = int(vals.pop(0))
    dirPort = int(vals.pop(0))
    version, osName = PLATFORM_REGEX.match(vals.pop(0)).groups()
    fingerprint = vals.pop(0).replace(" ", "")
    uptime = int(vals.pop(0))
    bw_observed = int(vals.pop(0))
    singleHop = vals.pop(0) == "1"
    willBindExits = vals.pop(0) == "1"
      
    #if the version of innomitor is recent enough, also have to check for allowDHTExit flag:
    allowDHT = False
    if Basic.compare_versions_strings(self.innomitorVersion, "0.4.9"):
      allowDHT = vals.pop(0) == "1"
      
    #cannot continue unless we know the relay's network status
    if fingerprint not in networkStatusMapping:
      return None
    
    #read in exit policy:
    isExit = False
    exitpolicy = []
    while len(vals) > 0:
      args = vals.pop(0).split(" ")
      shouldAccept = False
      if args.pop(0) == "accept":
        shouldAccept = True
        isExit = True
      policy = EXIT_POLICY_REGEX.match(args.pop(0))
      exitpolicy.append(TorCtl.ExitPolicyLine(shouldAccept, *policy.groups()))
    
    #validate the data:
    relayNetworkStatus = networkStatusMapping[fingerprint]
    dead = not ("Running" in relayNetworkStatus.flags)
    if name != relayNetworkStatus.nickname:
      log_msg("Got different names " + relayNetworkStatus.nickname + " vs " + name + " for " + relayNetworkStatus.idhex, 1)
    if not bw_observed and not dead and ("Valid" in relayNetworkStatus.flags):
      log_msg("No bandwidth for live relay " + relayNetworkStatus.nickname, 2)
    if not version or not osName:
      log_msg("No version and/or OS for relay " + relayNetworkStatus.nickname, 2)
    #this is deprecated
    if willBindExits:
      log_msg("Relay has deprecated bindExits flag set:  %s" % (fingerprint), 4)
      
    #build the descriptor
    self.relayKeys[fingerprint] = publicKey
    descriptor = TorCtl.Router(relayNetworkStatus.idhex, relayNetworkStatus.nickname, bw_observed, dead, exitpolicy, relayNetworkStatus.flags, ipAddress, version, osName, uptime, country, isExit, allowDHT)
    
    return descriptor
  
  def get_relay(self, hexId=None):
    """Get a Relay object that corresponds to hexid.  Will load the relay info
    from the TorCtl if it is not loaded already.  Will still return None occasionally,
    when Tor tries to build a circuit with some descriptor that it refuses to give us.
    @param hexId:  the hexid of the relay to load
    @type hexId:  str
    @return: Relay or None"""

    #default to using our own hexid
    if not hexId:
      hexId = Globals.FINGERPRINT
      #fail if we don't have one
      if not hexId:
        return None
    
    #fail if no relays have been loaded yet
    if not self.relays:
      return None
      
    #validate the input
    assert RELAY_HEX_ID_RE.match(hexId), "%s is not a valid hexId!" % (hexId)
    
    #return the relay if we've already loaded it
    if self.relays.has_key(hexId):
      return self.relays[hexId]
      
    #otherwise, see if we can load it right now:
    self.load_relay(hexId)
    return None
  
  #TODO:  stop using this, also, make it error better (check for duplicate names)
  def get_relay_by_name(self, name):
    """DO NOT USE.
    This is only here for debugging purposes, when a certain relay is behaving differently or strangely."""
    for hexId, relay in self.relays.iteritems():
      if relay.desc.nickname == name:
        return relay
    return None
    
  def _add_relays(self, relayList):
    """Adds a bunch of relays to our internal list.  Raises an Exception if you 
    try to add a relay whose hexid already exists.
    @param relayList:  all of the Relay's to be added
    @type relayList:  list of Relay's"""
    for relay in relayList:
      if not self.relays.has_key(relay.desc.idhex):
        self.relays[relay.desc.idhex] = relay
        GlobalEvents.throw_event("new_relay", relay)
      else:
        raise Exception("Please dont add relays that are already in .relays!  Just update the existing one instead")
  
  def load_relay(self, hexId):
    """Get relay data for a single relay from the Tor control connection.
    Called when we try to get a relay that we dont know about.
    @param hexId:  the hexid of the descriptor to load
    @type hexId:  str"""
    
    #get the network status document from Tor
    statusQuery = "ns/id/"+hexId
    statusDeferred = self.conn.get_info(statusQuery)
    statusDeferred.addErrback(self._silent_tor_errback, "Failed to get network status from Tor for %s" % (statusQuery))
    
    #and get the descriptor
    descriptorQuery = "desc_short/id/"+hexId
    descriptorDeferred = self.conn.get_info(descriptorQuery)
    descriptorDeferred.addErrback(self._silent_tor_errback, "Failed to get descriptor from Tor for %s" % (descriptorQuery))
    
    def response(result, descriptorQuery=descriptorQuery, statusQuery=statusQuery):
      """parse the responses from Tor"""
      #if either of the callbacks failed, just print a simple warning notice, this happens fairly frequently
      if not result[0][0] or not result[1][0] or not result[0][1] or not result[1][1]:
        log_msg("Failed to get relay info from Tor for %s" % (hexId), 2)
        return
      #read the network status and descriptors from the response
      networkStatus = TorCtl.parse_ns_body(result[1][1][statusQuery])[0]
      descriptorData = result[0][1][descriptorQuery].replace('DESC:\n', "", 1)
      descriptorData = descriptorData[:-1]
      descriptor = self._build_descriptor(descriptorData, {networkStatus.idhex: networkStatus})
      #add a Relay if the descriptor is new
      if not self.relays.has_key(descriptor.idhex):
        relay = Relay.Relay()
        relay.set_descriptor(descriptor)
        self._add_relays([relay])
      #otherwise, just update it
      else:
        self.relays[descriptor.idhex].set_descriptor(descriptor)
        
    #add the callbacks
    dList = defer.DeferredList([descriptorDeferred, statusDeferred])
    dList.addCallback(response)
    dList.addErrback(Basic.log_ex, "Failed while parsing relay information from Tor")
      
  def _silent_tor_errback(self, reason, messageString=None):
    """Just log_msg any TorCtlClosed or ErrorReply exceptions.
    This is useful for places where we are querying Tor but don't really care about the answer."""
    if Basic.exception_is_a(reason, [TorCtl.ErrorReply, TorCtl.TorCtlClosed]):
      if messageString == None:
        messageString = str(reason)
      log_msg(messageString)
    else:
      if messageString == None:
        messageString = "Failure during Tor communication"
      log_ex(reason, messageString)

  def _pick_random_relay_by_score(self, allowableRelays):
    """Randomly select a relay, weighted by the score of each relay.
    @param allowableRelays:  how many relays to include in the path
    @type allowableRelays:   list (of Relay instances)
    @return: Relay instance (from the list)"""
    
    #return if there's nothing to pick from:
    if len(allowableRelays) <= 0:
      return None
      
    #calculate the sum of all relay scores:
    totalScore = 0
    for relay in allowableRelays:
      totalScore += relay.score
      
    #pick randomly, but weight by bw of each relay:
    selectedScoreIdx = random.random() * float(totalScore)
    scoreSoFar = 0
    for relay in allowableRelays:
      scoreSoFar += relay.score
      if scoreSoFar >= selectedScoreIdx:
        return relay
        
    #should only make it here because of floating rounding errors
    return allowableRelays[-1]
    
  def _get_allowable_relays(self, host=None, port=None, exitCountry=None, ignoreExits=None, protocol="TCP"):
    """Returns two lists of allowable relays--one of those that will exit with the given parameters, and one of those that will not.
    @param length:  how many relays to include in the path
    @type length:   int
    @param host:  the last relay in the path must be able to exit to this host
    @type host:   hostname or IP address or None (if you dont care)
    @param port:  the last relay in the path must be able to exit to this port
    @type port:   int or None (if you dont care)
    @param exitCountry:  the last relay in the path must be able to exit to this country
    @type exitCountry:   string or None (if you dont care)
    @param ignoreExits:  Relays that should definitely not be used as the last relay
    @type ignoreExits:   a list of Relays
    @param protocol:  What type of traffic will be sent from the last relay
    @type protocol:   string (either TCP or DHT for now)
    @return: Tuple of 2 lists of allowable relays--one of those that will exit with the given parameters, and one of those that will not"""
    
    #convert arguments to the right types
    if not ignoreExits:
      ignoreExits = []
    intHost = None
    if host and type(host) != types.IntType:
      #check if this is an IP, or if it is a hostname that has yet to be resolved:
      if isIPAddress(str(host)):
        intHost = struct.unpack(">I", socket.inet_aton(host))[0]
    flags = ["Running"]
    
    #figure out which relays are allowable exits and which are allowable middle relays
    ourRelay = self.get_relay()
    middleRelays = []
    exitRelays = []
    for relay in self.relays.values():
      #is this relay allowable at all?
      relayIsAuthority = relay.desc.nickname.lower().find("innominetauth") != -1
      relayIsAllowed = not relayIsAuthority and relay.has_flags(flags)
      if relayIsAllowed:
        relayIsUs = ourRelay == relay
        #is this relay an allowable exit relay?
        relayWillExitToCountry = not exitCountry or relay.desc.country == exitCountry
        relayWillExitToHost = relay.will_exit_to(intHost, port, protocol)
        relayShouldBeIgnored = relay not in ignoreExits
        relayIsAllowableExit = relayWillExitToCountry and relayWillExitToHost and relayShouldBeIgnored
        if relayIsAllowableExit:
          exitRelays.append(relay)
        #otherwise, use it as a middle relay (unless it's our relay, which can never be a middle relay)
        elif not relayIsUs:
          middleRelays.append(relay)
          
    return (exitRelays, middleRelays)
    
  def make_path(self, length, host=None, port=None, exitCountry=None, ignoreExits=None, protocol="TCP"):
    """Makes a path for a circuit to exit to host:port with the given parameters.
    @param length:  how many relays to include in the path
    @type length:   int
    @param host:  the last relay in the path must be able to exit to this host
    @type host:   hostname or IP address or None (if you dont care)
    @param port:  the last relay in the path must be able to exit to this port
    @type port:   int or None (if you dont care)
    @param exitCountry:  the last relay in the path must be able to exit to this country
    @type exitCountry:   string or None (if you dont care)
    @param ignoreExits:  Relays that should definitely not be used as the last relay
    @type ignoreExits:   a list of Relays
    @param protocol:  What type of traffic will be sent from the last relay
    @type protocol:   string (either TCP or DHT for now)
    @return: a path that meets these criteria.  If there are not enough relays to make such a path, returns None"""

    #make a list of acceptable relays:
    exitRelays, middleRelays = self._get_allowable_relays(host, port, exitCountry, ignoreExits, protocol)
        
    #TODO:  this is pretty weird that you can ever select yourself.  Is it worth it?
    #remove our own relay from the list of exits, UNLESS there are very few (in which case this is de-anonymizing, and will potentially break something)
    #also, our relay should not be in the list if this is too short of a path:
    if len(exitRelays) > RARE_EXIT_POLICY_CUTOFF or length <= 2:
      ourRelay = self.get_relay()
      if ourRelay in exitRelays:
        exitRelays.remove(ourRelay)
          
    #pick an exit:
    for relay in exitRelays:
      relay.score = relay.get_score()
    exitRelay = self._pick_random_relay_by_score(exitRelays)
#    #for testing:  use sylph as exit for easier debugging
#    exitRelay = self.get_relay("0FA7BA1F266BDB109BF292D6256F388D48324832")
    
    #fail if there were no acceptable exits (happens when network is small or exit policy is obscure)
    if not exitRelay:
      log_msg("Failed to find exit relay to destination: %s:%s" % (Basic.clean(host), port), 1, "circuit")
      return None
      
    #finished if this was a one hop path
    if length <= 1:
      return [exitRelay]
      
    #otherwise, prepare and score the list of middle relays
    ratio = 2.0 + (float(len(middleRelays)) / float(len(exitRelays)))
    for relay in middleRelays:
      relay.score = ratio * relay.get_score()
    #prevent the exit relay from being used again
    exitRelays.remove(exitRelay)
    #allow the exit relays to be used as middle relays as well, even though they will be less likely:
    middleRelays += exitRelays
      
    #pick each of the (length-1) remaining relays for the path
    path = [exitRelay]
    for i in range(1, length):
      nextRelay = self._pick_random_relay_by_score(middleRelays)
      if not nextRelay:
        log_msg("Not enough relays to create a path!", 1, "circuit")
        return None
      middleRelays.remove(nextRelay)
      path.insert(0, nextRelay)
      
    return path
