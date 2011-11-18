#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Handles client connection and interactions with the bank
Also contains all protocols for communication with the bank."""

import os
import sys
import re
import time
import shutil
import random
import copy
import struct
from binascii import unhexlify, hexlify

from twisted.internet import defer
import M2Crypto.SSL.TwistedProtocolWrapper
from M2Crypto.SSL import Checker

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Basic
from common.classes import PublicKey
from common.classes import Scheduler
from common.system import Files
from common.system import System
from common.Errors import EarlyDepositError, BadLoginPasswordError
from common.events import GlobalEvents
from common.events import GeneratorMixin
from common.classes import SymmetricKey
from core.bank import BankMessages
from core.bank import UDPPayment
from core.bank import LoginFactory
from core.bank import ACoin
from core.bank import ACoinRequestFactory
from core.bank import ACoinDepositFactory
from core import HTTPClient
from core import ProgramState
from gui import GUIController
from Applications import Application
from Applications import SocksApp
from Applications import ApplicationSettings
from Applications import GlobalSettings
  
_instance = None
def get():
  return _instance
  
def start():
  global _instance
  if not _instance:
    _instance = BankConnection()
    
#must have at least this many credits to start sending traffic again
MIN_FUNCTIONAL_MONEY = 20L

if not ProgramState.DEBUG:
  #:  Lowest number of coins we maintain at all times- also the number we request from the bank
  ACOIN_LOW_LEVEL = 20
  #:  Highest number of coins we allow before we attempt to deposit
  ACOIN_HIGH_LEVEL = 100
  #:  the max number of ACoins to deposit at once:
  ACOIN_BATCH_SIZE = 30
  #:  max time to let pass without polling the bank for an updated balance when we have run out of credits
  BALANCE_POLL_TIMEOUT = 15.0 * 60.0
else:
  ACOIN_LOW_LEVEL = 20
  ACOIN_HIGH_LEVEL = 100
  ACOIN_BATCH_SIZE = 30
  BALANCE_POLL_TIMEOUT = 45.0
  
#TODO:  scaling stuff with nice backoffs for when a bank is done.  for now,
#a hack--this cannot be smaller, or people might request too many ACoins:
if BALANCE_POLL_TIMEOUT < BankMessages.TIMEOUT:
  BALANCE_POLL_TIMEOUT = BankMessages.TIMEOUT + 15.0

class BankConnection(SocksApp.SocksApplication):
  """Controls all client interactions with the bank.
  Also saves, loads, stores all coins from the bank.
  Schedules updates to control the amounts of coins stored locally."""
  def __init__(self):
    SocksApp.SocksApplication.__init__(self, "Bank", ApplicationSettings.ApplicationSettings, "", None, self)
    self._add_events("login_success", "login_failure")
    #: have we ever successfully logged in to the bank?
    self.isLoggedIn = False
    #: shared symmetric key for sending DEPOSIT and WITHDRAWAL messages.  Is set on login.
    self.secretKey = None
    #: the IP address of the bank.  Learned from the login server
    self.host = ""
    #: port of the bank.  Learned from the login server
    self.port = None
    #: main coin storage.  Maps from interval -> set(ACoins)
    self.ACoins = {}
    #: the number for the current interval
    self.currentACoinInterval = 0
    #: indicates that some coins have been added or removed:
    self.coinsChanged = False
    #: the event used to save the coins to disk:
    self.updateEvent = None
    #: the balance of our account at the bank:
    self.lastBankBalance = 0
    #: a queue of messages to be sent to the bank.  We only have a single connection open to the bank:
    self.messageQueue = []
    #: whether we are currently sending to the bank:
    self.messageInProgress = False
    #: the current message number.  First message will have 1:
    self.messageNum = 0
    #: whether we're already going to get more ACoins:
    self.acoinRequestInProgress = False
    #: whether we're already depositing ACoins:
    self.acoinDepositInProgress = False
    #: whether we are currently sending a login message
    self.loginInProgress = False
    #: the coins that we are currently depositing
    self.depositingACoins = []
    #: files for saving and loading coins.  Set when user logs in (need to know user name)
    self.ACOIN_FILE_NAME = None
    self.DEPOSITED_FILE_NAME = None
    #: just for so that we can display the value to the user:
    self.creditsEarned = 0
    self.creditsSpent = 0
    #: the time that we last earned some credits, or None if it hasnt happened yet
    self.lastEarnedTime = None
    #: for timing out when depositing ACoins while shutting down
    self.shutdownTimeoutEvent = None
    #:  this is set on each interval update with the length.  This value is our default for the live network
    self.APPROX_INTERVAL_LEN = 60.0 * 60.0 * 12
    #: our current credits amount state (for simplifying interactions about how many credits are left)
    self.creditStatus = "UNKNOWN"
    #: the last time that we learned about our bank balance.  Used to determine when to query the bank when we are out of credits and want to learn about more
    self.balanceLastUpdatedAt = 0
    #NOTE:  have to set here because we need to be sure that the chdir has happened
    #: mapping from ACoin value to the key used to sign those ACoins.  Only support coins of value 1 right now
    self.BANK_KEYS = {1 : PublicKey.load_public_key(fileName="common/keys/acoin.pem")}
    #: key used to encrypt payment messages.
    #NOTE:  this key is small for efficiency reasons and because it's barely necessary to encrypt this information anyway.
    self.PUBLIC_KEY = PublicKey.load_public_key(fileName="common/keys/bank.pem")
    #:  FOR TESTING ONLY:
    self._forceSetBalance = None
    
  def start(self):
    if self.isLoggedIn:
      return defer.succeed(True)
    if not self.startupDeferred:
      self.startupDeferred = defer.Deferred()
      self._trigger_event("launched")
    return self.startupDeferred
    
  def is_ready(self):
    return self.isLoggedIn
    
  def get_time_of_last_earning(self):
    return self.lastEarnedTime
    
  def login(self, username, password):
    """Launches the actual login attempt.  If username/password is None, uses the last value."""
    if self.loginInProgress:
      return
    assert username, "Must provide a valid username to log in"
    assert password, "Must provide a valid password to log in"
    self.lastUserName = username
    self.lastPassword = password
    f = LoginFactory.LoginFactory(self, self.lastUserName, self.lastPassword)
    f.forceHost = ProgramState.Conf.LOGIN_SERVER_HOST
    f.forcePort = ProgramState.Conf.LOGIN_PORT
    self.loginInProgress = True
    #TODO:  remove the stupid case below once everyone has upgraded to 0.5.8 or so?
    def stupid_checker(peerCert, host):
      #TODO:  fix the dev server as well:
      if not ProgramState.IS_LIVE:
        return True
      checker = M2Crypto.SSL.Checker.Checker()
      #stupid case because our certificate does not match.
      if host == "login.bitblinder.com":
        try:
          result = checker(peerCert, "innomi.net")
          if result == True:
            return True
        except:
          pass
      #normal case:
      return checker(peerCert, host)
    M2Crypto.SSL.TwistedProtocolWrapper.connectSSL(f.forceHost, f.forcePort, f, HTTPClient.ClientContextFactory(), reactor=Globals.reactor, postConnectionCheck=stupid_checker)
    
  def on_login_success(self, balance, authBlob, host, port, text):
    """Called when we successfully log in to the bank server, passed the response message
    @param balance:  how many credits we have at the bank
    @type  balance:  int
    @param authBlob:  the symmetric key to use for subsequent messages
    @type  authBlob:  str
    @param host:  where to send subsequent messages
    @type  host:  str (ip addr)
    @param port:  where to send subsequent messages
    @type  port:  int (port)
    @param text:  a status code and message from the bank to possibly show the user.
    @type  text:  str"""
    if not self.startupDeferred:
      return
    log_msg("login was successful: \nServer says: %s" % (text), 4)
    if text:
      #If the code is non-zero, display the text
      code, text = Basic.read_byte(text)
      if code == 0:
        text = None
    self.loginInProgress = False
    #figure out the shared symmetric key from the bank (for use encrypting all later messages)
    self.secretKey = SymmetricKey.SymmetricKey(authBlob)
    self.host = host
    self.port = port
    if not self.isLoggedIn:
      self.isLoggedIn = True
      #determine some file names based on the username:
      self.ACOIN_FILE_NAME = os.path.join(Globals.USER_DATA_DIR, "acoins.txt")
      self.DEPOSITED_FILE_NAME = os.path.join(Globals.USER_DATA_DIR, "acoins_in_deposit.txt")
      #inform the gui that we've logged in:
      self._trigger_event("login_success", text)
      #load any coins we stored when we shut down previously:
      self.load_coins()
      log_msg("Bank login successful!", 3)
      #make sure we have enough ACoins:
      self.check_wallet_balance()
      #let other parts of the program react to the fact that we just logged in
      GlobalEvents.throw_event("login")
      #notify anyone waiting on the startup deferred:
      self.startupDeferred.callback(True)
      self.startupDeferred = None
      self._trigger_event("started")
    else:
      log_ex("already logged in", "The bank should not be started more than once")
    
  def on_login_failure(self, err=None, text=None):
    """Called anytime login fails for any reason.
    @param err:  the failure
    @type  err:  Failure, Exception, or str
    @param text:  error message from the bank
    @type  text:  str"""
    if not self.startupDeferred:
      return
    log_ex(err, "Login failed", [BadLoginPasswordError])
    self.loginInProgress = False
    if not self.isLoggedIn:
      #dont automatically log in if we failed last time:
      GlobalSettings.get().save_password = False
      GlobalSettings.get().save()
      self._trigger_event("login_failure", err, text)
  
  def on_update(self):
    """Called periodically (once per second).
    Check whether we have run out of credits and if so, notifies the user and applications."""
    Application.Application.on_update(self)
    if not self.isLoggedIn:
      return
    currentBalance = self.get_expected_balance()
    #if we have no credits and it's been a while (15 minutes) since we queried the bank, do that now:
    if currentBalance <= 0 and time.time() > self.balanceLastUpdatedAt + BALANCE_POLL_TIMEOUT:
      if not self.acoinDepositInProgress:
        self.acoinDepositInProgress = True
        self.deposit_acoins(None)
        
    #TODO:  remove these from Global events
    #throw various balance related events
    if currentBalance <= 0:
      if self.creditStatus != "EMPTY":
        self.creditStatus = "EMPTY"
        GlobalEvents.throw_event("no_credits")
    elif currentBalance > MIN_FUNCTIONAL_MONEY:
      if self.creditStatus != "NORMAL":
        self.creditStatus = "NORMAL"
        GlobalEvents.throw_event("some_credits")
    else:
      self.creditStatus = "LOW"
        
    
  def encrypt_message(self, msg):
    """Encrypt a message to be sent to the bank server.
    @param msg:  the message to be encrypted
    @type  msg:  str
    @return: str, the encrypted message"""
    if not self.isLoggedIn:
      raise Exception("Must be logged in to bank to send encrypted messages!")
    #convert the fingerprint into binary
    fingerprint = unhexlify(Globals.FINGERPRINT)
    if self.secretKey:
      self.secretKey.reset()
    msg = struct.pack('!B20s', 0, fingerprint) + self.secretKey.encrypt(msg)
    return msg
  
  def decrypt_message(self, msg):
    """Decrypt a message to be sent to the bank server.
    @param msg:  the message to be derypted
    @type  msg:  str
    @return: str, the decrypted message"""
    if not self.isLoggedIn:
      raise Exception("Must be logged in to decrypt messages from the bank!")
    if self.secretKey:
      self.secretKey.reset()
    return self.secretKey.decrypt(msg)
       
  def send_message(self, f):
    """Use this to send any message to the bank.  We serialize messages to the bank
    so that users dont send lots of requests at once.
    @param f: the twisted Factory for the message to be sent"""
    #if we're not currently talking to the bank
    if not self.messageInProgress:
      #then go ahead and send the message
      self.messageInProgress = True
      self.send_next_message(f)
    #otherwise, add it to the queue
    else:
      log_msg("Adding %s to the queue..." % (f), 4)
      self.messageQueue.append(f)
      
  def send_next_message(self, f):
    """Actually connect the next factory from the queue
    @param f: the factory to be connected"""
    self.messageNum += 1
    host = self.host
    port = self.port
    if hasattr(f, "forceHost"):
      host = f.forceHost
    if hasattr(f, "forcePort"):
      port = f.forcePort
    log_msg("Sending %s to the bank at %s:%s" % (f, host, port), 4)
    Globals.reactor.connectTCP(host, port, f)
   
  def on_bank_message_done(self):
    """Called when any bank message finishes, whether it was successful or not.
    Here we just launch the next message in the queue if there is one."""
    try:
      #try sending the next message:
      f = self.messageQueue.pop(0)
    #if there are no more messages to send, fine
    except IndexError:
      log_msg("Done sending messages to the bank!", 4)
      self.messageInProgress = False
    else:
      self.send_next_message(f)
   
  def on_new_balance_from_bank(self, newBalance):
    """Called any time we learn a new bank balance from some message.
    Checks if we maybe want to get more coins now.
    @param newBalance:  the new balance
    @type  newBalance:  int"""
    #TODO:  disassociate testing code with real code.  Put it in a subclass or testing harness instead
    #to test interactions when we run out of credits
    if ProgramState.DEBUG and ProgramState.USE_GTK and GUIController.get() and GUIController.get().socksClientWindow.bankDisplay:
      bankDisplay = GUIController.get().socksClientWindow.bankDisplay
      if bankDisplay.entry.get_text():
        newBalance = int(bankDisplay.entry.get_text())
    if ProgramState.DEBUG and self._forceSetBalance != None:
      newBalance = self._forceSetBalance

    self.lastBankBalance = long(newBalance)
    self.balanceLastUpdatedAt = time.time()
    self.check_wallet_balance()
    
  def get_acoin_key(self, value):
    """Decide what value the A-Coin should have (what public key to use from the bank)
    @raises:  Exceptions if there is no bank key for value
    @param value: the value for which we want a matching acoin public key
    @type  value: int
    @return:  the key"""
    if not value:
      raise Exception("ACoin has no value set, cannot determine bank key")
    if not self.BANK_KEYS.has_key(value):
      raise Exception("No bank key is known to generate an ACoin with a value of %s" % (str(value)))
    return self.BANK_KEYS[value]
    
  def get_wallet_balance(self):
    """@return: the value of all ACoins."""
    balance = 0
    for interval, coins in self.ACoins.iteritems():
      if interval in (self.currentACoinInterval, self.currentACoinInterval-1):
        balance += ACoin.ACoinParent.VALUE * len(self.ACoins[interval])
    return balance  
    
  def check_wallet_balance(self):
    """Should be called whenever we use any ACoins.  If we dont have very many
    ACoins, get some from the bank (necessary for relaying traffic for others or ourselves)"""
    #no need to check wallet balance if we haven't even logged in yet (since we might load some old coins while logging in)
    if not self.isLoggedIn:
      return
    #should this instead just return the number of acoins we have?
    balance = self.get_wallet_balance()
    if balance < ACOIN_LOW_LEVEL:
      self.request_coins(1, ACOIN_BATCH_SIZE)
    
  def get_total_asset_value(self):
    assets = self.get_wallet_balance() + self.lastBankBalance
    return assets
  
  def request_coins(self, value=1, number=1):
    """request (number) new coins of a given (value)"""
    if self.is_stopping():
      return
    if self.acoinRequestInProgress:
      return
    while value*number > self.lastBankBalance:
      number -= 1
    if number <= 0:
      return
    self.acoinRequestInProgress = True
    self.send_message(ACoinRequestFactory.ACoinRequestFactory(self, value, number))
  
  def deposit_acoins(self, coins):
    """Send a deposit message to the bank with coins to be deposited.  Occasionally gets called with no coins just to learn about new intervals
    @param coins:  the coins to be deposited
    @type  coins:  list, or None"""
    if self.is_stopping():
      return
    if coins:
      for coin in coins:
        if coin not in self.depositingACoins:
          self.depositingACoins.append(coin)
    try:
      self.send_message(ACoinDepositFactory.ACoinDepositFactory(self, coins))
    except Exception, e:
      log_ex(e, "Failed to create ACoin deposit message")
  
  def on_earned_coin(self, coin):
    """Deal with a newly received acoin.
    @param coin:  the coin you just earned.  Congratulations!
    @type  coin:  ACoin"""
    if not coin:
      raise Exception("Cannot deposit None...")
    coin.validate(self.currentACoinInterval)
    #add to our list of coins
    self.add_acoin(coin)
    log_msg("Earned ACoin!", 4, "bank")
    self.lastEarnedTime = time.time()
    self.creditsEarned += coin.get_deposit_value()
    
  def on_new_info(self, balance, interval, expiresCurrent, expiresNext):
    """Called when we learn about new ACoin interval information
    @param balance:  new bank balance
    @type  balance:  int
    @param interval:  current ACoin interval
    @type  interval:  int
    @param expiresCurrent:  how many seconds until this interval expires
    @type  expiresCurrent:  int
    @param expiresNext:  how many seconds until the next interval also expires
    @type  expiresNext:  int"""
    #if we just learned about a new interval:
    if interval > self.currentACoinInterval:
      curTime = time.time()
      expiresCurrent += curTime
      expiresNext += curTime
      log_msg("Learned about new interval:  %s" % (interval), 4)
      #make sure we dont have any expiring ACoins:
      if self.ACoins.has_key(self.currentACoinInterval-1):
        del self.ACoins[self.currentACoinInterval-1]
      self.currentACoinInterval = interval
      self.curIntervalExpiration = expiresCurrent
      self.nextAcoinIntervalExpiration = expiresNext
      self.APPROX_INTERVAL_LEN = expiresNext - expiresCurrent
      self.beginDepositACoinTime = expiresCurrent - (0.1*self.APPROX_INTERVAL_LEN)
      self.beginDepositACoinTime -= random.random() * (0.3*self.APPROX_INTERVAL_LEN)
      self.sendOldACoinCutoff = expiresCurrent - (0.1*self.APPROX_INTERVAL_LEN)
      needNewACoinTime = self.sendOldACoinCutoff - (random.random()*0.1*self.APPROX_INTERVAL_LEN) - curTime
      if needNewACoinTime > 0:
        Scheduler.schedule_once(needNewACoinTime, self.check_next_acoins)
      self.intervalLearningDelay = random.random() * (0.25*self.APPROX_INTERVAL_LEN)
      log_msg("\nACoin send cutoff:  %s\nACoin accept cutoff:  %s\nCur interval ends at: %s\nLearning about next interval at:  %s" \
              % tuple([time.asctime(time.gmtime(t)) for t in (self.sendOldACoinCutoff, self.beginDepositACoinTime, expiresCurrent, expiresCurrent+self.intervalLearningDelay)]), 4)
    self.on_new_balance_from_bank(balance)
    
  #TODO:  try again with this function until it succeeds?
  def check_next_acoins(self):
    """Checks if we should go get some acoins for the current interval, in case we've just been using old ones so far
    Called right before we switch over to ONLY using acoins from this interval"""
    if not self.ACoins.has_key(self.currentACoinInterval) or len(self.ACoins[self.currentACoinInterval]) <= 0:
      self.request_coins(1, ACOIN_BATCH_SIZE)
        
  def get_earnings(self):
    """@return:  amount of credits earned since the program was started"""
    return self.creditsEarned
  
  def get_spendings(self):
    """@return:  amount of credits spent since the program was started"""
    return self.creditsSpent
    
  def get_current_bank_balance(self):
    """@return: the last bank balance that we heard about"""
    return self.lastBankBalance
    
  def get_expected_balance(self):
    """@return: the bank balance + local credits.  Note that this will be
    off in the case of a user running multiple clients on the same account."""
    return self.lastBankBalance + self.get_wallet_balance()
    
  def add_acoin(self, coin):
    """Called whenever an ACoin should be added to our local collection (for use by us later).
    This function does no validation of acoins.
    @param coin:  the coin to store
    @type  coin:  ACoin"""
    if not self.ACoins.has_key(coin.interval):
      self.ACoins[coin.interval] = set()
    if coin not in self.ACoins[coin.interval]:
      self.ACoins[coin.interval].add(coin)
      self.coinsChanged = True
    else:
      raise Exception("This ACoin has already been deposited to the local store!  %s" % (coin))
  
  def remove_coin(self, coin):
    """Called to remove an ACoin from our local collection when we want to use it.  Not always used.
    @param coin:  the coin to remove
    @type  coin:  ACoin
    @return:  True if the coin existed, False otherwise"""
    if not self.ACoins.has_key(coin.interval):
      return False
    if coin not in self.ACoins[coin.interval]:
      return False
    self.ACoins[coin.interval].remove(coin)
    self.coinsChanged = True
    return True
    
  def get_acoins(self, value, countAsSpent=True):
    """Returns coins that add up to make value, favoring coins that are about to expire
    @param value:  how many credits to take out
    @type  value:  int
    @param countAsSpent:  whether we are spending this ACoin or using it for something else
    @type  countAsSpent:  bool
    @return:  list(ACoins)
    @raises:  Exceptions if not enough acoins, invalid value"""
    if type(value) is not int:
      raise Exception("ACoin values must be integers!")
    keys = self.ACoins.keys()
    keys.sort()
    coins = []
    coinsValue = 0
    curTime = time.time()
    #get coins starting with the oldest intervals
    for key in keys:
      if key < self.currentACoinInterval:
        if key < self.currentACoinInterval-1:
          assert len(self.ACoins[key]) == 0, "acoins from bad interval still exist"
        if curTime > self.sendOldACoinCutoff:
          continue
      for coin in self.ACoins[key]:
        coins.append(coin)
        coinsValue += ACoin.ACoinParent.VALUE
        if coinsValue >= value:
          break
      if coinsValue >= value:
        break
    #make sure we had enough coins to fulfill the request
    if coinsValue < value:
      log_msg("Insufficient ACoins to pay %s (only have %s)" % (value, coinsValue), 4)
      return []
    #remove these coins from our list.  They will never be used for anything else.
    for coin in coins:
      self.remove_coin(coin)
    #make sure we have enough ACoins:
    self.check_wallet_balance()
    if countAsSpent:
      self.creditsSpent += value
    return coins
    
  def update_coins(self):
    """Check that we have enough ACoins locally, but not too many, and none that are about to expire"""
    try:
      self.check_wallet_balance()
      #should we consider sending a deposit message?
      if not self.acoinDepositInProgress:
        coins = []
        curTime = time.time()
        #we must retry depositing any existing coins that are in progress:
        if len(self.depositingACoins) > 0:
          coins += self.depositingACoins
        #are any stale?
        if curTime > self.beginDepositACoinTime:
          if self.ACoins.has_key(self.currentACoinInterval-1) and len(self.ACoins[self.currentACoinInterval-1]):
            newCoins = []
            for coin in self.ACoins[self.currentACoinInterval-1]:
              newCoins.append(coin)
              if len(newCoins) >= ACOIN_BATCH_SIZE:
                break
            for coin in newCoins:
              self.remove_coin(coin)
            coins += list(newCoins)
            if len(coins) > 0:
              #make sure we have enough coins:
              self.check_wallet_balance()
        #do we have too many?
        numCoins = (self.get_wallet_balance() - ACOIN_HIGH_LEVEL)
        if numCoins > 0:
          coins += self.get_acoins(ACOIN_BATCH_SIZE, False)
        #if we have coins to deposit, or we need to learn about the next interval
        if coins or curTime > self.curIntervalExpiration + self.intervalLearningDelay:
          self.acoinDepositInProgress = True
          self.deposit_acoins(coins)
    except Exception, e:
      log_ex(e, "Too many ACoins, but failed when trying to send to the bank")
    return self.save_coins()
    
  def load_coins(self):
    """Call this function once at the beginning of the program to read in any
    existing coins from the respective files."""
    try:
      def read(unicodeFileName, addFunc):
        fileName = System.encode_for_filesystem(unicodeFileName)
        if not Files.file_exists(fileName):
          log_msg("Could not load coins, file=%s does not exist." % (fileName), 1)
          return
        #TODO:  properly deal with various filesystem errors--permissions, etc  :-/
        #read in the original file:
        f = open(fileName, "rb")
        data = f.read()
        while len(data) > 0:
          acoin = ACoin.ACoin(self)
          data = acoin.read_binary(data)
          if acoin.is_fresh(self.currentACoinInterval):
            addFunc(acoin)
          else:
            log_msg("Dropped an expired acoin from %s interval because we are at %s." % \
                    (acoin.interval,self.currentACoinInterval), 1)
          f.close()
      assert not self.ACoins, "must not load coins more than once?"
      read(self.ACOIN_FILE_NAME, self.add_acoin)
      assert not self.depositingACoins, "cannot deposit coins while loading?"
      read(self.DEPOSITED_FILE_NAME, self.depositingACoins.append)
    except Exception, e:
      log_ex(e, "Failed to load coins from disk")
    #schedule the event to save the coins, now that they are loaded
    #TODO:  make this save way less often, this is just for debugging
    self.updateEvent = Scheduler.schedule_repeat(10, self.update_coins)
      
  def save_coins(self):
    """This function is called periodically.  It checks if any coins have been
    added or removed from our collections, and if so, stores them back to disk."""
    #if there have been any changes to our coins recently:
    if self.coinsChanged:
      #TODO:  properly deal with various filesystem errors--permissions, etc  :-/
      try:
        def write(unicodeFileName, coins):
          fileName = System.encode_for_filesystem(unicodeFileName)
          #do not overwrite existing until we're sure the whole file has been output
          newFileName = fileName+".new"
          f = open(newFileName, "wb")
          msg = ""
          for coin in coins:
            msg += coin.write_binary()
          #TODO:  these should probably be stored encrypted?  use username and password to generate an AES key for the file
          #TODO:  should there actually be a different key?  What about if there are multiple users?
          f.write(msg)
          f.close()
          #move the file to the real location:
          shutil.move(newFileName, fileName)
        coins = []
        for interval in self.ACoins:
          if interval < self.currentACoinInterval-1 and len(self.ACoins[interval]):
            log_ex("Ignoring %s ACoins because they are too old.  They should have been deposited before this!" % (len(self.ACoins[interval])), "Problem saving ACoins")
          else:
            coins += list(self.ACoins[interval])
        if self.ACOIN_FILE_NAME:
          startTime = time.time()
          write(self.ACOIN_FILE_NAME, coins)
          #save ACoins that are in the process of being deposited until we get confirmation that they have failed or succeeded
          write(self.DEPOSITED_FILE_NAME, self.depositingACoins)
          log_msg("Took %s seconds to save %s ACoins to disk" % (time.time()-startTime, len(coins)+len(self.depositingACoins)), 3)
        self.coinsChanged = False
      except Exception, e:
        log_ex(e, "Failed to save coins to disk")
    return True
    
  def make_bank_prefix(self, protocolVersion, request):
    """Called to make some communication with the bank
    @param protocolVersion:  what version of the message protocol to send to the bank
    @type  protocolVersion:  int
    @param request:  type of message to send to the bank
    @type  request:  str
    @returns:  str (packed message header)"""
    if request=='acoin request':
      request = 1
    elif request=='acoin deposit':
      request = 2
    return struct.pack("!BHB", protocolVersion, self.messageNum, request)
    
  def _shutdown_timeout(self):
    self.shutdownDeferred.errback(Exception("Timed out"))
    self._shutdown_done()
    
  def _shutdown_success(self, result):
    self.coinsChanged = True
    self.save_coins()
    self.shutdownDeferred.callback(True)
    self._shutdown_done()
    
  def _shutdown_failure(self, reason):
    log_ex(reason, "Failed while depositing ACoins during shutdown")
    newD = defer.Deferred()
    self.send_message(ACoinDepositFactory.ACoinDepositFactory(self, coinsToDeposit, newD))
    return newD
    
  def _shutdown_done(self):
    if self.shutdownTimeoutEvent and self.shutdownTimeoutEvent.active():
      self.shutdownTimeoutEvent.cancel()
    self.shutdownTimeoutEvent = None
    self.shutdownDeferred = None
    self.isLoggedIn = False
    self._trigger_event("finished")
    
  #TODO:  think about shutdown process some.  Takes a while for Tor to shutdown, and payments to finish.  Maybe do them simultaneously UNLESS we are tunneling all communications?
  def stop(self, timeout=10.0):
    """Dump all ACoins immediately.
    @param timeout: how long to wait while depositing ACoins
    @returns: a Deferred to be triggered when done or if the attempt timed out."""
    if self.shutdownDeferred:
      return self.shutdownDeferred
    #cancel any bank messages in progress
    self.messageQueue = []
    #since we wont be able to send the deposit anyway...
    if not self.isLoggedIn:
      if self.is_starting():
        #notify anyone waiting on the startup deferred:
        self.loginInProgress = False
        d = self.startupDeferred
        self.startupDeferred = None
        d.callback(False)
      return defer.succeed(True)
    #create the deferred
    self.shutdownDeferred = defer.Deferred()
    #schedule the timeout
    self.shutdownTimeoutEvent = Scheduler.schedule_once(timeout, self._shutdown_timeout)
    #move all ACoins over to be in deposit progress
    coinsToDeposit = []
    for key, coins in self.ACoins.iteritems():
      coinsToDeposit += coins
    self.ACoins = {}
    self.depositingACoins += coinsToDeposit
    if not self.acoinDepositInProgress:
      coinsToDeposit = self.depositingACoins
    #save ACoins
    self.coinsChanged = True
    self.save_coins()
    #send the message to the bank
    bankD = defer.Deferred()
    self.send_message(ACoinDepositFactory.ACoinDepositFactory(self, coinsToDeposit, bankD))
    #on success, trigger the deferred
    bankD.addCallback(self._shutdown_success)
    #deal with failure by trying again
    bankD.addErrback(self._shutdown_failure)
    self._trigger_event("stopped")
    return self.shutdownDeferred
    
