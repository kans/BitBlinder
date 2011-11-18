#!/usr/bin/python
# Copyright 2009 Innominet
"""PAR Banking Server- validates acoins and creates ecoin accounts out of them"""
from __future__ import with_statement

import struct
import time

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Basic
from common.classes import ACoin
from serverCommon.Events import BankPayment, BankRequest, BankDeposit
from serverCommon import db
import BankUtil
from BankEvents import BankEventLogger

ACOIN_VALUE = 1

#: used to log events:
eventLogger = BankEventLogger({"PAYMENTS":  BankPayment,
                               "REQUESTS":  BankRequest,
                               "DEPOSITS":  BankDeposit},
                               "/mnt/logs/bank/bank_events.out")

def get_correct_set(s):
  """converts a char to a number between 0 and Globals.numberOfSets (typically 8)"""
  return struct.unpack('B', s)[0]%Globals.numberOfSets

def deposit_acoin(blob, currentInterval):
  coin = BankACoin()
  blob = coin.read_binary(blob)
  #did the bank sign it and is the interval ok?
  if not coin.is_valid(currentInterval):
    return '1', coin, blob
  #has the coin already been deposited?
  store = coin.store()
  #the coin goes in a specific set based on the leading entry of the hash 
  set = get_correct_set(store[0])
  #the dict has a key for this interval
  if not store in Globals.Acoins[coin.interval][set]:
    Globals.Acoins[coin.interval][set].add(store)
  else:
    return '2', coin, blob
  #the acoin was good!
  return '0', coin, blob
  
class Request():
  """this class mints acoins- ie we stamp them with our signature!"""
  def __init__(self, encrypted_reply, user, hexId):
    #;owner of the account
    self.user = user 
    #: hexid of the relay making the request
    self.hexId = hexId 
    #: the function to send an encrypted message to the client
    self.encrypted_reply = encrypted_reply
      
  def on_message(self, msg):
    log_msg('ACoin signing request received',  3)
    d = self.unpack_and_mint(msg)
    d.addCallback(self.update_account)
      
  def unpack_and_mint(self, msg):
    """unpacks the request retreiving the number of coins packed and the total value desired.
    Verification: values must be positive!
    """
    self.number, msg = Basic.read_short(msg)
    value, msg = Basic.read_int(msg)
    log_msg('REQUEST:: %s %s'%(self.number, self.hexId), 0)
    if not BankUtil.is_positive_integer(self.number):
      raise ValueError('number of coins must be greater than 0!')
    if value != ACOIN_VALUE or not BankUtil.is_positive_integer(value):
      raise ValueError('coins must have a positive, integer value')
      
    self.bill = 0
    self.signatures = ""
    for i in range(0, self.number):
      #TODO: move to a worker pool or something
      sig = Globals.ACOIN_KEY.decrypt(msg[:Globals.ACOIN_KEY_BYTES], False)
      self.signatures += struct.pack('!%ss'%(Globals.ACOIN_KEY_BYTES), sig)
      msg = msg[Globals.ACOIN_KEY_BYTES:]
      self.bill += value
      
    #TODO: move this constraint to postgres to get rid of any potential race conditions
    sql = "SELECT balance FROM Accounts WHERE Username = %s"
    inj = (self.user,)
    d = db.read(sql, inj)
    return d
    
  def update_account(self, tup):
    """checks to see if the user has enough money to pay for the acoin signature, 
    though this should be a db constraint-
    attempts to deduct the value from the user's account"""
    assert len(tup) == 1
    balance = int(tup[0][0])
    proposedBalance = balance - self.bill 
    if proposedBalance >= 0:
      sql = "UPDATE Accounts SET Balance = %s WHERE Username = %s"
      inj = (proposedBalance, self.user)
      d = db.write(sql, inj)
      d.addCallback(self.send_reply, True, proposedBalance, balance)
      return
    else:
      self.send_reply(None, False, proposedBalance, balance)
      
  def send_reply(self, result, success, proposedBalance, balance):
    """creates response for the clients"""
    if success:
      log_msg("%s's account now has %s money" % (self.user, proposedBalance),  4)
      reply = struct.pack('!BII', 0, proposedBalance, self.number) + self.signatures
    else:
      log_msg("%s's account did not have enough money: %s" % (self.user, proposedBalance),  4)
      reply = struct.pack('!BI', 1, balance)
    self.encrypted_reply(reply)
    #log the event:
    eventLogger.aggregate_event("REQUESTS", self.user, balance-proposedBalance)
    
class Payment():
  def __init__(self, send_func, address):
    #: the protocol to use for communication
    self.send_func = send_func
    #:
    self.address = address
    
  def on_message(self, msg):
    log_msg('PAYMENT', 0)
    current = Globals.CURRENT_ACOIN_INTERVAL[0]
    #read the number of payments:
    numPayments, msg = Basic.read_byte(msg)
    reply = ""
    for i in range(0, numPayments):
      #read the payment:
      result, coin, msg = deposit_acoin(msg, current)
      reply += struct.pack('!s', result)
      token, msg = msg[:Globals.ACOIN_KEY_BYTES], msg[Globals.ACOIN_KEY_BYTES:]
      #if the coin is valid...
      if result == '0':
        sig = Globals.ACOIN_KEY.decrypt(token, False)
        #~ print "token:  " + repr(token)
        #~ print "sig:  " + repr(sig)
        reply += struct.pack('!%ss' % (Globals.ACOIN_KEY_BYTES), sig)
    #and finally, send it back to the client:
    self.send_func(reply)
    #log the event:
    eventLogger.aggregate_event("PAYMENTS", self.address[0], 1)
    
class Deposit():
  """accepts deposits for acoins to add value to the user's account"""
  def __init__(self, encrypted_reply, user, hexId):
    #;owner of the account
    self.user = user 
    #: hexid of the relay making the request
    self.hexId = hexId 
    #: the function to send an encrypted message to the client
    self.encrypted_reply = encrypted_reply
    #: how much was earned during this deposit
    self.amountEarned = 0
  
  def on_message(self, msg):
    log_msg('ACoin deposit request received',  3)
    total = self.unpack_and_verify(msg)
    self.update_account(total)

  def unpack_and_verify(self, blob):
    """verifies that...
    1. the coin is valid
    2. isn't expired
    3. hasn't been deposited before
    returns one of 4 statements"""
    self.number, blob = Basic.read_short(blob)
    log_msg('DEPOSIT:: %s %s'%(self.number, self.hexId), 0)
    total = 0
    self.returnSlip = ""
    if BankUtil.is_positive_integer(self.number):
      #we don't want the interval to roll over half way through a request
      current = Globals.CURRENT_ACOIN_INTERVAL[0]
      for i in range(self.number):
        result, coin, blob = deposit_acoin(blob, current)
        self.returnSlip += result
        if result == '0':
          total += ACoin.VALUE
    self.amountEarned = total
    return total
  
  def update_account(self, credit):
    """adds any money to the user's account"""
    if credit > 0:
      sql = "UPDATE Accounts SET Balance = Balance + %s WHERE Username = %s"
      inj = (credit, self.user)
      d = db.write(sql, inj)
      d.addCallback(self.get_balance)
      d.addCallback(self.reply)
    else:
      d = self.get_balance(None)
      d.addCallback(self.reply)
    
  def get_balance(self, result):  
    sql = "SELECT Balance FROM Accounts WHERE Username = %s"
    inj = (self.user,)
    d = db.read(sql, inj)
    return d
    
  def reply(self, msg):
    balance = msg[0][0]
    curExp, nextExp = BankUtil.get_interval_time_deltas()
    reply = struct.pack('!IIII%ss'%(self.number), balance, Globals.CURRENT_ACOIN_INTERVAL[0],
                        curExp, nextExp,
                        self.returnSlip)
    self.encrypted_reply(reply)
    #log the event if anything was actually deposited:
    if self.amountEarned:
      eventLogger.aggregate_event("DEPOSITS", self.user, self.amountEarned)
    
class BankACoin(ACoin.ACoin):
  """this class is just a wrapper around the Acoin.Acoin class so we can look up the bank key"""
  def get_bank_key(self):
    self.bankKey = Globals.ACOIN_KEY   
