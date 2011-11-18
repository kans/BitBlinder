#!/usr/bin/python
# Copyright 2008-2009 InnomiNet
"""Wrappers for M2Crypto.RSA class."""

import types
import struct
from random import getrandbits

import M2Crypto
ASN_DEFINED = True
try:
  from pyasn1.codec.ber import decoder
except:
  ASN_DEFINED = False

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common.utils import Crypto

def inverse(u, v):
  """inverse(u:long, u:long):long
  Return the inverse of u mod v.
  """
  u3, v3 = long(u), long(v)
  u1, v1 = 1L, 0L
  while v3 > 0:
    q = u3 / v3
    u1, v1 = v1, u1 - v1*q
    u3, v3 = v3, u3 - v3*q
  while u1 < 0:
    u1 = u1 + v
  return u1

class PublicKey():
  """More Pythonic version of M2Crypto RSA Key class."""
  
  def __init__(self, n, e=None):
    """Pass either two arguments (e,n) to build from existing data, or pass one
    argument (n=existing key) to build from an existing key."""
    if e:
      eStrLen = 0
      tmp = 1L
      while tmp < e or eStrLen % 2 != 0:
        tmp *= 256L 
        eStrLen += 1
      nStrLen = 0
      #NOTE:  this is completely bizarre.  Why does m2crypto think that we need an odd number of bytes to encode a key?
      nStrLen += 1
      tmp = 1L
      while tmp < n or eStrLen % 2 != 0:
        tmp *= 256L 
        nStrLen += 1
      eStr = struct.pack(">I%ss" % (eStrLen), eStrLen, Basic.long_to_bytes(e, eStrLen))
      nStr = struct.pack(">I%ss" % (nStrLen), nStrLen, Basic.long_to_bytes(n, nStrLen))
      self.key = M2Crypto.RSA.new_pub_key((eStr, nStr))
      self.e = long(e)
      self.n = long(n)
    else:
      #validate that this is of the correct type:
      try:
        if n.__class__.__name__ not in ("RSA", "RSA_pub"):
          raise Exception("Wrong type")
      except:
        raise Exception("n is not the right type:  " + str(n))
      self.key = n
    #: length of the key in bytes (used in blinding/unblinding)
    self.keyLen = len(self.key)
    
  def encrypt(self, msg, usePadding=True):
    """Encrypt msg with the key.
    @param msg: message to be decrypted
    @type msg: string
    @param usePadding: use padding if True, otherwise the message isn't padded (as for blinding)
    @type usePadding: bool
    @return: encrypted message as string"""
    Basic.validate_type(msg, types.StringType)
    if usePadding:
      return M2Crypto.m2.rsa_public_encrypt(self.key.rsa, msg, M2Crypto.RSA.pkcs1_padding)
    else:
      return M2Crypto.m2.rsa_public_encrypt(self.key.rsa, msg, M2Crypto.RSA.no_padding)
  
  def verify(self, msg, sig):
    """Return boolean of whether sig is a valid signature of msg with this key."""
    Basic.validate_type(msg, types.StringType)
    Basic.validate_type(sig, types.StringType)
    return self.key.verify(Crypto.make_hash(msg), sig, 'sha256')
  
  def blind(self, message, r, length=None):
    """Blind a message using random number r (assuming length of the key by default)
    @param message: string to be blinded
    @type message: string
    @param r: blinding factor
    @type r: long
    @param length: length of the message after blinding (needed to convert from a long to a string).
    @type long: None or int
    @return: string of message blinded with r assuming length of n
    """
    Basic.validate_type(message, types.StringType)
    Basic.validate_type(r, types.LongType)
    message = Basic.bytes_to_long(message)
    tmp = pow(r, self.e, self.n)
    tmp = (message * tmp) % self.n
    return Basic.long_to_bytes(tmp, length or self.keyLen)
  
  def unblind(self, message, r, length=None):
    """Unblind a message using random number r (assuming length of the key by default)
    @param message: string to be unblinded
    @type message: string
    @param r: blinding factor
    @type r: long
    @param length: length of the message after blinding (needed to convert from a long to a string).
    @type long: None or int
    @return: string of message blinded with r assuming length of n
    """
    Basic.validate_type(message, types.StringType)
    Basic.validate_type(r, types.LongType)
    message = Basic.bytes_to_long(message)
    tmp = inverse(r, self.n)
    tmp =  (message * tmp) % self.n
    return Basic.long_to_bytes(tmp, length or self.keyLen)
  
  def get_blinding_factor(self, numRandomBits):
    """returns a suitable blinding factor
    @return: blinding factor as long
    """
    b = getrandbits(numRandomBits)
    #r must be relatively prime to N
    while Basic.gcd(b, self.n) != 1:
      b = getrandbits(numRandomBits)
    return b
    
if ASN_DEFINED:
  def load_public_key(s=None, fileName=None):
    assert s or fileName, "load_public_key must be passed either a string or file"
    if fileName:
      key = M2Crypto.RSA.load_pub_key(fileName)
      publicKey = PublicKey(key)
      eStr, nStr = key.pub()
      publicKey.e = Basic.bytes_to_long(eStr[4:])
      publicKey.n = Basic.bytes_to_long(nStr[4:])
      return publicKey
    else:
      start = s.find("-----BEGIN RSA PUBLIC KEY-----")
      end = s.find("-----END RSA PUBLIC KEY-----")
      if start == -1:
        raise Exception("Missing PEM prefix")
      if end == -1:
        raise Exception("Missing PEM postfix")
      remainder = s[end+len("-----END RSA PUBLIC KEY-----\n\r"):]
      s = s[start+len("-----BEGIN RSA PUBLIC KEY-----") : end]

      parser = decoder.decode(s.decode("base64"))[0]
      n = long(parser.getComponentByPosition(0))
      e = long(parser.getComponentByPosition(1))
      
      publicKey = PublicKey(n, e)
      return publicKey, remainder
    
