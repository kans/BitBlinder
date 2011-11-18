#!/usr/bin/python
"""

"""
from twisted.conch.ssh import transport, userauth, connection, channel,  keys
from twisted.conch.ssh.common import NS
from twisted.conch.ssh import common
from twisted.conch import error
from twisted.internet import defer, protocol, reactor
import twisted.python.log
import sys
import struct
from common import Globals
from common.utils.Build import check_changelog

USER = 'build'
PASSWORD = 'build'
DEBUG = False
KNOWN_HOSTS = ('1b:72:a8:f1:41:ea:2c:de:d3:e3:68:31:bc:4a:be:1d', '9b:fa:d7:93:5d:f2:7f:6f:1c:9d:0c:08:a3:d4:c3:66')
    
def install_exception_handlers():
  """this handles exceptions that would normally be caught by Python or Twisted and just silently ignored..."""
  def handle_exception(excType, value, tb):
    print('err1:\n%s\n%s\n%s'%(value,  excType, tb))
  sys.excepthook = handle_exception
#  #this handles exceptions that would normally be caught by Twisted:
#  def handle_twisted_err(*args):
#    print('err2: \n%s'%(args))
#  twisted.python.log.err = handle_twisted_err
#  twisted.python.log.deferr = handle_twisted_err
  if DEBUG:
    def log_normal_msg(eventDict):
      if not eventDict["isError"]:
        text = str(eventDict['message']) + '\n'
        sys.stderr.write(text)
        sys.stderr.flush()
    twisted.python.log.addObserver(log_normal_msg)

install_exception_handlers()

class Transport(transport.SSHClientTransport):
  def verifyHostKey(self, pubKey, fingerprint):
    if fingerprint not in (KNOWN_HOSTS):
      return defer.fail(error.ConchError('bad key: %s' % (fingerprint)))
    else:
      return defer.succeed(1)

  def connectionSecure(self):
    self.requestService(UserAuth(USER, self.factory.connectionInstance))

class UserAuth(userauth.SSHUserAuthClient):
  def getPassword(self):
    return defer.succeed(PASSWORD)

#  def getPublicKey(self):
#    key = keys.Key.fromFile('/home/rtard/.ssh/build_key.pub').toString('OPENSSH')
#    print key
#    return key

#  def ssh_USERAUTH_FAILURE(self, packet):
#    print 'failure :*(',  packet
#    #reactor.stop()

  def getPrivateKey(self):
    key = keys.Key.fromFile('/home/rtard/.ssh/build_key')
    return defer.succeed(key)

class Connection(connection.SSHConnection):
  def __init__(self):
    connection.SSHConnection.__init__(self)
    self.currentCmd = None
    self.logFile = None
    self.host = None
    self.port = None
    
  def get_name(self):
    try:
      self.host, self.port = self.transport.transport.realAddress
      #The name of the connection class that is being run over there
      serviceName = self.transport.service.__class__.__name__
    except:
      self.host, self.port, serviceName = ("Unknown", "Unknown", "Unknown")
    return "%s_%s_%s" % (self.host, self.port, serviceName)
    
  def log_data(self, data):
    self.logFile.write(data)
    self.logFile.flush()
    
  def serviceStarted(self):
    self.logFile = open(self.get_name() + ".out", "wb")
    self._do_next_command()
    
  def _on_all_commands_done(self):
    print "Finished"
    
  def _do_next_command(self):
    if len(self.commands) <= 0:
      self._on_all_commands_done()
      return
    self.currentCmd = self.commands.pop(0)
    self.cmdOutput = ''
    channel = CommandChannel(self.currentCmd, self._on_command_done, conn = self)
    self.openChannel(channel)
    
  def _on_command_done(self, returnCode, output):
    if returnCode != 0:
      self.failure(BadChangelog(self.currentCmd, returnCode, output))
      return
    else:
      print("Command:  %s\nOutput:\n%s" % (self.currentCmd, output))
    self._do_next_command()

  def failure(self, reason=None):
    print reason
    
class BadChangelog(Exception):
  def __init__(self, cmd, returnCode, output):
    self.cmd = cmd
    self.returnCode = returnCode
    self.output = output
    
  def __str__(self):
    return "Last command (%s) failed with code %s and output:  %s" % (self.currentCmd, self.returnCode, self.output)
    
class LinuxInnomitorBuild(Connection):
  def __init__(self):
    Connection.__init__(self)
    self.commands = ['cd /home/innomitor/ 2>&1 && svn update 2>&1 && cd debian 2>&1 && python build.py 2>&1',
                     'echo "done"']
                
class LinuxBitBlinderCommit(Connection):
  def __init__(self, version):
    Connection.__init__(self)
    self.buildName = "bitblinder"
    self.version = version
    self.commands = ['cd /home/client/; svn commit -m "created new changelog for version %s"' % (self.version)]
    
  def _on_all_commands_done(self):
    reactor.connectTCP(self.host, self.port, SSHFactory(LinuxBitBlinderBuild(self.version)))

class LinuxBitBlinderBuild(Connection):
  def __init__(self, version):
    Connection.__init__(self)
    self.buildName = "bitblinder"
    self.version = version
    self.hadBadChangelogVersion = False
    self._set_build_commands()
                     
  def _set_build_commands(self):
    self.commands = ['cd /home/client/ 2>&1 && svn update 2>&1 && cd debian 2>&1 && python build.py --no-input --version %s 2>&1' % (self.version),
                     'echo "done"']
                     
  def failure(self, reason):
    if hasattr(reason, "value"):
      reason = reason.value
    if issubclass(type(reason), BadChangelog):
      self.hadBadChangelogVersion = True
      channel = CommandChannel('cat /home/client/debian/changelog', self._on_changelog_recvd, conn = self)
      self.openChannel(channel)
      
  def _on_changelog_recvd(self, returnCode, output):
    assert returnCode == 0, "Could not print changelog!"
    fileName = "%s_changelog" % (self.get_name())
    f = open(fileName, "wb")
    f.write(output)
    f.close()
    check_changelog(self.buildName, self.version, False, writeVersionFile=False, fileName=fileName)
    print "Committing new changelog..."
    f = open(fileName, "rb")
    data = f.read()
    f.close()
    channel = CommandChannel('cat > /home/client/debian/changelog', self._on_changelog_written, conn=self, dataToWrite=data)
    self.openChannel(channel)
    
  def _on_changelog_written(self, returnCode, output):
    assert returnCode == 0, "Could not write to changelog!"
    reactor.connectTCP(self.host, self.port, SSHFactory(LinuxBitBlinderCommit(self.version)))
    
  def _on_all_commands_done(self):
    #in other words, if we succeeded
    if not self.hadBadChangelogVersion:
      reactor.stop()
    
class CommandChannel(channel.SSHChannel):
  name = 'session'
  def __init__(self, command, callback, localWindow = 0, localMaxPacket = 0,
                       remoteWindow = 0, remoteMaxPacket = 0,
                       conn = None, data=None, avatar = None, dataToWrite=None):
    channel.SSHChannel.__init__(self, localWindow, localMaxPacket,
                       remoteWindow, remoteMaxPacket,
                       conn, data, avatar)
    self.command = command
    self.callback = callback
    self.finished = False
    self.dataToWrite = dataToWrite

  def channelOpen(self, data):
    self.cmdOutput = ''
    d = self.conn.sendRequest(self, 'exec', common.NS(self.command), wantReply = 1)
    d.addCallback(self._command_started)
    d.addErrback(self.failure)
    
  def request_exit_status(self, strData):
    try:
      self.exitCode = struct.unpack("!I", strData)[0]
    except Exception, e:
      self.failure(e)
      return

  def failure(self, reason=None):
    print reason
    if not self.finished:
      self.finished = True
      self.callback(None, self.cmdOutput)
      self.loseConnection()

  def openFailed(self, reason):
    self.failure(reason)

  def _command_started(self, data):
    if self.dataToWrite:
      self.write(self.dataToWrite)
      self.conn.sendEOF(self)
    #self.loseConnection()

  def dataReceived(self, data):
    assert data, "That's stupid, why call dataReceived when you didnt receive any data?  Jerks."
    name = self.conn.get_name()
    print("%s::  %s" % (name, data[:-1]))
    self.conn.log_data(data)
    self.cmdOutput += data

  def closed(self):
    if not self.finished:
      self.finished = True
      self.callback(self.exitCode, self.cmdOutput)
      
class SSHFactory(protocol.ClientFactory):
  def __init__(self, connectionInstance):
    self.protocol = Transport
    self.connectionInstance = connectionInstance

def main():
  #64bit machine builds innomitor and bitblinder
#  reactor.connectTCP('192.168.1.121', 12900, SSHFactory(LinuxInnomitorBuild()))
  reactor.connectTCP('192.168.1.121', 12900, SSHFactory(LinuxBitBlinderBuild(Globals.VERSION)))
  #32bit machine just builds innomitor
#  reactor.connectTCP('192.168.1.121', 13200, SSHFactory(LinuxInnomitorBuild()))
  reactor.run()

if __name__ == "__main__":
  main()
