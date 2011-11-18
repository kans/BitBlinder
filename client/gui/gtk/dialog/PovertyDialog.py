#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Dialog that pops up when a user runs out of credits"""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.events import GlobalEvents
from gui.gtk.widget import OptionalToggleFrame
from gui.gtk.utils import WrapLabel
from gui.gtk.utils import GTKUtils
from gui.gtk.utils import Images
from core import ProgramState
from Applications import BitBlinder
from Applications import Tor

CREDITS_HELP_TEXT = "\
\tThe goal of BitBlinder is to make anonymity practical.\
  This includes ensuring that the network is fast enough for people to use normally.\
  A little background is in order on how online anonymity works:\n\
\tThe basic mechanism for online anonymity is to proxy your web traffic through other computers.\
  To the outside world, it looks as if your traffic comes from one of these other computers.\
  In BitBlinder, these computers are other users of BitBlinder--\
peers around the world just like you who send your traffic on your behalf.\n\
\tTo keep BitBlinder fast, you are required to share as much bandwidth as you use.\
  Our credits ensure that this balance is maintained without infringing on your anonymity.\
  In order to earn credits, you must run a relay, though we do not require you to run an exit (ie, send traffic to NON-BitBlinder internet addresses) if you are uncomfortable with that.\
  We also give new users a few credits to get started and to try out BitBlinder.\
" 

PADDING = 5

class PovertyDialog(GlobalEvents.GlobalEventMixin):
  def __init__(self, controller):
    self.window = gtk.Window()
    self.window.set_title("Out of credits!")
    self.controller = controller
    
    self.catch_event("settings_changed")
    self.window.connect("destroy", self._destroy_cb)
    
    #tell the user what happened
    headerLabel = gtk.Label()
    headerLabel.set_markup("<span size='x-large' weight='bold'>You have spent all your credits.\n</span>")
    headerImage = gtk.Image()
    headerImage.set_from_pixbuf(Images.make_icon("warning.png", 32))
    headerBox = gtk.HBox(spacing=PADDING)
    headerBox.pack_start(headerImage, False, False, 0)
    headerBox.pack_start(headerLabel, False, False, 0)
    descriptionLabel = WrapLabel.WrapLabel("You must get more credits before you can keep sending traffic through BitBlinder.  All users are given a small number of new credits each hour.\n\nYou can keep downloading with BitTorrent by disabling anonymity (upper right of the BitTorrent interface), but you will obviously not be anonymous!")
    descriptionBox = gtk.VBox(spacing=PADDING)
    descriptionBox.pack_start(headerBox, False, False, 0)
    descriptionBox.pack_start(descriptionLabel, False, False, 0)
    descriptionBox.show_all()
    
    #make some help text to explain what credits are
    creditLabel = WrapLabel.WrapLabel(CREDITS_HELP_TEXT)
    creditLabel = GTKUtils.add_padding(creditLabel, PADDING)
    creditLabel.show()
    creditExplanation = OptionalToggleFrame.OptionalToggleFrame(creditLabel, "What are credits?")
    creditExplanation = GTKUtils.add_padding(creditExplanation, PADDING)
    creditExplanation.show()
    
    #only appears if the user is still not configured as a relay
    relayButton = GTKUtils.make_image_button('<span size="large">Start Relay</span>', self._start_relay_cb, "power_off.png")
    relayLabel = WrapLabel.WrapLabel()
    relayLabel.set_markup('<span size="large" weight="bold">You should set up a relay!  </span><span size="large">You will earn credits MUCH more quickly by being a relay and sending traffic for other users.</span>')
    self.relayRow = gtk.HBox(spacing=PADDING)
    spacingBox = gtk.VBox()
    spacingBox.pack_start(relayButton, True, False, 0)
    self.relayRow.pack_start(spacingBox, False, False, 0)
    self.relayRow.pack_start(relayLabel, True, True, 0)
    self.relayRow = GTKUtils.add_frame(self.relayRow, width=PADDING, name="Relay Setup")
    self.relayRow.show_all()
    
    #if we should always check
    self.alwaysShow = gtk.CheckButton("Always tell you when your credits run out.")
    self.alwaysShow.set_active(True)
    self.alwaysShow.show()
    
    #make the bottom button row
    waitButton = GTKUtils.make_image_button('<span size="large">Wait for Credits</span>', self._wait_cb, "time.png")
    purchaseButton = GTKUtils.make_image_button('<span size="large">Purchase Credits</span>', self._purchase_cb, "money.png")
    buttonRow = gtk.HBox(spacing=PADDING)
    buttonRow.pack_end(waitButton, False, False, 0)
    buttonRow.pack_end(purchaseButton, False, False, 0)
    buttonRow = GTKUtils.add_padding(buttonRow, PADDING)
    buttonRow.show_all()
    
    #pack everything together
    topBox = gtk.VBox(spacing=PADDING)
    topBox.pack_start(descriptionBox, False, False, 0)
    topBox.pack_start(creditExplanation, False, False, 0)
    topBox.pack_start(self.relayRow, False, False, 0)
    topBox.pack_start(self.alwaysShow, False, False, 0)
    topBox.show()
    topBox = GTKUtils.add_padding(topBox, PADDING)
    topBox.show()
    vbox = gtk.VBox()
    vbox.pack_start(topBox, False, False, 0)
    sep = gtk.HSeparator()
    sep.show()
    vbox.pack_end(buttonRow, False, False, 0)
    vbox.pack_end(sep, False, False, 0)
    vbox.show()
    
    #and add it into our dialog
    self.window.add(vbox)
    self.window.show()
    
#    self._update_relay_box_visibility()
    
  def show(self):
    self._update_relay_box_visibility()
    self.window.show()
    
  def hide(self):
    self.window.hide()
    
  def on_settings_changed(self):
    self._update_relay_box_visibility()
    
  def _update_relay_box_visibility(self):
    if Tor.get().is_server():
      self.relayRow.hide()
    else:
      self.relayRow.show()
    GTKUtils.refit(self.relayRow)
    
  def _start_relay_cb(self, widget=None):
    if not Tor.get().is_server():
      self.controller.toggle_relay()
      
  def _wait_cb(self, widget=None):
    self._on_done()
    
  def _purchase_cb(self, widget=None):
    GlobalEvents.throw_event("open_web_page_signal", '%s/purchase/' % (ProgramState.Conf.BASE_HTTP), True)
    self._on_done()
    
  def _destroy_cb(self, *args):
    self._on_done()
    return True
    
  def _on_done(self):
    BitBlinder.get().settings.alwaysShowPovertyDialog = self.alwaysShow.get_active()
    BitBlinder.get().settings.save()
    self.window.hide()
    
