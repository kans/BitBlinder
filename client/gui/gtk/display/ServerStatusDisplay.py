#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Show some very simple status and controls to the user"""
import os

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Format
from common.events import GlobalEvents
from common.events import ListenerMixin
from common.events import GeneratorMixin
from gui.gtk.display import BWGraph
from gui.gtk.utils import GTKUtils
from gui.gtk.utils import WrapLabel
from gui.gtk.utils import Images
from gui.gtk.widget import BaseMenuBar
from gui.gtk.widget import ClosableTabNotebook
from gui.gtk.window import TopWindow
from core import ClientUtil
from core import BWHistory
from core.bank import Bank
from Applications import Tor

def update_tooltips(widget, text):
  """assumes pygtk 2.12"""
  if widget.get_tooltip_text() != text:
    widget.set_tooltip_text(text)
    
def _make_row(labelText, helpText):
  tempBox = gtk.HBox()
  tooltips = gtk.Tooltips()
  tooltips.set_tip(tempBox, helpText)
  label = gtk.Label()
  label.set_markup("<span size='x-large' weight='bold'>%s </span>" % (labelText))
  tempBox.pack_start(label, False, False, 0)
  return tempBox, label
  
def _make_display(labelText, pixbuf, tooltips, helpText):
  tempBox = gtk.HBox()
  row = gtk.HBox()
  iconSize = 24
  image = gtk.Image()
  image.set_from_pixbuf(pixbuf)
  
  tooltips.set_tip(row, helpText)
    
  label = gtk.Label()
  label.set_markup("<span size='x-large' weight='bold'>%s </span>" % (labelText))
  tempBox.pack_start(label, False, False, 0)
  row.pack_start(tempBox, False, False, 0)
  row.pack_start(image, False, False, 0)
  return row, label, image

class StatusHBox(gtk.HBox):
  """convienence class to map a name to a label and image- should maybe be a hbox"""
  def __init__(self, name, label, widget, image):
    gtk.HBox.__init__(self)
    self.rowName = name
    self.rowLabel = label
    self.rowImage = image
    self.widget = widget
  
  def reset_row_image(self):
    self.rowImage.set_from_pixbuf(Images.GREY_CIRCLE)
    
  def update_row_image(self, value):
    if value == True:
      self.rowImage.set_from_pixbuf(Images.GREEN_CIRCLE)
    elif value == False:
      self.rowImage.set_from_pixbuf(Images.RED_CIRCLE)
    elif value == None:
      self.rowImage.set_from_pixbuf(Images.YELLOW_CIRCLE)
    
class ServerStatusDisplay(GlobalEvents.GlobalEventMixin, GeneratorMixin.GeneratorMixin, ListenerMixin.ListenerMixin):
  def __init__(self, controller):
    GeneratorMixin.GeneratorMixin.__init__(self)
    ListenerMixin.ListenerMixin.__init__(self)
    
    self.controller = controller
    self.torApp = Tor.get()
    
    self._add_events("show_settings", "toggle_server", "show_setup", "done")
    ClientUtil.add_updater(self)

    self.bwGraph = BWGraph.BWGraph(BWHistory.remoteBandwidth, root=controller.serverWindow)
    self.bwGraph.container.set_size_request(400, 200)
    self.bwGraph.label = gtk.Label("Relay Traffic")
    self.statusRows = []
    
    self.statistics = {}
    self.torStatus = None
    self.rows = []  
    iconSize = 24
    tooltips = gtk.Tooltips()
    
    def make_row_box(name, labelText, childWidget):
      """packs a gui row with a label, childWidget, and an image.
      it then adds the row and a separator to a vbox which it returns 
      as well as the label it created as for use in homogenizing all the label widths"""
      
      image = gtk.Image()
      image.set_from_pixbuf(Images.GREY_CIRCLE)
      imageAlign = gtk.Alignment(0, 0, 0, 0)
      #push the widget over 
      imageAlign.set_padding(0, 0, 0, 10)
      imageAlign.add(image)
     
      textLabel = gtk.Label()
      textLabel.set_markup("<span size='large' weight='bold'>%s</span>" % (labelText))
      #stick the align on the left
      textLabel.set_alignment(0, 0.5)
      
      row = StatusHBox(name, textLabel, childWidget, image)
      self.statusRows.append(row)
      
      row.pack_start(imageAlign, False, False, 0)
      row.pack_start(textLabel, False, False, 0)
      row.pack_start(childWidget, False, False, 0)
      
      #pad the whole row
      rowAlign = gtk.Alignment(0, 0, 1, 1)
      rowAlign.set_padding(0, 0, 5, 5)
      rowAlign.add(row)
      
      sep = gtk.HSeparator()
      vBox = gtk.VBox()
      vBox.pack_start(rowAlign, False, False, 10)
      vBox.pack_start(sep, False, False, 0)
      
      return (vBox, row)
    
    creditsValueLabel = gtk.Label("0")
    creditsBox, self.creditsRow = make_row_box('credits', 'Credits: ', creditsValueLabel)
    
    statusValueLabel = gtk.Label("Unknown")
    statusBox, self.statusRow = make_row_box('status', 'Status: ', statusValueLabel)
    
    def on_toggle(widget):
      self._trigger_event("toggle_server")
    self.relayToggleButton = GTKUtils.make_image_button(_("Start"), on_toggle, "exit.png")
    self.relayToggleButton.set_size_request(75, -1)
    relayBox, self.relayRow = make_row_box('relay', "Relay:", self.relayToggleButton)
    
    textLabel = gtk.Label("Unknown")
    relayPortBox, self.tcpRelayPortRow = make_row_box('orPort', "TCP Relay Port:", textLabel)
    
    textLabel = gtk.Label("Unknown")
    udpRelayPortBox, self.udpRelayPortRow = make_row_box('dhtPort', "UDP Relay Port:", textLabel)
    
    textLabel = gtk.Label()
    textLabel.set_markup('<span size="large">     55555 is unreachable        </span>')
    dirPortBox, self.dirPortRow = make_row_box('dirPort', "Directory Port:", textLabel)
    
    labels = [box.rowLabel for box in \
              self.creditsRow, self.statusRow, self.relayRow, self.tcpRelayPortRow, self.udpRelayPortRow, self.dirPortRow]
    maxLabelWidth = 5 + max([label.size_request()[0] for label in labels])
    for label in labels:
      label.set_size_request(maxLabelWidth, -1)
      
    hideButton = gtk.Button("Hide")
    hideButton.connect("clicked", self._hide_cb)
    settingsButton = gtk.Button("Settings")
    def on_settings(widget):
      self._trigger_event("show_settings")
    settingsButton.connect("clicked", on_settings)
    buttonBox = gtk.HBox()
    buttonBox.pack_start(hideButton, False, False, 0)
    buttonBox.pack_end(settingsButton, False, False, 0)
    
    self.serverBox = gtk.VBox()
    for box in [relayBox, statusBox, relayPortBox, udpRelayPortBox, dirPortBox, creditsBox]:
      self.serverBox.pack_start(box, True, False, 0)
    self.serverBox.pack_start(buttonBox, True, False, 0)
    align = gtk.Alignment(0, 0, 0, 0)
    align.set_padding(0, 0, 5, 5)
    align.add(self.serverBox)
    
    serverFrame = GTKUtils.add_frame(align)
    makeAuroraFramesRounded = gtk.HBox()
    makeAuroraFramesRounded.set_size_request(0,0)
    serverFrame.set_label_widget(makeAuroraFramesRounded)
    
    self.notebook = ClosableTabNotebook.ClosableTabNotebook()
    self.notebook.show_display(self.bwGraph)
    
    notebookAlign = gtk.Alignment(0, 0, 1, 1)
    notebookAlign.set_padding(5, 5, 0, 5)
    notebookAlign.add(self.notebook)

    hbox = gtk.HBox()
    hbox.pack_start(serverFrame, False, False, 0)
    hbox.pack_start(notebookAlign, True, True, 0)
    hbox.show_all()
    
    self.catch_event("settings_changed")
    
#    self.container = hbox
    self.label = gtk.Label("Server Status %s" % (Globals.VERSION))
    
    vbox = gtk.VBox() 
    self.menuBar = BaseMenuBar.BaseMenuBar(self.controller)    
    vbox.pack_start(self.menuBar.create_menus(), False, False, 0)
    vbox.pack_start(hbox, True, True, 0)
    vbox.show_all()
    self.container = vbox
    
  def start(self):
    self.container.show()
    
  def stop(self):
    self.container.hide()

  def on_update(self):
    """updates the gui via pulling infos out of tor and the bank-
    slow, stupid, and easy"""
    #don't do updates if we arent visible
    if not GTKUtils.is_visible(self.container):
      return
    
    configuredAsRelay = self.torApp.is_server()
    if configuredAsRelay:
      self.relayRow.update_row_image(True)
    else:
      self.relayRow.reset_row_image()
    
    relayStatus, relayStateString = self.torApp.get_relay_status()
    if self.torApp.is_server():
      self.statusRow.update_row_image(relayStatus)
    else:
      self.statusRow.reset_row_image()
    self.statusRow.widget.set_markup('<span size="large">%s</span>' % (relayStateString))
    
    #update as appropriate for rows when we are trying to be a relay
    if configuredAsRelay:
      boolToStringMapping = {True: 'is reachable', False: 'is unreachable', None: 'testing...'}
      #do updates where we have the info
      relayPortsState = self.torApp.get_all_port_status()
      for row in self.statusRows:
        updateForGUIPort = row.rowName in relayPortsState
        if updateForGUIPort:
          port = relayPortsState[row.rowName]
          row.update_row_image(port[0])
          statusText = boolToStringMapping[port[0]]
          row.widget.set_markup('<span size="large">%s %s</span>' % (port[1], statusText))
    #else, null  everything out
    else:
      for row in [self.udpRelayPortRow, self.tcpRelayPortRow, self.dirPortRow, self.statusRow]:
        row.reset_row_image()
        row.widget.set_markup('<span size="large">offline</span>')
    
    #update the balance
    bank = Bank.get()
    if not bank:
      return
    credits = bank.get_expected_balance()
    if not credits:
      return
    self.creditsRow.widget.set_markup('<span size="large">%s  (%s)</span>'%\
                       (credits, Format.convert_to_gb(credits)))
    if credits > 200:
      creditState = True
    elif credits > 100:
      creditState = None
    else:
      creditState = False
    self.creditsRow.update_row_image(creditState)
    
  def on_settings_changed(self):
    if Tor.get().settings.beRelay:
      self.relayToggleButton.label.set_text(_("Stop"))
      self.relayToggleButton.image.set_from_pixbuf(Images.STOP_RELAY_PIXBUF)
    else:
      self.relayToggleButton.label.set_text(_("Start"))
      self.relayToggleButton.image.set_from_pixbuf(Images.START_RELAY_PIXBUF)
    
  def _hide_cb(self, widget=None):
    self._trigger_event("done")
      
