#!/usr/bin/python
"""Contains an anonymous coin class for use on the client."""
import time
 
from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import ACoin as ACoinParent

class ACoin(ACoinParent.ACoin):
  """An anonymous coin on the client side."""
  def __init__(self, bankKeyStore):
    ACoinParent.ACoin.__init__(self)
    #: if this coin was recieved as a payment, points to the originating circuit.  That way it can be closed if the coin is invalid.
    self.originCircuit = None
    #: this object must implement get_acoin_key (currently just the bank)
    self.bankKeyStore = bankKeyStore
    
  def get_bank_key(self):
    """grabs the correct public bank key, given this coins value"""
    self.bankKey = self.bankKeyStore.get_acoin_key(self.value)
    
  def is_fresh(self, currentAcoinInterval):
    """the coin interval has to be from this interval the previous, or the next one to be valid
    @param currentACoinInterval:  number of the interval that we think it is now
    @type  currentACoinInterval:  int
    @return:  True if this coin is ok given the current interval"""
    if self.interval in range(currentAcoinInterval-1, currentAcoinInterval+2):
      return True
    log_msg("Got an ACoin from some crazy interval (%s, %s, %s)" % (time.time(), currentAcoinInterval, self.interval), 0)
    return False
