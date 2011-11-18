#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Base class for dialogs."""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class BaseDialog():
  """A wrapper for gtk.Dialog so that it is appropriately destroyed and the interface is simplified"""
  def __init__(self, title, buttonNames, parent):
    self.title = title
    if buttonNames:
      buttons = []
      for buttonName in buttonNames:
        if buttonName.lower() in ("yes", "no", "ok", "cancel", "apply"):
          buttons.append(getattr(gtk, "STOCK_" + buttonName.upper()))
          buttons.append(getattr(gtk, "RESPONSE_" + buttonName.upper()))
      buttons = tuple(buttons)
    else:
      buttons = None
      
    if parent:
      flags = gtk.DIALOG_DESTROY_WITH_PARENT
    else:
      flags = 0
      
    self.dia = gtk.Dialog(title, parent, flags, buttons)
    #connect the handler:
    self.dia.connect("response", self._on_response)
    #start the dialog
    self.dia.show_all()

  def on_response(self, responseId):
    """Override this function to handle the result of the dialog"""
    raise NotImplementedError()
    
  def on_done(self):
    """Override this function to do any cleanup that must always run"""
    return
    
  def _on_response(self, dialog, responseId):
    """Let the base class handle the response.  Then destroy the dialog unless the base class says not to."""
    #let the base class handle the response:
    try:
      result = self.on_response(responseId)
    except Exception, error:
      log_ex(error, "Failure while handling response for '%s' dialog" % (self.title))
      return
      
    #return if the base class returned True to indicate that they completely handled the event
    if result is True:
      return
      
    #otherwise, let the base class do any necessary cleanup
    self._on_done()
    
  def raise_(self):
    if self.dia and self.dia.window:
      self.dia.window.raise_()
      
  def _on_done(self):
    """Trigger any necessary cleanup"""
    try:
      self.on_done()
    except Exception, error:
      log_ex(error, "Failure while handling on_done for '%s' dialog" % (self.title))
      
    #then destroy the dialog
    self.dia.destroy()
    self.dia = None
    