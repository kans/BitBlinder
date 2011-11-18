#!/usr/bin/python
# Copyright 2008-2009 Innominet
"""PAR2 Banking Server via Twisted with PostgreSQL backend"""
from __future__ import with_statement

import sys
import time
import signal
import binascii
import optparse
import os
from cPickle import dumps, loads

from twisted.internet import reactor, defer, threads, protocol
from twisted.protocols.basic import Int32StringReceiver

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Basic
from common.utils import Twisted
from common.classes import Logger
from common.classes import EncryptedDatagram
from common.classes import SymmetricKey
from common.classes import PrivateKey
from serverCommon import db
import BankUtil
import ACoinMessages

if os.path.exists("THIS_IS_DEBUG"):
  from common.conf import Dev as Conf
  import cProfile
  Globals.DEBUG = True
  Globals.PROFILER = cProfile.Profile()
else:
  from common.conf import Live as Conf
  Globals.DEBUG = False

parser = optparse.OptionParser()
parser.add_option('-p', '--port', dest='port', type='int', default=Conf.SERVER_PORT, 
                  metavar=str(Conf.SERVER_PORT), help='port to bind to serve clients')
parser.add_option('-t', '--time', dest='time', type='int', default=15, 
                  metavar='15', help='minutes between memory dumps')
parser.add_option('-s', '--sets', dest='sets', type='int', default=8, 
                  metavar='8', help='number of sets per interval to cache acoins in- \
                  total sets will be twice this number (which should be devisable by 2)')
parser.add_option('-n', '--non-daemon-mode', dest='mode', action="store_true", default=False, metavar='False',
                  help='specify to run in non-daemon-mode')
parser.add_option('--acoin-key-file', dest='akf', default=None, type='str', metavar='FILE', 
                  help='location of acoin private key RSA pem file')
parser.add_option('--bank-key-file', dest='bkf', default=None, type ='str', metavar='FILE', 
                  help='location of bank private key RSA pem file')
parser.add_option('-d', '--debug', dest='debug', type='int', default=2, 
                  metavar='2', help='debug lvl- int from 0 to 4')
(options, args) = parser.parse_args()
  
if not options.mode:
  signal.signal(signal.SIGHUP, signal.SIG_IGN)
if '--acoin-key-file' not in args:
  options.akf = 'private_keys/acoin.key'
if '--bank-key-file' not in args:
  options.bfk = 'private_keys/bank.key'
#number of current and previous acoin interval sets to be stored in memory
Globals.numberOfSets = options.sets
Globals.CURRENT_ACOIN_INTERVAL = []
#create all keys
Globals.ACOIN_KEY = PrivateKey.PrivateKey(options.akf)
Globals.GENERIC_KEY = PrivateKey.PrivateKey(options.bfk)
#is the reactor listening?
Globals.isListening = False
Globals.isInitialize = False

#used to cache responses for dropped packets
cache = {}
#used to enforce a max size on the cache
queue = []
#max requests in the cache
MAX_SIZE = 500
#TODO: this system is stupid, but only costs a MB of ram...

def initialize():
  """initialize coins and locks"""
  log_msg('Initializing cache.', 3)
  previous, current = BankUtil.get_intervals()
  Globals.Acoins = {previous: [], current: []}
  for i in range(Globals.numberOfSets+1):
    Globals.Acoins[previous].append(set())
    Globals.Acoins[current].append(set())
    
def on_new_interval():
  """removes expired acoins and locks from the cache and makes new ones"""
  previous, current = BankUtil.get_intervals()
  log_msg('New interval learned: %s!'%current, 3)
  if Globals.isInitialize:
    Globals.Acoins[current] = []
    for repo in range(Globals.numberOfSets+1):
      #create new ones
      Globals.Acoins[current].append(set())
    del(Globals.Acoins[previous-1])
  else:
    initialize()
    Globals.isInitialize = True

def start_listening():
  """called when we learn the current acoin interval"""
  #flush_scheduler()
  factory = protocol.ServerFactory()
  factory.protocol = TCPServer
  reactor.listenTCP(options.port, factory)
  reactor.listenUDP(options.port, UDPServer())
  log_msg('Server is listening on port: %s!' % (options.port), 2)
        
def main():
  """Launches the Serverfactoryprotocolthing """
  #run as a daemon
  Globals.logger = Logger.Logger(options.debug)
  Globals.logger.start_logs(["BANK", "errors"], "BANK", ".")
  Twisted.install_exception_handlers()
  BankUtil.update_local_acoin_interval(start_listening, on_new_interval)
  Globals.reactor = reactor
  log_msg('Server started: fail is imminent (not an error)!', 0)
  if Globals.DEBUG:
    def start_profiler():
      Globals.PROFILER.clear()
      Globals.PROFILER.enable()
    def stop_profiler():
      Globals.PROFILER.disable()
      Globals.PROFILER.dump_stats("temp.stats")
    reactor.callLater(15.0, start_profiler)
    reactor.callLater(75.0, stop_profiler)
  reactor.run()
  ACoinMessages.eventLogger.on_shutdown()
  log_msg("Shutdown cleanly", 2)
    
class UDPServer(protocol.DatagramProtocol):
  MAX_LENGTH = 1024
  
  """responsible for handling payment requests from the clients"""
  
  def datagramReceived(self, datagram, address):
    try:
      self.address = address
      log_msg('Datagram received from %s:%s!'%address, 3)
      msgType, msg = Basic.read_byte(datagram)
      #for compatability really
      if msgType == 1:
        #is it a replay?
        if not cache.has_key(msg):
          self.request = msg
          self.symKey = EncryptedDatagram.ServerSymKey(Globals.GENERIC_KEY)
          msg = self.symKey.decrypt(msg)
          #for compatability really
          request_type, msg = Basic.read_byte(msg)
          if request_type == 3:
            self.handler = ACoinMessages.Payment(self.reply, self.address) 
            self.handler.on_message(msg)
          else:
            raise Exception("Unknown request_type:  %s" % (request_type))
        else:
          self.reply(cache[msg], putInQueue=False)
          return
      else:
        raise Exception("Unknown msgType:  %s" % (msgType))
    except Exception, e:
      self.err(e)
    
  def reply(self, response, putInQueue=True, wasSuccess=True):
    """returns string msg to client"""
    #should this item go into the temporary cache for dropped packets?
    if putInQueue:
      global queue, cache
      if self.request not in cache:
        queue.append(self.request)
        cache[self.request] = response
        #kept while for jash, though only we element is ever added at a time
        while len(queue) > MAX_SIZE:
          del cache[queue.pop(0)]
    self.transport.write(response, self.address)
    log_msg('msg returned to client',  3)
    
  def err(self, err, optional=None):
    #TODO: move this over to an error log file
    log_msg('ERROR in request from ADDRESS:: %s:%s \n%s' %(self.address +(err,)))
    rep = str("An error was encountered with your request; contact kans or contact jash to get kans.")
    self.reply(rep, False, False)
  
  def drop_connection(self, reason = None):
    #log_msg('connection dropped by server', 2)
    self.transport.loseConnection()
  
  def connectionLost(self, reason):
    """is called when a connection is lost"""
    del(self.handler) #helping the garbage collector out...
    log_msg('connection lost: %s'%(reason.value), 2)
    
class TCPServer(Int32StringReceiver):
  MAX_LENGTH = 128 * 1024 * 1024 #128 megabytes
  """responsible for handling basic requests from the clients"""
  def __init__(self):
    #: handler for the  request
    self.handler = None
    #: symmetric key associated with the relay
    self.symKey = None
    #: tor hex id of the user sending the request
    self.hexId = 'unknown'

  def stringReceived(self, data):
    try:
      #if this is the first request on the connection, the data gets a handler
      if not self.handler:
        d = self.sym_decrypt(data)
        d.addCallback(self.handle_message)
        d.addErrback(self.err, optional="INVALID REQUEST")
      else:
        msg = self.symKey.decrypt(data)
        self.handler.on_message(msg)
    except Exception, e:
      self.err(e)
    
  def handle_message(self, msg):
    request_type, msg = Basic.read_byte(msg)
    #attach the correct handler
    if request_type == 1:
      self.handler =  ACoinMessages.Request(self.encrypted_reply, self.owner, self.hexId)
    elif request_type == 2:
      self.handler = ACoinMessages.Deposit(self.encrypted_reply, self.owner, self.hexId)
    elif request_type == 3:
      self.owner = self.transport.getPeer()
      self.handler =  ACoinMessages.Payment(self.reply, self.owner) 
    else:
      log_msg('invalid request: %s, %s' % (request_type, msg), 1)
      self.reply('invalid request: %s' % (request_type))
      #self.drop_connection()
      return
    self.handler.on_message(msg)
    
  def reply(self, msg):
    """returns string msg to client"""
    msg = str(msg)
    self.sendString(msg)
    log_msg('msg returned to client',  3)
    self.drop_connection()
    return
  
  def encrypted_reply(self,  msg):
    """returns an encrypted reply to the client"""
    msg = self.symKey.encrypt(msg)
    self.reply(msg)
    
  def err(self, err, optional=None):
    #TODO: move this over to an error log file
    log_msg('ERROR in request from ADDRESS: %s with HEXID: %s\n%s ' % (self.transport.getPeer(), self.hexId, err),  )
    rep = str("An error was encountered with your request; contact kans or contact jash to get kans.")
    if not self.symKey:
      self.reply(rep)
    else:
      self.encrypted_reply(rep)
  
  def drop_connection(self, reason = None):
    #log_msg('connection dropped by server', 2)
    self.transport.loseConnection()
  
  def connectionLost(self, reason):
    """is called when a connection is lost"""
    del(self.handler) #helping the garbage collector out...
    log_msg('connection lost: %s'%(reason.value), 2)
    
  def sym_decrypt(self, msg):
    """this is disgusting because we use two different systems for symmetric encryption
    type 0 uses SmmetricKey while
    type 1 uses EncryptedDatagram
    quirks: 
    0 must also update the nonce stored in the db
    1 performs heavy crypto and has non symmetric client/server side encryption/decryption"""
    if not self.symKey:
      msgType, msg = Basic.read_byte(msg)
      if msgType is 0:
        #get the tor fingerprint so we know how to decrypt the message
        (binId,), msg = Basic.read_message('!20s', msg)
        #convert the tor fingerprint back into hex
        self.hexId = binascii.hexlify(binId).upper()
        #get the symmetric key out of the database:
        sql = "SELECT Owner, Public_Key, Msgnum, auth_blob FROM Relays WHERE Tor_Id = %s"
        inj = (self.hexId,)
        d = db.read(sql, inj)
        #get the sym key from the db and decrypt the msg
        d.addCallback(self.fetch_sym_key, msg)
        #update the message number in the database
        d.addCallback(self.update_db)
      elif msgType is 1:
        self.symKey = EncryptedDatagram.ServerSymKey(Globals.GENERIC_KEY)
        d = threads.deferToThread(self.get_sym_key_value, msg)
      else:
        raise Exception("Unknown msgType:  %s" % (msgType))
    else:
      raise Exception('Passing more than one message per tcp connection is currently not supported')
    return d
    
  def fetch_sym_key(self, tup, encrypted):
    """utility function to get the authblob from the database which is set at time of login"""
    assert len(tup) == 1
    self.owner, n, self.previousMsgnum, authBlob = tup[0]
    self.symKey = SymmetricKey.SymmetricKey(authBlob)
    return self.symKey.decrypt(encrypted)
    
  def update_db(self, blob):
    """utility function that updates verifies the nonce in the msg and then updates the nonce in the db"""
    protocol, blob = Basic.read_byte(blob)
    if protocol is not 1:
      raise Exception('change protocol')
    msgNum, blob = Basic.read_short(blob)
    #the msgNum is a nonce to prevent replay attacks- 
    #the client always increases it by one, we just check that it is bigger
    if msgNum > self.previousMsgnum:
      #update the msgnum in the db to be this msgnum of course - 
      #not generally threadsafe
      sql = "UPDATE Relays SET Msgnum = %s WHERE tor_id = %s"
      inj = (msgNum, self.hexId)
      d = db.write(sql, inj)
    else:
      raise Exception('replay attack or something')
    return blob
    
  def get_sym_key_value(self, msg):
    """utility function that does a decrypt with the one time key"""
    msg = self.symKey.decrypt(msg)
    return msg
    
if __name__ == '__main__':
  reactor = main()
  
