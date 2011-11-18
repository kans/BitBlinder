#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Cryptographic utility functions."""

import types
import time
import hashlib

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

def make_hash(msg):
  """hashes msg (a string) using SHA256.  Returns a string of 32 bytes"""
  assert type(msg) == types.StringType, "Cannot hash non-string data, msg was a %s" % (type(msg))
  hashObj = hashlib.sha256(msg)
  return hashObj.digest()
  
#TODO:  there has to be a library function for this.  Also I probably did it wrong.
def hash_file_data(fileName):
  """Read a file in blocks of 4KB and hash it all together.
  @returns:  the hash of the whole file."""
  fileToHash = open(fileName, "rb")
  hashObj = hashlib.sha256()
  while True:
    data = fileToHash.read(4096)
    if not data:
      break
    hashObj.update(data)
    time.sleep(0.001)
  fileToHash.close()
  return hashObj.hexdigest()