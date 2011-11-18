#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Contains the bank login protocol"""

import struct
import socket

from twisted.protocols.basic import Int16StringReceiver

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common import Globals
from common.Errors import BadLoginPasswordError
from common.classes import SymmetricKey
from core.bank import BankMessages

class LoginProtocol(Int16StringReceiver):
  """Protocol for LOGIN messages.  Calls on_login_failure if the protocol fails"""
  def connectionMade(self):
    log_msg('Sending login message...', 2)
    signedFingerprint = Globals.PRIVATE_KEY.sign(Globals.FINGERPRINT)
    publicKey = Basic.long_to_bytes(long(Globals.PRIVATE_KEY.n), 128)
    protocol = 1
    msg = struct.pack('!B128s50s50s128s', protocol, signedFingerprint, self.factory.username, self.factory.password, publicKey)
    self.sendString(msg)
    
  def stringReceived(self, data):
    """Called when the login response arrives"""
    self.factory.done = True
    self.responseReceived = True
    text = None
    try:
      protocol, data = Basic.read_byte(data)
      if protocol == 1:
        returnCode, data = Basic.read_byte(data)
        if returnCode == 1:
          format = '!IIII4sI'
          (balance, currentACoinInterval, currentACoinIntervalExpiration, nextAcoinIntervalExpiration, host, port), blob = Basic.read_message(format, data)
          size = struct.calcsize(SymmetricKey.MESSAGE_FORMAT)
          authBlob = blob[:size]
          text = blob[size:]
          host = socket.inet_ntoa(host)
          self.factory.bank.on_new_info(balance, currentACoinInterval, currentACoinIntervalExpiration, nextAcoinIntervalExpiration)
          self.factory.bank.on_login_success(balance, authBlob, host, port, text)
        else:
          size = struct.calcsize('!I')
          timeout = struct.unpack('!I', data[:size])[0]
          text = data[size:]
          raise BadLoginPasswordError(timeout)
      else:
        raise Exception('unknown protocol: %s'%(protocol))
    except Exception, error:
      self.factory.bank.on_login_failure(error, text)
    finally:
      self.transport.loseConnection()
  
  def connectionLost(self, reason):
    if not self.factory.done:
      #log_ex(reason, "Login failed: %s" % (reason), 0)
      self.factory.bank.on_login_failure(reason)
      
class LoginFactory(BankMessages.BankConnectionFactory):
  """Factory for login messages"""
  protocol = LoginProtocol
  def __init__(self, bank, username, password):
    BankMessages.BankConnectionFactory.__init__(self, bank)
    self.username = username
    self.password = password
    self.done = False
    
  def clientConnectionFailed(self, connector, reason):
    BankMessages.BankConnectionFactory.clientConnectionFailed(self, connector, reason)
    self.bank.on_login_failure(reason)
  
  def clientConnectionLost(self, connector, reason):
    BankMessages.BankConnectionFactory.clientConnectionLost(self, connector, reason)
    if not self.done:
      self.bank.on_login_failure(reason)
      
