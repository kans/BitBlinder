#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Warn the user that they are running out of credits.  Ask them to start being a relay."""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Format
from gui.gtk.utils import GTKUtils
from core.bank import Bank
from Applications import Tor
from Applications import CoreSettings

class MoneyLowDialog():
  def __init__(self, controller):
    buttons = (gtk.STOCK_YES, gtk.RESPONSE_YES, gtk.STOCK_NO, gtk.RESPONSE_NO)
    dia = gtk.Dialog("Credits Low", None, 0, buttons)
    self.controller = controller
    
    vbox = gtk.VBox()
    
    title = gtk.Label()
    markup = "<span size='large' weight='bold'>You Are Running out of Credits</span>"
    title.set_markup(markup)
    title.set_justify(gtk.JUSTIFY_CENTER)
    vbox.pack_start(title, True, False, 0)
    
    #A text entry telling the user what to do:
    balance = Bank.get().get_expected_balance()
    balanceGB = Format.convert_to_gb(balance)
    label = gtk.Label()
    text = "You only have %s (%s) credits remaining.  You must set up a relay to gain more credits.  \
This will allow other users to send traffic via your computer.\n\nWould you like to set up a relay now?" % (balance, balanceGB)
    label.set_markup(text)
    label.set_line_wrap(True)
    vbox.pack_start(label, True, True, 5)
    
    #if we should always check:
    self.askAboutRelay = gtk.CheckButton("Always ask about help setting up relay")
    vbox.pack_start(self.askAboutRelay, True, True, 10)
    #initialize the checkbox:
    self.askAboutRelay.set_active(CoreSettings.get().askAboutRelay)

    vbox = GTKUtils.add_padding(vbox, 5)
    dia.vbox.pack_start(vbox, True, True, 0)
    dia.connect("response", self.on_response)
    self.dia = dia
    #start the dialog
    dia.show_all()

  #handle the result of the dialog:
  def on_response(self, dialog, response_id):
    CoreSettings.get().askAboutRelay = self.askAboutRelay.get_active()
    CoreSettings.get().save()
    if (response_id == gtk.RESPONSE_YES):
      if not Tor.get().settings.beRelay:
        self.controller.toggle_relay()
    else:
      log_msg("User elected not to set up relay.", 4)
    self.dia.destroy()
    
