#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""A custom version of the GTK2Reactor from Twisted."""

import sys
import socket

from twisted.internet import gtk2reactor
from twisted.internet import selectreactor
from twisted.internet.main import installReactor
from twisted.python import runtime

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core import ProgramState

#NOTE:  hurray for monkeypatching...
class GtkReactor(gtk2reactor.PortableGtkReactor):
  """This class is necessary because a number of modifications need to be made
  to the GtkReactor so that it can be run with my custom main iteration loop
  below (e.g. we dont run gtk.main() but want Twisted to be part of the Gtk
  event loop anyway)"""
  
  @staticmethod
  def install():
    """Start up the Twisted networking support.  Returns the new, running reactor."""
    #This works fine anyway I think?  Not really sure why this is here, just keeping it how it was in Twisted
    if runtime.platform.getType() == 'posix':
      reactor = gtk2reactor.install(ProgramState.USE_GTK)
    #Windows needs this custom class
    else:
      try:
        reactor = GtkReactor()
        installReactor(reactor)
      except socket.error, e:
        #NOTE:  10022 is a bit suspect.  I saw it once (it's "invalid argument"), 
        #but it can apparently happen in cases that might be caused by a firewall...
        #10013 is "forbidden"
        #10047 is "cannot bind"
        #10049 is "Can't assign requested address"
        if e[0] not in (10013, 10047, 10049, 10022):
          raise e
        import win32api
        win32api.MessageBox(0, "You must allow incoming and outgoing connections for both BitBlinder.exe and Tor.exe in your firewall.  Otherwise, BitBlinder will not work correctly.", "Firewalled")
        sys.exit(-5)
    reactor._simtag = None
    reactor.startRunning(installSignalHandlers=1)
    reactor.simulate()
    return reactor
  
  def crash(self):
    """Make sure Twisted shuts down properly."""
    #close twisted
    selectreactor.SelectReactor.crash(self)
    #close gtk
    gtk2reactor._our_mainquit()
