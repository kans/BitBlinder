#!/usr/bin/python
"""Contains an anonymous coin class."""

import struct

from hashlib import md5

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common import Errors
from common.utils import Basic
from common.classes import EasyComparableMixin

SEPARATOR = " "
MESSAGE_FORMAT = "!%ssI%ss" % (Globals.ACOIN_BYTES, Globals.ACOIN_KEY_BYTES)
MESSAGE_SIZE = struct.calcsize(MESSAGE_FORMAT)

SIG_FORMAT = "!%ssI"%(Globals.ACOIN_BYTES)
SIG_SIZE = struct.calcsize(SIG_FORMAT)

VALUE = 1
  
class ACoinValidationError(Errors.CoinValidationError):
  """ACoin invalid"""

class ACoin(EasyComparableMixin.EasyComparableMixin):
  """An anonymous coin.  The coin is given a bank-blind signature that
  depends on the value and interval of the coin--different keys are used
  for different values."""
  COMPARISON_ORDER = ("receipt", "value", "interval")
  
  @staticmethod
  def pack_acoin_for_signing(receipt, interval):
    return struct.pack(SIG_FORMAT, receipt, interval)
    
  def __init__(self):
    self.name = 'ACoin'
    self.initialized = False
    self.value = None
    self.sent_deposit_request = False
    self.bankKey = None
    
  def write_binary(self):
    msg = struct.pack(MESSAGE_FORMAT, self.receipt, self.interval, self.signature)
    return msg
    
  def read_binary(self, msg):
    vals, msg = Basic.read_message(MESSAGE_FORMAT, msg)
    self.receipt = vals[0]
    self.interval = vals[1]
    self.signature = vals[2]
    self.value = VALUE
    self.initialized = True
    if self.interval == 0:
      temp = 4
    return msg
  
  def create(self, value, receipt, sig, interval=1):
    """Initialize an ACoin with the details from the bank response."""
    self.value = value
    self.receipt = receipt
    self.signature = sig
    self.initialized = True
    self.interval = interval
    if self.interval == 0:
      temp = 4
    
  def is_valid(self, currentAcoinInterval):
    """Check whether this coin is valid.
    Will return false if invalid, or if not yet initialized, True if valid."""
    try:
      self.validate(currentAcoinInterval)
    except ACoinValidationError, e:
      return False
    return True
      
  def validate(self, currentAcoinInterval):
    """Do the validation process.  Raises exceptions if anything is out of order.
    @param currentAcoinInterval: the current, globally known acoin interval
    @type currentAcoinInterval: int
    @return: None"""
    if not self.initialized:
      raise ACoinValidationError("not initialized")
    if not self.bankKey:
      self.get_bank_key()
    if not self.bankKey:
      raise ACoinValidationError("bank key not known")
    #generate the message that was signed:
    msg = self.pack_acoin_for_signing(self.receipt, self.interval)
    #check that the signature works out- ie, the encrypted blinded sig on the receipt must match the original msg-
    #also gets wierd because we can't use padding with blinding so a bunch of nulls get added to the msg
    if self.bankKey.encrypt(self.signature, False)[-len(msg):] != msg:
      raise ACoinValidationError("bad bank signature")
    if not self.is_fresh(currentAcoinInterval):
      raise ACoinValidationError("Coin has either expired is from the future!")
      
  def is_fresh(self, currentAcoinInterval):
    """the coin interval has to be from this interval or the previous one to be valid"""
    if self.interval != currentAcoinInterval and self.interval != currentAcoinInterval-1:
      return False
    else:
      return True
    
  def store(self):
    """hashes the signature for storage at the bank to check for double deposits
    md5 is ok because purposefully generating a collision entails a loss"""
    return md5(self.signature).digest()
    
  def is_depositable(self):
    """Return True if the coin is valid.  This is just to make SCoins and ACoins have a common interface."""
    return self.is_valid()
  
  def get_deposit_value(self):
    """Get the value of the ACoin."""
    return self.value
  
  def get_expected_value(self):
    """Get the value of the ACoin."""
    return self.value