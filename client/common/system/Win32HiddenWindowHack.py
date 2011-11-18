#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Necessary on windows, unfortunately, to prevent UPNP processes from popping up"""

import os
import win32api
import win32con
import win32file
import win32pipe
import win32process
import win32security
import pywintypes

from twisted.python.win32 import quoteArguments
from twisted.internet import _pollingfile
import twisted.internet._dumbwin32proc

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
  
def apply():  
  def __new_init__(self, reactor, protocol, command, args, environment, path):
      _pollingfile._PollingTimer.__init__(self, reactor)
      self.proto = protocol
      self.protocol = protocol

      # security attributes for pipes
      sAttrs = win32security.SECURITY_ATTRIBUTES()
      sAttrs.bInheritHandle = 1

      # create the pipes which will connect to the secondary process
      self.hStdoutR, hStdoutW = win32pipe.CreatePipe(sAttrs, 0)
      self.hStderrR, hStderrW = win32pipe.CreatePipe(sAttrs, 0)
      hStdinR,  self.hStdinW  = win32pipe.CreatePipe(sAttrs, 0)

      win32pipe.SetNamedPipeHandleState(self.hStdinW,
                                        win32pipe.PIPE_NOWAIT,
                                        None,
                                        None)

      # set the info structure for the new process.
      StartupInfo = win32process.STARTUPINFO()
      StartupInfo.hStdOutput = hStdoutW
      StartupInfo.hStdError  = hStderrW
      StartupInfo.hStdInput  = hStdinR
      StartupInfo.dwFlags = win32process.STARTF_USESTDHANDLES

      # Create new handles whose inheritance property is false
      currentPid = win32api.GetCurrentProcess()

      tmp = win32api.DuplicateHandle(currentPid, self.hStdoutR, currentPid, 0, 0,
                                     win32con.DUPLICATE_SAME_ACCESS)
      win32file.CloseHandle(self.hStdoutR)
      self.hStdoutR = tmp

      tmp = win32api.DuplicateHandle(currentPid, self.hStderrR, currentPid, 0, 0,
                                     win32con.DUPLICATE_SAME_ACCESS)
      win32file.CloseHandle(self.hStderrR)
      self.hStderrR = tmp

      tmp = win32api.DuplicateHandle(currentPid, self.hStdinW, currentPid, 0, 0,
                                     win32con.DUPLICATE_SAME_ACCESS)
      win32file.CloseHandle(self.hStdinW)
      self.hStdinW = tmp

      # Add the specified environment to the current environment - this is
      # necessary because certain operations are only supported on Windows
      # if certain environment variables are present.

      env = os.environ.copy()
      env.update(environment or {})

      cmdline = quoteArguments(args)
      # TODO: error detection here.
      def doCreate():
          for key in env.keys():
            if type(env[key]) == type(u"string"):
              env[key] = env[key].encode('MBCS')
          self.hProcess, self.hThread, self.pid, dwTid = win32process.CreateProcess(
              command, cmdline, None, None, 1, win32process.CREATE_NO_WINDOW, env, path, StartupInfo)
      try:
          doCreate()
      except pywintypes.error, pwte:
          if not twisted.internet._dumbwin32proc._invalidWin32App(pwte):
              # This behavior isn't _really_ documented, but let's make it
              # consistent with the behavior that is documented.
              raise OSError(pwte)
          else:
              # look for a shebang line.  Insert the original 'command'
              # (actually a script) into the new arguments list.
              sheb = twisted.internet._dumbwin32proc._findShebang(command)
              if sheb is None:
                  raise OSError(
                      "%r is neither a Windows executable, "
                      "nor a script with a shebang line" % command)
              else:
                  args = list(args)
                  args.insert(0, command)
                  cmdline = quoteArguments(args)
                  origcmd = command
                  command = sheb
                  try:
                      # Let's try again.
                      doCreate()
                  except pywintypes.error, pwte2:
                      # d'oh, failed again!
                      if twisted.internet._dumbwin32proc._invalidWin32App(pwte2):
                          raise OSError(
                              "%r has an invalid shebang line: "
                              "%r is not a valid executable" % (
                                  origcmd, sheb))
                      raise OSError(pwte2)

      win32file.CloseHandle(self.hThread)

      # close handles which only the child will use
      win32file.CloseHandle(hStderrW)
      win32file.CloseHandle(hStdoutW)
      win32file.CloseHandle(hStdinR)

      self.closed = 0
      self.closedNotifies = 0

      # set up everything
      self.stdout = _pollingfile._PollableReadPipe(
          self.hStdoutR,
          lambda data: self.proto.childDataReceived(1, data),
          self.outConnectionLost)
      
      #Josh:  added this so that stderr data isnt unexpected (causes a useless exception otherwise that we have no good way of handling)
      def got_data(data):
        self.proto.childDataReceived(2, data)
      self.proto.errReceived = self.proto.errReceivedIsGood
        
      self.stderr = _pollingfile._PollableReadPipe(
              self.hStderrR,
              got_data,
              self.errConnectionLost)

      self.stdin = _pollingfile._PollableWritePipe(
          self.hStdinW, self.inConnectionLost)

      for pipewatcher in self.stdout, self.stderr, self.stdin:
          self._addPollableResource(pipewatcher)


      # notify protocol
      self.proto.makeConnection(self)

      # (maybe?) a good idea in win32er, otherwise not
      # self.reactor.addEvent(self.hProcess, self, 'inConnectionLost')
      
      self._addPollableResource(twisted.internet._dumbwin32proc._Reaper(self))
    
  #and finally, apply the monkeypatch:
  twisted.internet._dumbwin32proc.Process.__init__ = __new_init__
    
