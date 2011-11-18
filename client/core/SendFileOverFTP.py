#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Open a connection to an FTP server, send a file, and trigger any callback"""

import re

from twisted.protocols.ftp import FTPClient
from twisted.internet.protocol import ClientCreator

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core import ProgramState

class SendFileOverFTP():
  """submits the archive via ftp to the central server and STORs it as name"""
  def __init__(self, archive, name, host=Globals.FTP_HOST, port=Globals.FTP_PORT, user=Globals.FTP_USER, pw=Globals.FTP_PASSWORD):
    zipRegex = re.compile(r"^.*\.zip$")
    if not zipRegex.match(name):
      name += ".zip"
    self.name = name
    self.archive = archive
    log_msg("archive is: %s  name is: %s" % (archive, name), 2)
    FTPClient.debug = 1
    creator = ClientCreator(Globals.reactor, FTPClient, user, pw, passive=1)
    self.d = creator.connectTCP(host, port)
    self.d.addCallback(self.connectionMade)
    self.d.addErrback(self.error)
    self.cb = False
  
  def error(self, failure):
    #ignore shutdown errors
    if ProgramState.DONE:
      return
    log_ex(failure, "Error while submitting logs via FTP")
    if self.cb:
      self.cb(False)
    
  def sendfile(self, consumer):
    f = open(self.archive, "rb")
    consumer.write(f.read())
    consumer.finish()
    
  def success(self, response):
    log_msg('submited logs: %s' % (response), 2)
    if self.cb:
      self.cb(True)
    
  def connectionMade(self, client):
    dC, dL = client.storeFile(self.name)
    dC.addCallback(self.sendfile)
    dC.addErrback(self.error)
    dL.addCallback(self.success)
    dL.addErrback(self.error)
    