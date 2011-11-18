#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""PAR Banking Login Server via Twisted, OpenSSL, and with cyborg run PostgreSQL backend"""

import signal
import getpass
import struct
import sys
import time
import os
from socket import inet_aton

import psycopg2 as cyborg
from OpenSSL import SSL
from pyasn1.codec.ber import encoder
from pyasn1.type import univ
from twisted.internet import reactor, defer, protocol, ssl, address
from twisted.protocols.basic import Int16StringReceiver

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.system import Files
from common.utils import Basic
from common.utils import TorUtils
from common.classes import Logger
from common.classes import SymmetricKey
from common.classes import PublicKey
from serverCommon.DBUtil import format_auth
from serverCommon import db
from serverCommon.Events import BankLogin
from serverCommon import EventLogging
import BankUtil
import AccountCreation
EventLogging.open_logs("/mnt/logs/bank/login_events.out")

cert = '/etc/apache2/ssl/server.crt'
privateKey = '/etc/apache2/ssl/server.key'

if os.path.exists("THIS_IS_KANS_MACHINE"):
  from common.conf import Dev as Conf
  bank1Address = address.IPv4Address('TCP', '24.131.16.34', 10001) #
  Conf.LOGIN_PORT = 1092
elif os.path.exists("THIS_IS_DEBUG"):
  from common.conf import Dev as Conf
  bank1Address = address.IPv4Address('TCP', Conf.DEV_SERVER, Conf.SERVER_PORT) #innomi.net
  cert = '/home/certificate_authority/server.crt'
else:
  from common.conf import Live as Conf
  bank1Address = address.IPv4Address('TCP', '174.129.199.15', Conf.SERVER_PORT) #login.bitblinder.com

#start up our logs
Globals.logger = Logger.Logger()
Globals.logger.start_logs(["login", "login_errors"], "login", ".")
Globals.logger.ERROR_LOG_NAME = "login_errors"

Globals.CURRENT_ACOIN_INTERVAL = [0,0]
#is the reactor listening?
Globals.isListening = False

addressBook = [bank1Address]

def main():
  """Entrance"""
  global crtPassword
  crtPassword = getpass.getpass('enter private key password: ')
  signal.signal(signal.SIGHUP, signal.SIG_IGN) #ignore sighup
  log_msg('Login Reactor Started- Fail is near!', 2)
  BankUtil.update_local_acoin_interval(start_listening)
  Globals.reactor = reactor
  reactor.run()
  
def start_listening():
  """called when we learn the current acoin interval"""
  factory = protocol.ServerFactory()
  factory.protocol = Server
  log_msg('Login server is listening on port: %s.'%(Conf.LOGIN_PORT), 2)
  log_msg('Sending clients to address: %s.'%(bank1Address), 2)
  reactor.listenSSL(Conf.LOGIN_PORT, factory, ServerContextFactory())
  
class Server(Int16StringReceiver):
  def stringReceived(self, data):
    self.successful = True
    #we don't have any errbacks attached yet- an error will just make the client hang indefinately
    try:
      protocol, blob = Basic.read_byte(data)
      if protocol == 1:
        self.hexIdSig, self.username, self.password, self.n = self.unpack(blob)
        d = self.check_for_timeout()
        d.addCallback(self.login_timeout_known)
        d.addErrback(self.err)
      elif protocol == 2:
        ipAddress = self.transport.getPeer().host
        self.currentAction = AccountCreation.AccountCreation(blob, ipAddress, db, self.reply)
      else:
        raise Exception('unknown login protocol: %s' % (protocol))
    except Exception, e:
      self.err(e)
    
  def unpack(self, blob):
    """expects to get a struct of the form
    20s hexId
    50s username
    50s password
    128s publickey
    """
    msg = struct.unpack('!128s50s50s128s', blob)
    hexIdSig = msg[0]
    #strip out the null padding characters
    username = msg[1].replace('\x00', '')
    password = msg[2].replace('\x00', '')
    n = long(Basic.bytes_to_long(msg[3]))
    log_msg('attempting to login user: %s @ time: %s!' % (username, time.ctime()), 2)
    return (hexIdSig, username, password, n)
  
  def check_for_timeout(self):
    """if there is a timeout, raises an exception to trigger the bad_info errback
    sets: self.timeout
    """        
    #check to see if the account has a login timeout on it
    sql = "SELECT timeout, escalation FROM badlogin WHERE username = %s AND active = true"
    inj = (self.username,)
    return db.read(sql, inj)
    
  def login_timeout_known(self, results):
    """branches depending on if a timeout on the username exists or not"""
    if results:
      self.timeout, escalation = results[0]
      if int(self.timeout) > int(time.time()):
        self.generate_timeout('Existing timeout- user isn\'t allowed to login yet.')
      else:
        self.get_password_from_db()
    else:
      self.timeout = None
      self.get_password_from_db()
        
  def get_password_from_db(self):
    """gets the password form the db which is also an implicit check to see if the account exists"""
    #check to see if the account exists
    d = db.read("SELECT password, balance FROM Accounts WHERE Username = %s",(self.username,))
    d.addCallback(self.does_account_exist_and_do_passwords_match)
    d.addErrback(self.err)

  def does_account_exist_and_do_passwords_match(self, tup):
    if tup:
      db_pw, balance  = tup[0]
      #next, do the passwords match?
      h = format_auth(self.username, self.password)
      if str(db_pw) != h:
        self.generate_timeout('Account exists, but the passwords don\'t match.')
      else:
        self.balance = balance
        self.does_relay_belong_to_account()
    else:
      #ie no username by that name exists, but we still may need to put a timeout on it 
      self.generate_timeout('Account does not exist.')
  
  def does_relay_belong_to_account(self):
    """can we verify the signature on the hexid?
    basically, can we prove that the relay and no one else owns that hexid
    a hexid is derived from the relays public key, so they should be able to sign their id proving ownership
    sets: self.hexId
    @return: None"""
    thumb = TorUtils.fingerprint(self.n)
    key = PublicKey.PublicKey(self.n, 65537L)
    if not key.verify(thumb, self.hexIdSig):
      raise Exception("fingerprint doesn't match")
    self.hexId = thumb
    self.update_db()
  
  def update_db(self):
    """a convenience function
    each callback returns a different deferred"""
    d = self.update_db1()
    d.addCallback(self.update_db2)
    d.addCallback(self.update_db3)
    d.addCallback(self.generate_reply)
    d.addErrback(self.err)
    
  def update_db1(self):
    """if there was a timeout for this account, get rid of it since a valid username/pw has been supplied"""
    if self.timeout:
      sql = "UPDATE badlogin SET active = false WHERE Username = %s AND active = true"
      inj = (self.username,)
      return db.write(sql, inj)
    else:
      return defer.succeed(None)
      
  def update_db2(self, returned=None):
    """generate session auth stuff and also see if the relay is known to exist"""
    symKey = SymmetricKey.SymmetricKey()
    self.authBlob = symKey.pack()
    d = db.read("SELECT Owner, Public_Key FROM Relays WHERE Tor_Id = %s",(self.hexId,))
    return d
      
  def update_db3(self, tup=None):
    """writes the relays info into the db
    @return: deferred of db write (None)"""
    #does the relay exist?
    if not tup: 
      #no entry yet-  need to insert row
      sql = "INSERT INTO Relays (Tor_ID, Owner, Public_Key, auth_blob, Msgnum) VALUES (%s, %s, %s, %s, %s)"
      inj = (self.hexId, self.username, self.n, cyborg.Binary(self.authBlob), 0)
      d = db.write(sql, inj)
    else:
      #entry exists, need update row; 
      #note, the public key is tied to the hexId, so it should be imposible for one to change without the other
      sql = "UPDATE Relays SET auth_blob=%s, Msgnum = %s WHERE Tor_ID = %s"
      inj = (cyborg.Binary(self.authBlob), 0, self.hexId)
      d = db.write(sql, inj)
    return d
    
  def generate_reply(self, returned=None, optional=None):
    """This function is a bit crazy as it is entered from several points as both a callback or called directly :(
    returns either the successful msg, containing the symmertric key, balance, bank ip address, and login token
    OR
    the timeout until the client can log in again
    @param optional: text to return to the client with a code
    @type optional: [int, str]
    @return: None"""
    PROTOCOL = 1
    if self.successful:
      log_msg('Login was successful.', 3)
      EventLogging.save_event(BankLogin(username=self.username))
      #address of the bank server
      address = addressBook[0]
      curExp, nextExp = BankUtil.get_interval_time_deltas()
      format = '!BBIIII4sI'
      reply = struct.pack(format, PROTOCOL, 1, self.balance, Globals.CURRENT_ACOIN_INTERVAL[0], \
                                  curExp, nextExp, 
                                  inet_aton(address.host), address.port)
      reply += self.authBlob
    else:
      reply = struct.pack('!BBI', PROTOCOL, 0, self.timeout)
    #currently, 1 will replace the txt for a failure displayed client side, while 1 adds to it- thats all for now
    optional = [0, 'hello']
    if optional:
      code = struct.pack('!B', optional[0])
      reply += code + optional[1]
    #shove off the reply  
    self.reply(reply)
      
  def generate_timeout(self, reason=None):
    """
    Called by an unsuccessful login attempt-  either by an incorrect username/pw or if the user is locked out 
    because of a previous attempt.  In the case of the former- log the attempt into the db.
    sets: self.timeout
    @return: deferred
    """
    self.successful = False
    #will trap either err or reraise anything else preserving the traceback
    if self.timeout:
      log_msg('User login disallowed: currently locked out!', 1)
      self.generate_reply()
      return
    
    log_msg('User login failed- %s!'%(reason), 1)
    #see if this is the first successive active error
    sql = "SELECT escalation, timeout FROM badlogin WHERE username = %s AND active = true" 
    inj = (self.username,)
    d = db.read(sql, inj)    
    d.addCallback(self.flush_timeout_to_db)
    d.addCallback(self.generate_reply)
    d.addErrback(self.err)
    
  def flush_timeout_to_db(self, tup):
    """called to write the timeout on the account to the db to make sure the user
    can't login in again too soon"""
    currentTime =  int(time.time())
    if not tup:
      #since the entry dosn't exist, we need to make it
      sql = "INSERT INTO badlogin (escalation, timeout, username, ip, active) VALUES (%s, %s, %s, %s, true)"
      timeout = currentTime
      inj = (0, timeout, self.username, self.transport.getPeer().host)
    else:
      #update the existing entry
      escalation, timeout = tup[0]
      #escalate, and find the appropriate timeout
      escalation= int(escalation) + 1 
      if escalation < 2:
        timeout = currentTime
      elif escalation <= 24:
        timeout = currentTime + 2**escalation
      else:
        timeout = currentTime +  31536000 #one year
      #since we are past the timeout threshold and the login failed again, we need to update the db entry
      sql = "UPDATE badlogin SET escalation = %s, timeout = %s WHERE username=%s AND active = true"
      inj = (escalation, timeout, username)
    self.timeout = timeout
    d = db.write(sql, inj)
    return d
      
  def reply(self, msg):
    self.sendString(msg)
    self.transport.loseConnection()
    
  def err(self, err, optional=None):
    """returns an error msg"""
    log_ex(err, "Unhandled error from %s" % (self.transport.getPeer()))
    #DEBUG:  NOTE:  this is a security vulnerability otherwise
    if optional:
      rep = "%s\nerr: %s"%(optional, err)
    else:
      rep = "Error with login!"
    self.reply(rep)
      
class ServerContextFactory:
  """Create an SSL context for twisted"""
  def getContext(self):
    """does stuff!"""
    def password_cb(maxLength, promptTwice, data=None):
      """called when the context object requests a password"""
      return crtPassword
      
    ctx = SSL.Context(SSL.SSLv3_METHOD) #SSLv3 = 2!
    ctx.set_passwd_cb(password_cb)
    ctx.use_certificate_file(cert)
    ctx.use_privatekey_file(privateKey)
    return ctx

if __name__ == "__main__":
  main()
