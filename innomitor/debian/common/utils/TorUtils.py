#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Misc functions for interacting with Tor."""

import binascii
import hashlib

try:
  from pyasn1.codec.ber import encoder
  from pyasn1.type import univ
except ImportError:
  pass
  #print "Could not import pyasn1"

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

def make_auth_lines(authServers):
  """Make Tor configuration lines corresponding to an authority server."""
  dirServers = ""
  for server in authServers:
    dirServers += "DirServer %s orport=%s v3ident=%s %s:%s %s\n" % (server["name"], server["orport"], server["v3ident"], server["address"], server["dirport"], server["key"])
  return dirServers
  
def get_hex_id(fullRouterName):
  """Extract a hex id from a full Tor event, which specifies both name and hex id"""
  hexId = ""
  if fullRouterName.count("=") > 0:
    hexId = fullRouterName.split("=")[0]
  else:
    hexId = fullRouterName.split("~")[0]
  hexId = hexId.replace("$", "")
  return hexId
  
def fingerprint(publicKeyN, publicKeyE=65537L):
  """In Tor, fingerprints are computed as the SHA1 digest of the ASN.1 encoding
  of the public key, converted to hexadecimal, in upper case, with a
  space after every four digits, though we compress the spaces for our purposes"""
  asn1Str = encoder.encode(univ.Sequence().setComponentByPosition(0, univ.Integer(publicKeyN)).setComponentByPosition(1, univ.Integer(publicKeyE)))
  hashString = hashlib.sha1(asn1Str).digest()
  hexlifiedHash = binascii.hexlify(hashString)
  return hexlifiedHash.upper()