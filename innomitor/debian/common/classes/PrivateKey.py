#!/usr/bin/python
# Copyright 2008-2009 InnomiNet
"""Wrappers for M2Crypto.RSA class."""

import types

import M2Crypto

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common.utils import Crypto
from common.classes import PublicKey

class PrivateKey(PublicKey.PublicKey):
  """A simple wrapper for private keys of the Crypto.PublicKey.RSA class.  All
  arguments in and out of these functions should be longs."""
  
  def __init__(self, constructor):
    """Pass either file location of public key or bit length for new key."""
    if isinstance(constructor, basestring):
      #load the key found at location: constructor
      self.key = M2Crypto.RSA.load_key(constructor)
    elif type(constructor) == int:
      #generate a key of length constructor
      def silence(*args):
        pass
      self.key = M2Crypto.RSA.gen_key(constructor, 65537, silence)
    else:
      raise TypeError('invalid argument: %s'%constructor)
    eStr, nStr = self.key.pub()
    self.e = Basic.bytes_to_long(eStr[4:])
    self.n = Basic.bytes_to_long(nStr[4:])
    #: length of the key in bytes (used in blinding/unblinding)
    self.keyLen = len(self.key)
      
  def decrypt(self, msg, usePadding=True):
    """Decrypt msg (str) with key, return the result (as a string)
    @param msg: message to be decrypted
    @type msg: string
    @param usePadding: use padding if True, otherwise the message isn't padded (as for blinding)
    @type usePadding: bool
    @return: encrypted message as string"""
    Basic.validate_type(msg, types.StringType)
    if usePadding:
      return M2Crypto.m2.rsa_private_decrypt(self.key.rsa, msg, M2Crypto.RSA.pkcs1_padding)
    else:
      return M2Crypto.m2.rsa_private_decrypt(self.key.rsa, msg, M2Crypto.RSA.no_padding)
    
  def sign(self, msg):
    """Sign the msg with key, return the result as string"""
    return self.key.sign(Crypto.make_hash(msg), 'sha256')
  
  def publickey(self):
    """Get the PublicKey object that corresponds to this private key."""
    k = PublicKey.PublicKey(self.key)
    k.e = self.e
    k.n = self.n
    return k
    
if __name__ == "__main__":
  #sample usage
  msg = "hello"
  #generate a new key
  k = PrivateKey(1024)
  #check signing:
  sig = k.sign(msg)
  pub = k.publickey()
  result = pub.verify(msg, sig)
  n = k.n
  #get a blinding factor
  b = k.get_blinding_factor(40*8)
  #blind the msg with the blinding factor
  blindedMsg = k.blind(msg, b)
  #sign the message (without any padding- don't do unless you blinded it first)
  sig = k.decrypt(blindedMsg, False)
  #unblind the sig
  unblindedSig = k.unblind(sig, b)
  #verify the sig
  result = k.encrypt(unblindedSig, False)
  print msg
  print result[-len(msg):]
