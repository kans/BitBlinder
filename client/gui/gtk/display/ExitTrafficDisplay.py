#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Window for selecting exit traffic types"""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.events import GeneratorMixin
from gui.gtk.utils import GTKUtils
from gui.gtk.utils import Images
from gui.gtk.display import SettingsDisplay
from Applications import Tor

PADDING = 10
SUCCESS_PIXBUF = Images.make_icon("apply.png", 48)

class ExitTrafficDisplay(GeneratorMixin.GeneratorMixin):
  def __init__(self):
    GeneratorMixin.GeneratorMixin.__init__(self)
    self.torApp = Tor.get()
    self._add_events("done")

    #make the components for this GUI
    headerBox = self._make_header_box()
    exitTrafficBox = self._make_exit_traffic_box()
    buttonBox = self._make_button_box()
    
    #pack them into our window:
    box = gtk.VBox(spacing=PADDING)
    box.pack_start(headerBox, False, False, 0)
    box.pack_start(exitTrafficBox, False, False, 0)
    box.pack_start(gtk.HSeparator(), False, False, 0)
    box.pack_start(buttonBox, False, False, 0)
    box.show()
    
    paddedBox = GTKUtils.add_padding(box, PADDING)
    paddedBox.show()
    
    self.container = paddedBox
    self.label = gtk.Label("Exit Traffic Types")
    
    self.container.set_focus_child(self.doneButton)
    
  def start(self):
    self.container.show()
    
  def stop(self):
    self.container.hide()
    
  def _make_header_box(self):
    """Make the congratulations message"""
    self.headerBoxLabel = gtk.Label()
    self.headerBoxImage = gtk.Image()
    self.headerBoxLabel.set_markup("<span size='x-large' weight='bold'>Relay Setup Complete!</span>")
    self.headerBoxImage.set_from_pixbuf(SUCCESS_PIXBUF)
    headerBox = gtk.HBox(spacing=PADDING)
    headerBox.pack_start(self.headerBoxImage, False, False, 0)
    headerBox.pack_start(self.headerBoxLabel, False, False, 0)
    headerBox.show_all()
    return headerBox
    
  def _make_exit_traffic_box(self):
    def make_exit_row(labelText):
      #make the widgets
      label = gtk.Label()
      label.set_markup("<span size='large'>%s</span>" % (labelText))
      entry = SettingsDisplay.make_entry("bool", True)
      #and pack them together
      box = gtk.HBox()
      box.pack_start(label, False, False, 0)
      box.pack_end(entry.entry, False, False, 0)
      return (entry, box)
    
    #make widgets
    exitTrafficLabel = gtk.Label()
    exitTrafficLabel.set_markup("<span size='large' weight='bold'>Exit Traffic Permissions:</span>")
    exitTrafficLabel.set_alignment(0.0, 0.5)
    self.webTrafficEntry, webBox = make_exit_row("   Allow Web Traffic")
    self.btTrafficEntry, btBox = make_exit_row("   Allow BitTorrent Traffic")
    self.dhtTrafficEntry, dhtBox = make_exit_row("   Allow DHT Traffic")
    risksLink = GTKUtils.make_html_link("What are the risks?", "")
    risksLink.label.set_alignment(0.0, 0.5)
    
    #pack them together:
    box = gtk.VBox(spacing=PADDING)
    box.pack_start(exitTrafficLabel, False, False, 0)
    box.pack_start(btBox, False, False, 0)
    box.pack_start(webBox, False, False, 0)
    box.pack_start(dhtBox, False, False, 0)
    box.pack_start(risksLink, False, False, 0)
    box = GTKUtils.add_padding(box, PADDING)
    frame = GTKUtils.add_frame(box, width=0)
    frame.show_all()
    return frame
    
  def _make_button_box(self):
    self.doneButton = gtk.Button("Done")
    self.doneButton.connect("clicked", self._on_done)
    self.doneButton.show()
    
    box = gtk.HBox()
    box.pack_end(self.doneButton, False, False, 0)
    box.show()
    return box
    
  def _apply(self):
    exitType = "None"
    if self.webTrafficEntry.get_value() and self.btTrafficEntry.get_value():
      exitType = "Both"
    elif self.btTrafficEntry.get_value():
      exitType = "BitTorrent"
    elif self.webTrafficEntry.get_value():
      exitType = "Web"
    self.torApp.settings.exitType = exitType
    self.torApp.settings.completedServerSetup = True
    self.torApp.settings.on_apply(self.torApp, "")
    self.torApp.settings.save()
    
  def _on_done(self, widget=None):
    self._apply()
    self._trigger_event("done")
      