#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Python module to allow instances of our program to talk to each other"""

from twisted.internet import protocol
from twisted.protocols.basic import Int32StringReceiver

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals

#Listens for other BitBlinder instances to connect to us (who are acting as a relay, probably an exit).
class MessageServer:
  def __init__(self, host, port):
    #address to listen for BitBlinder connections on:
    self.host = host
    self.port = port
    #so we can stop listening later
    self.listener = None
    
  #Add a of handler for name, error if one already exists
  def add_service(self, name, handler):
    if not SERVICES.has_key(name):
      SERVICES[name] = handler
    else:
      log_msg("A service is already defined for %s!" % (name), 0)

  def start_listening(self):
    self.listener = Globals.reactor.listenTCP(self.port, MessageServerFactory(), interface=self.host)
    
  def stop_listening(self):
    if self.listener:
      #TODO:  IMPORTANT:  this might be a deferred sometimes, so be careful  :(
      self.listener.stopListening()
      
class MessageReceiver(Int32StringReceiver):
  """Deprecated"""
  def __init__(self):
    Int32StringReceiver.__init__(self)
    
  def _get_message_arg(self, argString, argNum=0):
    """Assumes argString contains a number of space-delineated arguments.  Returns
    the argNum'th argument (0-indexed), and the argString without that argument"""
    try:
      if not argString:
        return (None, argString)
      vals = argString.split(" ")
      val = vals[argNum]
      retStr = " ".join(vals[:argNum])
      if argNum < len(vals)-1:
        retStr += " ".join(vals[argNum+1:])
      return (val, retStr)
    except:
      return (None, argString)
    
  def stringReceived(self, msg):
    msg, args = self._get_message_arg(msg)
    self.messageReceived(msg, args)
    
  def messageReceived(self, msg, args):
    """Subclasses should override this"""
    return
  
  def sendMessage(self, msg, args=""):
    self.sendString(msg + " " + str(args))
      
class MessageServerProtocol(MessageReceiver):
  """
  This is the incoming protocol. An instance of this class will be created
  for each socket opened to the server.
  """
  def __init__(self):
    #need to track the child class for actually handling messages  :(
    self.handler = None
  
  def messageReceived(self, msg, args):
    #if we dont know what type of protocol is happening here yet:
    if not self.handler:
      if SERVICES.has_key(msg):
        #create the handler
        self.handler = SERVICES[msg](self, args)
      else:
        log_msg("Unknown MessageServerHandler = %s" % (msg), 1)
        self.transport.loseConnection()
    else:
      self.handler.handle_message(msg, args)
      
  def connectionLost(self, reason):
    if self.handler:
      self.handler.handle_message("CLOSED", [str(reason)])
      
class MessageServerFactory(protocol.ServerFactory):
  """
  This is what Twisted uses to spawn the incoming proxy server. To accept
  TCP connections, you create an instance of a Factory class like this one,
  and send it to the reactor.listenTCP method.
  """
  protocol = MessageServerProtocol
  
  def clientConnectionFailed(self, connector, reason):
    log_msg("MessageServer:  Connection failed:  %s" % (str(reason)), 2)
    if connector.handler:
      connector.handler.handle_message("CLOSED", [str(reason)])
  
  def clientConnectionLost(self, connector, reason):
    log_msg("MessageServer:  Connection lost", 4)
    if connector.handler:
      connector.handler.handle_message("CLOSED", [str(reason)])
    
#base class for handling connections to MessageServer
#inheriting classes should just override handle_message to implement their protocol
class MessageServerHandler:
  def __init__(self, conn, args):
    #the connection to the client
    self.clientConn = conn
  
  #sample handler function.  msg is a string, and args is a string
  def handle_message(self, msg, args):
    if msg == "HELLO":
      pass
    elif msg == "CLOSED":
      self.close(args[0])
    else:
      self.clientConn.sendMessage("FAIL", "Invalid command = %s" % (msg))
  
  #close the socket nicely, and inform the client that we're closing the connection
  def close(self, reason):
    try:
      if self.clientConn:
        self.clientConn.sendMessage("CLOSED", reason)
    except:
      pass
    if self.clientConn and self.clientConn.transport:
      self.clientConn.transport.loseConnection()
    
    
#Maps from messages to the handler that should be used.
SERVICES = {"HELLO" : MessageServerHandler}
  
