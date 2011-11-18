#!/usr/bin/python
# Copyright 2008-2009 Innominet
"""A module with a bunch of random functions."""

import sys

import twisted.python.log
from twisted.internet import defer
from twisted.internet.abstract import isIPAddress

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

def is_local_ip(addr):
  """@param addr:  check if this IP address is from the local network or machine
  @returns:  True if this is a local address, False otherwise"""
  if not isIPAddress(addr):
    raise Exception("That's not even an IP address!  %s" % (addr))
  v = [int(x) for x in addr.split(".")]
  if v[0] == 10 or v[0] == 127 or v[:2] in ([192, 168], [169, 254]):
    return True
  if v[0] == 172 and v[1] >= 16 and v[1] <= 31:
    return True
  return False

def install_exception_handlers(quitFunc=None):
  """this handles exceptions that would normally be caught by Python or Twisted and just silently ignored..."""
  def handle_exception(excType, value, tb):
    log_ex(value, "Unhandled exception in main loop:", reasonTraceback=tb, excType=excType)
  sys.excepthook = handle_exception
  #this handles exceptions that would normally be caught by Twisted:
  def handle_twisted_err(_stuff=None, _why=None, quitFunc=quitFunc, **kw):
    excType = None
    tb = None
    #get the exception from the system if necessary
    if not _stuff or issubclass(type(_stuff), Exception):
      (excType, _stuff, tb) = sys.exc_info()
    #check if this is a shutdown signal
    if quitFunc and _stuff and issubclass(type(_stuff), KeyboardInterrupt):
      log_msg("Shutting down from keyboard interrupt...", 0)
      quitFunc()
      return
    #otherwise, log the exception
    if excType and tb:
      log_ex(_stuff, "Unhandled exception from Twisted:", reasonTraceback=tb, excType=excType)
    else:
      log_ex(_stuff, "Unhandled failure from Twisted:")
  twisted.python.log.err = handle_twisted_err
  twisted.python.log.deferr = handle_twisted_err
  #for debugging deferreds--maintains the callstack so AlreadyCalled errors are easier to debug
  defer.setDebugging(True)
  
#TODO:  remove this monkeypatching once this fix is in everyone's installed twisted  :(
#see this ticket:  http://twistedmatrix.com/trac/ticket/3998
def apply_dns_hack():
  import socket
  from twisted.names import dns
  import twisted.names.common
  def extractRecord(resolver, name, answers, level = 10):
      if not level:
          return None
      if hasattr(socket, 'inet_ntop'):
          for r in answers:
              if r.name == name and r.type == dns.A6:
                  return socket.inet_ntop(socket.AF_INET6, r.payload.address)
          for r in answers:
              if r.name == name and r.type == dns.AAAA:
                  return socket.inet_ntop(socket.AF_INET6, r.payload.address)
      for r in answers:
          if r.name == name and r.type == dns.A:
              return socket.inet_ntop(socket.AF_INET, r.payload.address)
      for r in answers:
          if r.name == name and r.type == dns.CNAME:
              result = extractRecord(resolver, r.payload.name, answers, level - 1)
              if not result:
                  return resolver.getHostByName(str(r.payload.name), effort=level-1)
              return result
      # No answers, but maybe there's a hint at who we should be asking about this
      for r in answers:
          if r.type == dns.NS:
              from twisted.names import client
              r = client.Resolver(servers=[(str(r.payload.name), dns.PORT)])
              return r.lookupAddress(str(name)
                  ).addCallback(lambda (ans, auth, add): extractRecord(r, name, ans + auth + add, level - 1)
                  #Just removed this, as described in the ticket link above
                  )#.addBoth(lambda passthrough: (r.protocol.transport.stopListening(), passthrough)[1])
  twisted.names.common.extractRecord = extractRecord
  
#TODO:  remove this monkey-patching when Twisted is fixed for real...
#see here:  http://twistedmatrix.com/trac/ticket/970
#NOTE:  i took the attachment from that page, not the commit.  The commit didnt work for me...
def apply_dns_hack2():
  import warnings
  import exceptions

  from twisted.names import dns
  from twisted.names.root import _DummyController, retry

  def cleanUpProtocolInstance(data, protocolInstance):
      if protocolInstance is None:
          log_msg("protocollInstance is None", 0)
      else:
          try:
              protocolInstance.transport.stopListening()
          except exceptions.AttributeError:
              log_msg("ProtocolInstance: %s could not be cleaned up after: %s" % (protocolInstance,protocolInstance.transport))           
      return data

  def lookupNameservers(host, atServer, p=None):
      pWasNone=(p is None)
      if pWasNone:
          p = dns.DNSDatagramProtocol(_DummyController())
          p.noisy = False
      ret=retry(
          (1, 3, 11, 45),                     # Timeouts
          p,                                  # Protocol instance
          (atServer, dns.PORT),               # Server to query
          [dns.Query(host, dns.NS, dns.IN)]   # Question to ask
      )
      if pWasNone:
          ret.addBoth(cleanUpProtocolInstance,p)
      return ret

  def lookupAddress(host, atServer, p=None):
      pWasNone=(p is None)
      if pWasNone:
          p = dns.DNSDatagramProtocol(_DummyController())
          p.noisy = False
      ret = retry(
          (1, 3, 11, 45),                     # Timeouts
          p,                                  # Protocol instance
          (atServer, dns.PORT),               # Server to query
          [dns.Query(host, dns.A, dns.IN)]    # Question to ask
      )
      if pWasNone:
          ret.addBoth(cleanUpProtocolInstance,p)
      return ret

  import twisted.names.root
  twisted.names.root.cleanUpProtocolInstance = cleanUpProtocolInstance
  twisted.names.root.lookupNameservers = lookupNameservers
  twisted.names.root.lookupAddress = lookupAddress
