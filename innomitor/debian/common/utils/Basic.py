#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""The most very basic operations.  Are either used everywhere, or should be in python."""

import types
import struct

from common import Globals

def _(data):
  """Use this to wrap all user-displayed strings.  Can then do a lookup for translations"""
  return str(data)

###############################################################################
# Logging
###############################################################################  
  
def log_msg(msg, debugval=0, log=None):
  """Use this function for logging everywhere.  Will send to the logger if available."""
  if Globals.logger:
    Globals.logger.log_msg(msg, debugval, log)
  else:
    print(msg)
  
def log_ex(reason, title, exceptions=None, reasonTraceback=None, excType=None):
  """Use this function for logging everywhere.  Will send to the logger if available."""
  if Globals.logger:
    Globals.logger.log_ex(reason, title, exceptions, reasonTraceback, excType)
  else:
    print(reason)
    
def clean(data):
  """@returns: data if we are NOT anonymizing logs, otherwise returns a fixed string to indicate that this information was filtered out"""
  if Globals.CLEAN_LOGS:
    return "(data anonymized)"
  else:
    return str(data)
    
###############################################################################
# Misc
###############################################################################  

def compare_versions_strings(versionString1, versionString2):
  """Returns True if the v1 is greater than v2"""
  def make_version_tuple(versionString):
    """Convert a string like 0.4.9rc5 to a tuple (0,4,9,5))"""
    vals = versionString.split(".")
    if vals[-1].lower().find("rc") == -1:
      vals[-1] = vals[-1]+"rc1000000000"
    last2 = vals[-1].lower().split("rc")
    vals.remove(vals[-1])
    vals += last2
    vals = [int(x) for x in vals]
    return vals
    
  #convert the version strings to something easier to compare
  versionTuple1 = make_version_tuple(versionString1)
  versionTuple2 = make_version_tuple(versionString2)
  
  #compare each element of the tuple to figure out which is greater
  for i in range(0, len(versionTuple1)):
    if versionTuple1[i] > versionTuple2[i]:
      return True
    elif versionTuple1[i] < versionTuple2[i]:
      return False
  return False

def validate_result(result, name):
  """Returns False if there was any error.  Logs any unexpected errors.  
  Results of False dont count as unexpected, but still count as failures.
  Returns True if everything checked out.  Useful for handling DeferredLists
  and regular Deferreds in the same way."""
  if result is True:
    return True
  elif result is False:
    return False
  elif type(result) in (types.ListType, types.TupleType):
    allGood = True
    for val in result:
      if not validate_result(val, name):
        allGood = False
        #NOTE:  we dont break here because we want to call validate result for all, 
        #so that non-Boolean return values get logged
    return allGood
  else:
    log_ex(result, "Unexpected result for %s" % (name))
    return False

def validate_type(data, dataType):
  """Ensure that data is of dataType.  If not, an exception is raised.
  @type data: object
  @type dataType:  type"""
  #TODO: change this to if isinstance(data, dataType) where dataType is basestring for string testing... (supports unicode) which currently fails this test
  if type(data) != dataType:
    raise Exception("Argument must be a %s.  Data was:\n%s\nwhich is a %s" % (dataType, data, type(data)))

def exception_is_a(reason, errors):
  """Check if 'reason' is one of the exception types listed in errors.
  @param reason:  the exception
  @type  reason:  an Exception or Failure (uses the Exception from the Failure)
  @param errors:  a list of types of Exceptions to check for
  @type  errors:  List"""
  #check if this is a Twisted Failure without having to import that class:
  if hasattr(reason, "value") and issubclass(type(reason.value), Exception):
    reason = reason.value
  if issubclass(type(reason), Exception) and errors:
    for error in errors:
      if issubclass(type(reason), error):
        return True
  return False
  
def gcd(a, b):
  """Euclid's Algorithm for the greatest common divisor"""
  while b:
    a, b = b, a % b
  return a
  
def bytes_to_long(data):
  """Convert from a string to a long.
  @type data: str"""
  validate_type(data, types.StringType)
  return _bytes_to_long(data)

def long_to_bytes(data, dataLen):
  """Convert from a long to a string.  Needs to know how many bytes the
  resulting string should be, so it can append 0-bytes to the front in the case
  where the number happened to be smaller than expected."""
  validate_type(data, types.LongType)
  newStr = _long_to_bytes(data)
  if len(newStr) > dataLen:
    raise Exception('the length of the string: %s is bigger than dataLen: %s'%(len(newStr), dataLen))
  while len(newStr) < dataLen:
    newStr = '\0' + newStr
  return newStr
  
def _long_to_bytes(data, blocksize=0):
  """long_to_bytes(data:long, blocksize:int) : string
  Convert a long integer to a byte string.

  If optional blocksize is given and greater than zero, pad the front of the
  byte string with binary zeros so that the length is a multiple of
  blocksize.
  """
  # after much testing, this algorithm was deemed to be the fastest
  resultString = ''
  data = long(data)
  pack = struct.pack
  while data > 0:
    resultString = pack('>I', data & 0xffffffffL) + resultString
    data = data >> 32
  # strip off leading zeros
  i = 0
  for i in range(len(resultString)):
    if resultString[i] != '\000':
      break
  else:
    # only happens when data == 0
    resultString = '\000'
    i = 0
  resultString = resultString[i:]
  # add back some pad bytes.  this could be done more efficiently w.r.t. the
  # de-padding being done above, but sigh...
  if blocksize > 0 and len(resultString) % blocksize:
    resultString = (blocksize - len(resultString) % blocksize) * '\000' + resultString
  return resultString

def _bytes_to_long(data):
  """bytes_to_long(string) : long
  Convert a byte string to a long integer.

  This is (essentially) the inverse of long_to_bytes().
  """
  acc = 0L
  unpack = struct.unpack
  length = len(data)
  if length % 4:
    extra = (4 - length % 4)
    data = '\000' * extra + data
    length = length + extra
  for i in range(0, length, 4):
    acc = (acc << 32) + unpack('>I', data[i:i+4])[0]
  return acc

###############################################################################
# Message packing and unpacking
###############################################################################

def read_message(format, msg):
  size = struct.calcsize(format)
  assert size <= len(msg), "Message was not long enough to unpack %s" % (format)
  return struct.unpack(format, msg[:size]), msg[size:]

def read_byte(msg):
  vals, msg = read_message("!B", msg)
  return vals[0], msg

def write_byte(msg):
  return struct.pack("!B", msg)

def read_short(msg):
  vals, msg = read_message("!H", msg)
  return vals[0], msg

def write_short(msg):
  return struct.pack("!H", msg)
  
def read_int(msg):
  vals, msg = read_message("!I", msg)
  return vals[0], msg

def write_int(msg):
  return struct.pack("!I", msg)
  
def read_long(msg):
  vals, msg = read_message("!L", msg)
  return vals[0], msg

def write_long(msg):
  return struct.pack("!L", msg)
  
def read_hexid(msg):
  vals, msg = read_message("!20s", msg)
  return vals[0].encode("hex").upper(), msg

def write_hexid(msg):
  return struct.pack("!20s", msg.decode("hex"))
  
def read_lenstr(msg):
  msgLen, msg = read_int(msg)
  vals, msg = read_message("!%ss" % (msgLen), msg)
  return vals[0], msg

def write_lenstr(msg):
  return struct.pack("!I%ss" % (len(msg)), len(msg), msg)
