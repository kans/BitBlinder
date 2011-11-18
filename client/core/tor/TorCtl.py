#!/usr/bin/python
# TorCtl.py -- Python module to interface with Tor Control interface.
# Copyright 2005 Nick Mathewson
# Copyright 2007 Mike Perry. See LICENSE file.

"""
Library to control Tor processes.

This library handles sending commands, parsing responses, and delivering
events to and from the control port. The basic usage is to create a
socket, wrap that in a TorCtl.Connection, and then add an EventHandler
to that connection. 

Note that the TorCtl.Connection is fully compatible with the more
advanced EventHandlers in TorCtl.PathSupport (and of course any other
custom event handlers that you may extend off of those).

This package also contains a helper class for representing Routers, and
classes and constants for each event.

"""

__all__ = ["EVENT_TYPE", "TorCtlError", "TorCtlClosed", "ProtocolError",
           "ErrorReply", "NetworkStatus", "ExitPolicyLine", "Router",
           "RouterVersion", "Connection", "parse_ns_body",
           "EventHandler", "NetworkStatusEvent",
           "NewDescEvent", "CircuitEvent", "StreamEvent", "ORConnEvent",
           "StreamBwEvent", "LogEvent", "AddrMapEvent", "BWEvent",
           "UnknownEvent", "StatusEvent", "PaymentEvent", "NewConsensusEvent" ]

import os
import re
import struct
import sys
import threading
import Queue
import datetime
import socket
import binascii
import types
import time
from TorUtil import *

from twisted.python.failure import Failure
from twisted.internet.defer import Deferred
from twisted.protocols import basic
from twisted.internet.protocol import Protocol, ReconnectingClientFactory

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core import ProgramState

console_data_string = ''
trackingConsoleChanges = False

class TorClientFactory(ReconnectingClientFactory):
  def __init__(self, torApp, connectionCallback):
    self.torApp = torApp
    self.connectionCallback = connectionCallback
    self.maxDelay = 0.5
    self.initialDelay = 0.2

  def buildProtocol(self, addr):
    self.resetDelay()
    p = TorControlProtocol(self.torApp)
    p.factory = self
    return p
    
  def clientConnectionSucceeded(self, protocol):
    self.connectionCallback(protocol)

  def clientConnectionLost(self, connector, reason):
    return

  def clientConnectionFailed(self, connector, reason):
    self.retry(connector)

def log_data(data):
  global console_data_string
  log_msg(data, 3, "tor_conn")
  if ProgramState.DEBUG:
    if trackingConsoleChanges:
      for filterString in ("250 OK", "TOKEN_LEVELS ", "ORCONN ", "BW ", "SENDPAYMENT ", "ADDTOKENS "):
        if data.find(filterString) != -1:
          return
      console_data_string += data

# Types of "EVENT" message.
EVENT_TYPE = Enum2(
          CIRC="CIRC",
          STREAM="STREAM",
          ORCONN="ORCONN",
          STREAM_BW="STREAM_BW",
          BW="BW",
          NS="NS",
          NEWDESC="NEWDESC",
          ADDRMAP="ADDRMAP",
          DEBUG="DEBUG",
          INFO="INFO",
          NOTICE="NOTICE",
          WARN="WARN",
          ERR="ERR",
          STATUS_GENERAL="STATUS_GENERAL",
          STATUS_CLIENT="STATUS_CLIENT",
          STATUS_SERVER="STATUS_SERVER",
          ORCIRCUIT="ORCIRCUIT",
          NEWCONSENSUS="NEWCONSENSUS",
          TOKEN_LEVELS="TOKEN_LEVELS")          
    
rtre_ = re.compile(r"^router (\S+) (\S+)")
fpre_ = re.compile(r"^opt fingerprint (.+).*on (\S+)")
plre_ = re.compile(r"^platform Tor (\S+).*on (\S+)")
acre_ = re.compile(r"^accept (\S+):([^-]+)(?:-(\d+))?")
rjre_ = re.compile(r"^reject (\S+):([^-]+)(?:-(\d+))?")
bwre_ = re.compile(r"^bandwidth \d+ \d+ (\d+)")
upre_ = re.compile(r"^uptime (\d+)")
hire_ = re.compile(r"^opt hibernating 1")

class TorCtlError(Exception):
  "Generic error raised by TorControl code."
  pass

class TorCtlClosed(TorCtlError):
  "Raised when the controller connection is closed by Tor (not by us.)"
  pass

class ProtocolError(TorCtlError):
  "Raised on violations in Tor controller protocol"
  pass

class ErrorReply(TorCtlError):
  "Raised when Tor controller returns an error"
  pass

class NetworkStatus:
  "Filled in during NS events"
  def __init__(self, nickname, idhash, orhash, updated, ip, orport, dirport, flags):
    self.nickname = nickname
    self.idhash = idhash
    self.orhash = orhash
    self.ip = ip
    self.orport = int(orport)
    self.dirport = int(dirport)
    self.flags = flags
    self.idhex = (self.idhash + "=").decode("base64").encode("hex").upper()
    m = re.search(r"(\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)", updated)
    self.updated = datetime.datetime(*map(int, m.groups()))

class NetworkStatusEvent:
  def __init__(self, event_name, nslist):
    self.event_name = event_name
    self.arrived_at = 0
    self.nslist = nslist # List of NetworkStatus objects

class NewDescEvent:
  def __init__(self, event_name, idlist):
    self.event_name = event_name
    self.arrived_at = 0
    self.idlist = idlist

class CircuitEvent:
  def __init__(self, event_name, circ_id, status, path, reason, remote_reason):
    self.event_name = event_name
    self.arrived_at = 0
    self.circ_id = circ_id
    self.status = status
    self.path = path
    self.reason = reason
    self.remote_reason = remote_reason

class StreamEvent:
  def __init__(self, event_name, strm_id, status, circ_id, target_host,
         target_port, reason, remote_reason, source, source_addr, purpose):
    self.event_name = event_name
    self.arrived_at = 0
    self.strm_id = strm_id
    self.status = status
    self.circ_id = circ_id
    self.target_host = target_host
    self.target_port = int(target_port)
    self.reason = reason
    self.remote_reason = remote_reason
    self.source = source
    self.source_addr = source_addr
    self.purpose = purpose

class ORConnEvent:
  def __init__(self, event_name, status, endpoint, age, read_bytes,
         wrote_bytes, reason, ncircs):
    self.event_name = event_name
    self.arrived_at = 0
    self.status = status
    self.endpoint = endpoint
    self.age = age
    self.read_bytes = read_bytes
    self.wrote_bytes = wrote_bytes
    self.reason = reason
    self.ncircs = ncircs

class StreamBwEvent:
  def __init__(self, event_name, strm_id, read, written):
    self.event_name = event_name
    self.strm_id = int(strm_id)
    self.bytes_read = int(read)
    self.bytes_written = int(written)

class LogEvent:
  def __init__(self, level, msg):
    self.event_name = self.level = level
    self.msg = msg

class AddrMapEvent:
  def __init__(self, event_name, from_addr, to_addr, when):
    self.event_name = event_name
    self.from_addr = from_addr
    self.to_addr = to_addr
    self.when = when

class BWEvent:
  def __init__(self, event_name, read, written):
    self.event_name = event_name
    self.read = read
    self.written = written
    
#TODO:  make this init function less retarded
class StatusEvent:
  def __init__(self, event_name, body):
    self.event_name = event_name
    self.text = body
    self.data = {}
    try:
      vals = body.split(" ")
      self.severity = vals.pop(0)
      self.status_event = vals.pop(0)
      i = 0
      while i < len(vals):
        val = vals[i].split("=")
        key = val[0]
        val = val[1]
        if val.find('"') != -1:
          if val.count('"') % 2 != 0:
            val = val.replace('"', "")
            while True:
              i += 1
              next_val = vals[i]
              if next_val.find('"') != -1:
                next_val = next_val.replace('"', "")
                val += " " + next_val
                break
              else:
                val += " " + next_val
        self.data[key] = val
        i += 1
    except:
      print("StatusEvent was improperly formatted:  %s" % (body))
      
class ORCircuitEvent:
  def __init__(self, event_name, body):
    self.event_name = event_name
    self.text = body
    vals = body.split(" ")
    try:
      self.msgType = vals[0]
      self.prevCircId = int(vals[1])
      self.prevHexId = vals[2]
      if self.prevHexId in ("0", "0000000000000000000000000000000000000000"):
        self.prevHexId = None
      self.nextCircId = int(vals[3])
      self.nextHexId = vals[4]
      if self.nextHexId in ("0", "0000000000000000000000000000000000000000"):
        self.nextHexId = None
      if self.msgType == "PAYMENT":
        self.msgData = vals[5].decode("base64")
      else:
        self.msgData = vals[5]
    except:
      print("PaymentEvent was improperly formatted:  %s" % (body))
      
class TokenLevelEvent:
  def __init__(self, event_name, body):
    self.event_name = event_name
    self.text = body
    vals = body.split(" ")
    try:
      self.circ_id = int(vals[0])
      self.reads = int(vals[1])
      self.writes = int(vals[2])
      self.reads_added = int(vals[3])
      self.writes_added = int(vals[4])
    except:
      print("TokenLevelEvent was improperly formatted:  %s" % (body))
      
class NewConsensusEvent:
  def __init__(self, event_name, data):
    self.event_name = event_name
    self.data = data
    return

class UnknownEvent:
  def __init__(self, event_name, event_string):
    self.event_name = event_name
    self.event_string = event_string

class ExitPolicyLine:
  """ Class to represent a line in a Router's exit policy in a way 
      that can be easily checked. """
  def __init__(self, match, ip_mask, port_low, port_high):
    self.match = match
    if ip_mask == "*":
      self.ip = 0
      self.netmask = 0
    else:
      if not "/" in ip_mask:
        self.netmask = 0xFFFFFFFF
        ip = ip_mask
      else:
        ip, mask = ip_mask.split("/")
        if re.match(r"\d+.\d+.\d+.\d+", mask):
          self.netmask=struct.unpack(">I", socket.inet_aton(mask))[0]
        else:
          self.netmask = ~(2**(32 - int(mask)) - 1)
      self.ip = struct.unpack(">I", socket.inet_aton(ip))[0]
    self.ip &= self.netmask
    if port_low == "*":
      self.port_low,self.port_high = (0,65535)
    else:
      if not port_high:
        port_high = port_low
      self.port_low = int(port_low)
      self.port_high = int(port_high)
  
  #Josh:  now assumes that you're passing an int:
  def check(self, ip, port):
    """Check to see if an ip and port is matched by this line. 
     Returns true if the line is an Accept, and False if it is a Reject. """
    #ip = struct.unpack(">I", socket.inet_aton(ip))[0]
    if (ip & self.netmask) == self.ip:
      if self.port_low <= port and port <= self.port_high:
        return self.match
    return -1

class RouterVersion:
  """ Represents a Router's version. Overloads all comparison operators
      to check for newer, older, or equivalent versions. """
  def __init__(self, version):
    if version:
      v = re.search("^(\d+).(\d+).(\d+).(\d+)", version).groups()
      self.version = int(v[0])*0x1000000 + int(v[1])*0x10000 + int(v[2])*0x100 + int(v[3])
      self.ver_string = version
    else: 
      self.version = version
      self.ver_string = "unknown"

  def __lt__(self, other): return self.version < other.version
  def __gt__(self, other): return self.version > other.version
  def __ge__(self, other): return self.version >= other.version
  def __le__(self, other): return self.version <= other.version
  def __eq__(self, other): return self.version == other.version
  def __ne__(self, other): return self.version != other.version
  def __str__(self): return self.ver_string

class Router:
  """ 
  Class to represent a router from a descriptor. Can either be
  created from the parsed fields, or can be built from a
  descriptor+NetworkStatus 
  """     
  def __init__(self, idhex, name, bw, down, exitpolicy, flags, ip, version, os, uptime, country, isExit, allowDHT):
    self.idhex = idhex
    self.nickname = name
    self.bw = bw
    self.exitpolicy = exitpolicy
    self.flags = flags
    self.down = down
    self.ip = struct.unpack(">I", socket.inet_aton(ip))[0]
    self.version = RouterVersion(version)
    self.os = os
    self.list_rank = 0 # position in a sorted list of routers.
    self.uptime = uptime
    #will be set to the 2-letter country code if we can figure it out from the IP, None otherwise
    self.country = None
    if country != "??":
      self.country = country
    #ip in the form x.x.x.x
    self.ip_str = ip
    #whether this node allows any exit traffic
    self.isExit = isExit
    #: whether this node allows DHT exit traffic
    self.allowsDHT = allowDHT

  def __str__(self):
    s = self.idhex, self.nickname
    return s.__str__()

  def build_from_desc(desc, ns):
    """
    Static method of Router that parses a descriptor string into this class.
    'desc' is a full descriptor as a string. 
    'ns' is a TorCtl.NetworkStatus instance for this router (needed for
    the flags, the nickname, and the idhex string). 
    Returns a Router instance.
    """
    # XXX: Compile these regular expressions? This is an expensive process
    # Use http://docs.python.org/lib/profile.html to verify this is 
    # the part of startup that is slow
    exitpolicy = []
    dead = not ("Running" in ns.flags)
    bw_observed = 0
    version = None
    os = None
    uptime = 0
    ip = 0
    router = "[none]"

    for line in desc:
      rt = rtre_.match(line)
      fp = fpre_.match(line)
      pl = plre_.match(line)
      ac = acre_.match(line)
      rj = rjre_.match(line)
      bw = bwre_.match(line)
      up = upre_.match(line)
      if hire_.match(line):
        #dead = 1 # XXX: Technically this may be stale..
        if ("Running" in ns.flags):
          plog("INFO", "Hibernating router "+ns.nickname+" is running..")
      if ac:
        exitpolicy.append(ExitPolicyLine(True, *ac.groups()))
      elif rj:
        exitpolicy.append(ExitPolicyLine(False, *rj.groups()))
      elif bw:
        bw_observed = int(bw.group(1))
      elif pl:
        version, os = pl.groups()
      elif up:
        uptime = int(up.group(1))
      elif rt:
        router,ip = rt.groups()
    if router != ns.nickname:
      plog("NOTICE", "Got different names " + ns.nickname + " vs " +
             router + " for " + ns.idhex)
    if not bw_observed and not dead and ("Valid" in ns.flags):
      plog("INFO", "No bandwidth for live router " + ns.nickname)
    if not version or not os:
      plog("INFO", "No version and/or OS for router " + ns.nickname)
    return Router(ns.idhex, ns.nickname, bw_observed, dead, exitpolicy,
        ns.flags, ip, version, os, uptime)
  build_from_desc = Callable(build_from_desc)

  def update_to(self, new):
    """ Somewhat hackish method to update this router to be a copy of
    'new' """
    if self.idhex != new.idhex:
      plog("ERROR", "Update of router "+self.nickname+"changes idhex!")
    self.idhex = new.idhex
    self.nickname = new.nickname
    self.bw = new.bw
    self.exitpolicy = new.exitpolicy
    self.flags = new.flags
    self.ip = new.ip
    self.version = new.version
    self.os = new.os
    self.uptime = new.uptime

  def will_exit_to(self, ip, port):
    """ Check the entire exitpolicy to see if the router will allow
        connections to 'ip':'port' """
    for line in self.exitpolicy:
      ret = line.check(ip, port)
      if ret != -1:
        return ret
    plog("WARN", "No matching exit line for "+self.nickname)
    return False
   
class TorControlProtocol(basic.LineReceiver):
  """A Connection represents a connection to the Tor process via the 
     control port."""
  def __init__(self, torApp):
    self.torApp = torApp
    self._handler = None
    self._handleFn = None
    self._callbackQueue = []
    self._closedEx = None
    self._closed = 0
    self._closeHandler = None
    self._debugLog = True
    #CTL:  have to deal with the above variables, most of them are obsolete now
    self._lines = []
    self.multiline = False
    
  def connectionMade(self):
    self.factory.clientConnectionSucceeded(self)
    
  def connectionLost(self, reason):
    if not self.torApp.is_stopping():
      self._err((type(reason.value), reason.value, None))

  def set_close_handler(self, handler):
    """Call 'handler' when the Tor process has closed its connection or
       given us an exception.  If we close normally, no arguments are
       provided; otherwise, it will be called with an exception as its
       argument.
    """
    self._closeHandler = handler

  def close(self):
    """Shut down this controller connection"""
    if self.transport:
      self.transport.loseConnection()
    self._closed = 1
    
  def is_closed(self):
    return self._closed
    
  def lineReceived(self, line):
    """Main subthread loop: Read commands from Tor, and handle them either
       as events or as responses to other commands.
    """
    try:
      isEvent = self.parse_line(line)
    except:
      self._err(sys.exc_info())
      return
    
    if isEvent == None:
      return

    reply = self._lines
    try:
      if isEvent:
        if self._handler is not None:
          self.handle_event(time.time(), reply)
      else:
        cb = self._callbackQueue.pop(0)
        cb(reply)
    except Exception, e:
      errorMsg = "Tor control callback failed"
      if isEvent:
        errorMsg = "Tor event handler failed"
      log_ex(e, errorMsg)
    finally:
      self._lines = []

  def _err(self, (tp, ex, tb), fromEventLoop=0):
    """DOCDOC"""
    self._closedEx = ex
    self.close()
    if self._closeHandler is not None:
      self._closeHandler(tp, ex, tb)
    return

  def handle_event(self, timestamp, reply):
    if reply[0][0] == "650" and reply[0][1] == "OK":
      plog("DEBUG", "Ignoring incompatible syntactic sugar: 650 OK")
      return
    try:
      self._handleFn(timestamp, reply)
    except Exception, e:
      for code, msg, data in reply:
          plog("WARN", "No event for: "+str(code)+" "+str(msg))
#      self._err(sys.exc_info(), 1)
      log_ex(e, "Error in an event handler")
      return

  def _sendImpl(self, sendFn, msg):
    """Create a deferred that will be triggered when we receive the response"""

    if self._closedEx is not None:
      raise self._closedEx
    elif self._closed:
      raise TorCtlClosed()
    
    d = Deferred()
    def cb(reply, d=d):
      if reply == "EXCEPTION":
        d.errback(Failure(self._closedEx))
      else:
        d.callback(reply)
    self._callbackQueue.append(cb)
    sendFn(msg) # _doSend(msg)
    return d

  def set_event_handler(self, handler):
    """Cause future events from the Tor process to be sent to 'handler'.
    """
    self._handler = handler
    self._handleFn = handler._handle1

  def parse_line(self, line):
    if self.multiline:
      if self._debugLog:
        log_data(line)
      if line in (".", "650 OK"):
        self._lines[0] = (self._lines[0][0], self._lines[0][1], unescape_dots("\r\n".join(self.more)))
        isEvent = (self._lines and self._lines[0][0][0] == '6')
        self.multiline = False
        if isEvent: # Need "250 OK" if it's not an event. Otherwise, end
          return isEvent
      self.more.append(line)
      return None
    if self._debugLog:
       log_data(line)
    if len(line)<4:
      raise ProtocolError("Badly formatted reply line: Too short")
    code = line[:3]
    tp = line[3]
    s = line[4:]
    if tp == "-":
      self._lines.append((code, s, None))
    elif tp == " ":
      self._lines.append((code, s, None))
      isEvent = (self._lines and self._lines[0][0][0] == '6')
      return isEvent
    elif tp != "+":
      raise ProtocolError("Badly formatted reply line: unknown type %r"%tp)
    else:
      self.multiline = True
      self.more = []
      self._lines.append((code, s, ""))
    return None

  def _doSend(self, msg):
    if self._debugLog:
      amsg = msg
      lines = amsg.split("\n")
      if len(lines) > 2:
        amsg = "\n".join(lines[:2]) + "\n"
      log_data(amsg)
    if type(msg) == unicode:
      pass
    self.transport.write(msg)

  def sendAndRecv(self, data="", expectedTypes=("250", "251")):
    """Helper: Send a command 'msg' to Tor, and wait for a command
       in response.  If the response type is in expectedTypes,
       return a list of (tp,body,extra) tuples.  If it is an
       error, raise ErrorReply.  Otherwise, raise ProtocolError.
    """
    if type(data) == types.ListType:
      data = "".join(data)
    assert data.endswith("\r\n")

    d = self._sendImpl(self._doSend, data)
    def response(lines):
      # print lines
      for tp, msg, _ in lines:
        if tp[0] in '45':
          raise ErrorReply("%s %s (in response to %s)"%(tp, msg, data))
        if tp not in expectedTypes:
          raise ProtocolError("Unexpected message type %r"%tp)
      return lines
    #so that errors from both the callback and the original function get to later functions
    def error(failure):
      return failure
    d.addCallback(response)
    d.addErrback(error)
    return d

  def authenticate(self, secret=""):
    """Send an authenticating secret to Tor.  You'll need to call this
       method before Tor can start.
    """
    #hexstr = binascii.b2a_hex(secret)
    return self.sendAndRecv("AUTHENTICATE \"%s\"\r\n"%secret)

  def get_option(self, name):
    """Get the value of the configuration option named 'name'.  To
       retrieve multiple values, pass a list for 'name' instead of
       a string.  Returns a list of (key,value) pairs.
       Refer to section 3.3 of control-spec.txt for a list of valid names.
    """
    if not isinstance(name, str):
      name = " ".join(name)
    d = self.sendAndRecv("GETCONF %s\r\n" % name)
    def response(lines):
      r = []
      for _,line,_ in lines:
        try:
          key, val = line.split("=", 1)
          r.append((key,val))
        except ValueError:
          r.append((line, None))
      return r
    d.addCallback(response)
    return d

  def set_option(self, key, value):
    """Set the value of the configuration option 'key' to the value 'value'.
    """
    return self.set_options([(key, value)])

  def set_options(self, kvlist):
    """Given a list of (key,value) pairs, set them as configuration
       options.
    """
    if not kvlist:
      return
    msg = " ".join(["%s=%s"%(k,quote(v)) for k,v in kvlist])
    return self.sendAndRecv("SETCONF %s\r\n"%msg)

  def reset_options(self, keylist):
    """Reset the options listed in 'keylist' to their default values.

       Tor started implementing this command in version 0.1.1.7-alpha;
       previous versions wanted you to set configuration keys to "".
       That no longer works.
    """
    self.sendAndRecv("RESETCONF %s\r\n"%(" ".join(keylist)))

  def get_network_status(self, who="all"):
    """Get the entire network status list. Returns a list of
       TorCtl.NetworkStatus instances."""
    d = self.sendAndRecv("GETINFO ns/"+who+"\r\n")
    def response(nsBody):
      nsBody = nsBody[0][2]
      if not nsBody:
        return None
      return parse_ns_body(nsBody)
    d.addCallback(response)
    return d

  def get_router(self, ns):
    """Fill in a Router class corresponding to a given NS class"""
    desc = self.sendAndRecv("GETINFO desc/id/" + ns.idhex + "\r\n")[0][2].split("\n")
    return Router.build_from_desc(desc, ns)


  def read_routers(self, nslist):
    """ Given a list a NetworkStatuses in 'nslist', this function will 
        return a list of new Router instances.
    """
    bad_key = 0
    new = []
    for ns in nslist:
      try:
        r = self.get_router(ns)
        new.append(r)
      except ErrorReply:
        bad_key += 1
        if "Running" in ns.flags:
          plog("NOTICE", "Running router "+ns.nickname+"="
             +ns.idhex+" has no descriptor")
      except Exception, e:
        log_ex(e, "Unexpected error while loading routers")
        continue
  
    return new

  def get_info(self, name):
    """Return the value of the internal information field named 'name'.
       Refer to section 3.9 of control-spec.txt for a list of valid names.
       DOCDOC
    """
    if not isinstance(name, str):
      name = " ".join(name)
    def response(lines):
      data = {}
      for _,msg,more in lines:
        if msg == "OK":
          break
        try:
          k,rest = msg.split("=",1)
        except ValueError:
          raise ProtocolError("Bad info line %r",msg)
        if more:
          data[k] = more
        else:
          data[k] = rest
      return data
    d = self.sendAndRecv("GETINFO %s\r\n"%name)
    d.addCallback(response)
    return d

  def set_events(self, events, extended=False):
    """Change the list of events that the event handler is interested
       in to those in 'events', which is a list of event names.
       Recognized event names are listed in section 3.3 of the control-spec
    """
    if extended:
      plog ("DEBUG", "SETEVENTS EXTENDED %s\r\n" % " ".join(events))
      return self.sendAndRecv("SETEVENTS EXTENDED %s\r\n" % " ".join(events))
    else:
      return self.sendAndRecv("SETEVENTS %s\r\n" % " ".join(events))

  def save_conf(self):
    """Flush all configuration changes to disk.
    """
    return self.sendAndRecv("SAVECONF\r\n")

  def send_signal(self, sig):
    """Send the signal 'sig' to the Tor process; The allowed values for
       'sig' are listed in section 3.6 of control-spec.
    """
    sig = { 0x01 : "HUP",
        0x02 : "INT",
        0x03 : "NEWNYM",
        0x0A : "USR1",
        0x0C : "USR2",
        0x0F : "TERM" }.get(sig,sig)
    return self.sendAndRecv("SIGNAL %s\r\n"%sig)

  def resolve(self, host):
    """ Launch a remote hostname lookup request:
        'host' may be a hostname or IPv4 address
    """
    # TODO: handle "mode=reverse"
    return self.sendAndRecv("RESOLVE %s\r\n"%host)

  def map_address(self, kvList):
    """ Sends the MAPADDRESS command for each of the tuples in kvList """
    if not kvList:
      return
    m = " ".join([ "%s=%s" for k,v in kvList])
    lines = self.sendAndRecv("MAPADDRESS %s\r\n"%m)
    r = []
    for _,line,_ in lines:
      try:
        key, val = line.split("=", 1)
      except ValueError:
        raise ProtocolError("Bad address line %r",v)
      r.append((key,val))
    return r

  def extend_circuit(self, circid, hops):
    """Tell Tor to extend the circuit identified by 'circid' through the
       servers named in the list 'hops'.
    """
    if circid is None:
      circid = "0"
    plog("DEBUG", "Extending circuit")
    d = self.sendAndRecv("EXTENDCIRCUIT %d %s\r\n"
                  %(circid, ",".join(hops)))
    def response(lines):
      tp,msg,_ = lines[0]
      m = re.match(r'EXTENDED (\S*)', msg)
      if not m:
        raise ProtocolError("Bad extended line %r",msg)
      plog("DEBUG", "Circuit extended")
      return int(m.group(1))
    d.addCallback(response)
    return d

  def redirect_stream(self, streamid, newaddr, newport=""):
    """DOCDOC"""
    if newport:
      return self.sendAndRecv("REDIRECTSTREAM %d %s %s\r\n"%(streamid, newaddr, newport))
    else:
      return self.sendAndRecv("REDIRECTSTREAM %d %s\r\n"%(streamid, newaddr))

  def attach_stream(self, streamid, circid, hop=None):
    """Attach a stream to a circuit, specify both by IDs. If hop is given, 
       try to use the specified hop in the circuit as the exit node for 
       this stream.
    """
    if hop:
      plog("DEBUG", "Attaching stream: "+str(streamid)+" to hop "+str(hop)+" of circuit "+str(circid))
      return self.sendAndRecv("ATTACHSTREAM %d %d HOP=%d\r\n"%(streamid, circid, hop))
    else:
      plog("DEBUG", "Attaching stream: "+str(streamid)+" to circuit "+str(circid))
      return self.sendAndRecv("ATTACHSTREAM %d %d\r\n"%(streamid, circid))

  def close_stream(self, streamid, reason=0, flags=()):
    """DOCDOC"""
    return self.sendAndRecv("CLOSESTREAM %d %s %s\r\n"%(streamid, reason, "".join(flags)))

  def close_circuit(self, circid, reason=0, flags=()):
    """DOCDOC"""
    return self.sendAndRecv("CLOSECIRCUIT %d %s %s\r\n"
              %(circid, reason, "".join(flags)))

  def post_descriptor(self, desc):
    return self.sendAndRecv("+POSTDESCRIPTOR purpose=controller\r\n%s"%escape_dots(desc))

def parse_ns_body(data):
  """Parse the body of an NS event or command into a list of
     NetworkStatus instances"""
  nsgroups = re.compile(r"^r ", re.M).split(data)
  nsgroups.pop(0)
  nslist = []
  for nsline in nsgroups:
    m = re.search(r"^s((?:\s\S*)+)", nsline, re.M)
    flags = m.groups()
    flags = flags[0].strip().split(" ")
    m = re.match(r"(\S+)\s(\S+)\s(\S+)\s(\S+\s\S+)\s(\S+)\s(\d+)\s(\d+)", nsline)
    nslist.append(NetworkStatus(*(m.groups() + (flags,))))
  return nslist

class EventHandler:
  """An 'EventHandler' wraps callbacks for the events Tor can return. 
     Each event argument is an instance of the corresponding event
     class."""
  def __init__(self):
    """Create a new EventHandler."""
    self._map1 = {
      "CIRC" : self.circ_status_event,
      "STREAM" : self.stream_status_event,
      "ORCONN" : self.or_conn_status_event,
      "STREAM_BW" : self.stream_bw_event,
      "BW" : self.bandwidth_event,
      "DEBUG" : self.msg_event,
      "INFO" : self.msg_event,
      "NOTICE" : self.msg_event,
      "WARN" : self.msg_event,
      "ERR" : self.msg_event,
      "NEWDESC" : self.new_desc_event,
      "ADDRMAP" : self.address_mapped_event,
      "NS" : self.ns_event,
      "STATUS_GENERAL" : self.general_status_event,
      "STATUS_CLIENT" : self.client_status_event,
      "STATUS_SERVER" : self.server_status_event,
      "ORCIRCUIT" : self.orcircuit_event,
      "NEWCONSENSUS" : self.new_consensus_event,
      "TOKEN_LEVELS" : self.token_level_event
      }

  def _handle1(self, timestamp, lines):
    """Dispatcher: called from Connection when an event is received."""
    for code, msg, data in lines:
      event = self._decode1(msg, data)
      event.arrived_at = timestamp
      self.heartbeat_event(event)
      self._map1.get(event.event_name, self.unknown_event)(event)

  def _decode1(self, body, data):
    """Unpack an event message into a type/arguments-tuple tuple."""
    if " " in body:
      evtype,body = body.split(" ",1)
    else:
      evtype,body = body,""
    evtype = evtype.upper()
    if evtype == "CIRC":
      m = re.match(r"(\d+)\s+(\S+)(\s\S+)?(\s\S+)?(\s\S+)?(\s\S+)?", body)
      if not m:
        raise ProtocolError("CIRC event misformatted.")
      ident,status,path,purpose,reason,remote = m.groups()
      ident = int(ident)
      if path:
        if "PURPOSE=" in path:
          remote = reason
          reason = purpose
          purpose = path
          path=[]
        else:
          path = path.strip().split(",")
      else:
        path = []
      if purpose: purpose = purpose[9:]
      if reason: reason = reason[8:]
      if remote: remote = remote[15:]
      event = CircuitEvent(evtype, ident, status, path, reason, remote)
    elif evtype == "STREAM":
      #plog("DEBUG", "STREAM: "+body)
      m = re.match(r"(\S+)\s+(\S+)\s+(\S+)\s+(\S*):(\d+)(\sREASON=\S+)?(\sREMOTE_REASON=\S+)?(\sSOURCE=\S+)?(\sSOURCE_ADDR=\S+)?(\sPURPOSE=\S+)?", body)
      if not m:
        raise ProtocolError("STREAM event misformatted.")
      ident,status,circ,target_host,target_port,reason,remote,source,source_addr,purpose = m.groups()
      ident,circ = map(int, (ident,circ))
      if reason: reason = reason[8:]
      if remote: remote = remote[15:]
      if source: source = source[8:]
      if source_addr: source_addr = source_addr[13:]
      if purpose: purpose = purpose[9:]
      event = StreamEvent(evtype, ident, status, circ, target_host,
               int(target_port), reason, remote, source, source_addr, purpose)
    elif evtype == "ORCONN":
      m = re.match(r"(\S+)\s+(\S+)(\sAGE=\S+)?(\sREAD=\S+)?(\sWRITTEN=\S+)?(\sREASON=\S+)?(\sNCIRCS=\S+)?", body)
      if not m:
        raise ProtocolError("ORCONN event misformatted.")
      target, status, age, read, wrote, reason, ncircs = m.groups()

      #plog("DEBUG", "ORCONN: "+body)
      if ncircs: ncircs = int(ncircs[8:])
      else: ncircs = 0
      if reason: reason = reason[8:]
      if age: age = int(age[5:])
      else: age = 0
      if read: read = int(read[6:])
      else: read = 0
      if wrote: wrote = int(wrote[9:])
      else: wrote = 0
      event = ORConnEvent(evtype, status, target, age, read, wrote,
                reason, ncircs)
    elif evtype == "STREAM_BW":
      m = re.match(r"(\d+)\s+(\d+)\s+(\d+)", body)
      if not m:
        raise ProtocolError("STREAM_BW event misformatted.")
      event = StreamBwEvent(evtype, *m.groups())
    elif evtype == "BW":
      m = re.match(r"(\d+)\s+(\d+)", body)
      if not m:
        raise ProtocolError("BANDWIDTH event misformatted.")
      read, written = map(long, m.groups())
      event = BWEvent(evtype, read, written)
    elif evtype in ("DEBUG", "INFO", "NOTICE", "WARN", "ERR"):
      event = LogEvent(evtype, body)
    elif evtype == "NEWDESC":
      event = NewDescEvent(evtype, body.split(" "))
    elif evtype == "ADDRMAP":
      # TODO: Also parse errors and GMTExpiry
      m = re.match(r'(\S+)\s+(\S+)\s+(\"[^"]+\"|\w+)', body)
      if not m:
        raise ProtocolError("ADDRMAP event misformatted.")
      fromaddr, toaddr, when = m.groups()
      if when.upper() == "NEVER":  
        when = None
      else:
        when = time.strptime(when[1:-1], "%Y-%m-%d %H:%M:%S")
      event = AddrMapEvent(evtype, fromaddr, toaddr, when)
    elif evtype == "NS":
      event = NetworkStatusEvent(evtype, parse_ns_body(data))
    elif evtype in ("STATUS_GENERAL", "STATUS_CLIENT", "STATUS_SERVER"):
      event = StatusEvent(evtype, body)
    elif evtype in ("ORCIRCUIT"):
      event = ORCircuitEvent(evtype, body)
    elif evtype in ("NEWCONSENSUS"):
      event = NewConsensusEvent(evtype, parse_ns_body(data))
    elif evtype in ("TOKEN_LEVELS"):
      event = TokenLevelEvent(evtype, body)
    else:
      event = UnknownEvent(evtype, body)

    return event

  def heartbeat_event(self, event):
    """Called before any event is recieved. Convenience function
       for any cleanup/setup/reconfiguration you may need to do.
    """
    pass

  def unknown_event(self, event):
    """Called when we get an event type we don't recognize.  This
       is almost alwyas an error.
    """
    raise NotImplemented()

  def circ_status_event(self, event):
    """Called when a circuit status changes if listening to CIRCSTATUS
       events."""
    raise NotImplemented()

  def stream_status_event(self, event):
    """Called when a stream status changes if listening to STREAMSTATUS
       events.  """
    raise NotImplemented()

  def stream_bw_event(self, event):
    raise NotImplemented()

  def or_conn_status_event(self, event):
    """Called when an OR connection's status changes if listening to
       ORCONNSTATUS events."""
    raise NotImplemented()

  def bandwidth_event(self, event):
    """Called once a second if listening to BANDWIDTH events.
    """
    raise NotImplemented()

  def new_desc_event(self, event):
    """Called when Tor learns a new server descriptor if listenting to
       NEWDESC events.
    """
    raise NotImplemented()

  def msg_event(self, event):
    """Called when a log message of a given severity arrives if listening
       to INFO_MSG, NOTICE_MSG, WARN_MSG, or ERR_MSG events."""
    raise NotImplemented()

  def ns_event(self, event):
    raise NotImplemented()

  def address_mapped_event(self, event):
    """Called when Tor adds a mapping for an address if listening
       to ADDRESSMAPPED events.
    """
    raise NotImplemented()
  
  def general_status_event(self, event):
    """Called when Tor prints one of a number of specified status messages
       pertaining to the general state of the program.
    """
    raise NotImplemented()
  
  def server_status_event(self, event):
    """Called when Tor prints one of a number of specified status messages
       related to the server functionality.
    """
    raise NotImplemented()
  
  def client_status_event(self, event):
    """Called when Tor prints one of a number of specified status messages
       related to the client state.
    """
    raise NotImplemented()
    
  def new_consensus_event(self, event):
    """Called when Tor begins using a new consensus document
    """
    raise NotImplemented()