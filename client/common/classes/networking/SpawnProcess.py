#!/usr/bin/python
# Copyright 2008-2009 Innominet
"""Spawn a process and learn when it is launched?"""

from twisted.internet import protocol

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class SpawnProcess(protocol.ProcessProtocol):
  def __init__(self, deferred, stdin=None, outCallback=None, madeCallback=None, errback=None):
    """A convienence class to spawn non blocking processes.
    @param deferred: a deferred to which callback and errback are added
    @type deferred: twisted deferred
    @param stdin: text to write to stdin when we connect to the process
    @type stdin: str
    @param outCallback: callback added to deferred to be called with the data from stdout
    @param madeCallback: callback added to deferred to be called with the pid when the process is created
    currently, you should only pass a single callback or none as two will break it :("""
    self.deferred = deferred
    self.stdin = stdin
    self.pid = None
    self.outCallback = outCallback
    self.madeCallback = madeCallback
    self.errback = errback
    if self.madeCallback:
      self.deferred.addCallback(self.madeCallback)
    if self.outCallback:
      self.deferred.addCallback(self.outCallback)
    if self.errback:
      self.deferred.addErrBack(self.errback)
    
  def connectionMade(self):
    """is called when we connect to the process"""
    self.pid = self.transport.pid
    if self.stdin:
      self.transport.write(self.stdin)
      self.transport.closeStdin()
    if self.madeCallback:
      self.deferred.callback(self.pid)
      
  def outReceived(self, data):
    """receives data from stdout"""
    self.transport.loseConnection()
    if self.outCallback:
      self.deferred.callback(data)
    
  def errReceived(self, data):
    """receives output from stderr"""
    self.transport.loseConnection()
    if self.errback:
      self.deferred.errback(data)
    else:
      log_ex('No errback attached to process to handle stderr%s' % (data), 0)
      