#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Window for controlling FireFox settings"""

import os

from twisted.internet import defer
import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from gui.gtk.window import TopWindow
from gui.gtk.widget import BaseMenuBar
from gui.gtk.utils import GTKUtils
from gui.gtk.utils import WrapLabel
from gui.gtk.utils import Images
from gui.gtk.dialog import BaseDialog
from gui.gtk.dialog import AnonymityLevelDialog
from gui.gtk.display import SettingsDisplay

PADDING = 10

class FirefoxMenuBar(BaseMenuBar.BaseMenuBar): pass

class FirefoxWindow(TopWindow.Window):
  def __init__(self, controller, app):
    TopWindow.Window.__init__(self, "Firefox",  app)
    self.catch_event("settings_changed")
    self.controller = controller
    self.anonymityDialog = None
    
  def create(self):
#    titleLabel = gtk.Label()
#    titleLabel.set_markup("<span size='x-large' weight='bold'>Firefox Controls</span>")
    descriptionLabel = WrapLabel.WrapLabel("")
    descriptionLabel.set_markup("<span size='x-large' weight='bold'>Important:  Flash is NOT supported yet!</span>\n\nAlso, DO NOT leave Firefox open if you are not using it!  Some website might keep sending traffic and cause you to lose credits over time\n\nThese will eventually be integrated into an extension inside of Firefox.")
    
    #make the controls:
    def make_button_row(labelText, callback, imageFile, descriptionText):
      button = GTKUtils.make_image_button(labelText, callback, imageFile, iconSize=32)
      button.set_size_request(200, -1)
      label = WrapLabel.WrapLabel(descriptionText)
      label.set_size_request(200, -1)
      box = gtk.HBox(spacing=3*PADDING)
      box.pack_start(button, False, False, 0)
      box.pack_start(label, False, False, 0)
      return (box, button)
    anonRow, self.anonButton = make_button_row("Anonymity Level", self._anonymity_cb, "identity.png", "Control how fast and anonymous your Firefox traffic will be.")
    circuitRow, circuitButton = make_button_row("New Circuit", self._new_circuit_cb, "network.png", "Get a new circuit (and IP address) for Firefox traffic.  The new circuit might be faster or slower.")
    ffRow, self.ffButton = make_button_row("Launch", self.toggle_firefox, "grey.png", "Start or stop our anonymous version of Firefox.")
    visibilityRow, self.visibilityButton = make_button_row("Hide", self._hide_cb, "hide.png", "Hide these controls.  They can always be opened from the system tray icon or file menu.")
    controlBox = gtk.VBox(spacing=PADDING)
    controlBox.pack_start(ffRow, False, False, 0)
    controlBox.pack_start(anonRow, False, False, 0)
    controlBox.pack_start(circuitRow, False, False, 0)
    controlBox.pack_start(visibilityRow, False, False, 0)
    controlBox = GTKUtils.add_padding(controlBox, PADDING)
    controlBox = GTKUtils.add_frame(controlBox, name="Controls")
    
    def on_launched(button):
      self.start()
      self.ffButton.label.set_text("Starting...")
      self.ffButton.image.set_from_pixbuf(Images.YELLOW_CIRCLE)
    self._start_listening_for_event("launched", self.app, on_launched)
    def on_started(button):
      self.ffButton.label.set_text("Stop")
      self.ffButton.image.set_from_pixbuf(Images.GREEN_CIRCLE)
    self._start_listening_for_event("started", self.app, on_started)
    def on_stopped(button):
      self.ffButton.label.set_text("Closing...")
      self.ffButton.image.set_from_pixbuf(Images.YELLOW_CIRCLE)
    self._start_listening_for_event("stopped", self.app, on_stopped)
    def on_finished(button):
      self.ffButton.label.set_text("Start")
      self.ffButton.image.set_from_pixbuf(Images.GREY_CIRCLE)
    self._start_listening_for_event("finished", self.app, on_finished)
    
    #pack everything into our window:
    box = gtk.VBox(spacing=PADDING)
#    box.pack_start(titleLabel, False, False, 0)
    box.pack_start(descriptionLabel, False, False, 0)
    box.pack_start(controlBox, False, False, 0)
    box.show()
    
    paddedBox = GTKUtils.add_padding(box, PADDING)
    paddedBox.show()
    frame = GTKUtils.add_frame(paddedBox)
    frame.show_all()
    
    vbox = gtk.VBox() 
    self.menuBar = FirefoxMenuBar(self.controller)    
    vbox.pack_start(self.menuBar.create_menus(), False, False, 0)
    vbox.pack_start(frame, True, True, 0)
    vbox.show_all()
    self.add(vbox)
    
  def make_popup_menu(self, newMenu):
    """creates a drop down menu on the system tray icon when right clicked"""
  
    submenu = gtk.Menu()
    if not self.app or not self.app.is_running():
      GTKUtils.append_menu_item(submenu, "Start Firefox", self.controller.toggle_firefox)
    else:
      GTKUtils.append_menu_item(submenu, "Show Firefox Controls", self._start_cb)
      GTKUtils.append_menu_item(submenu, "New identity", self._new_circuit_cb)
      GTKUtils.append_menu_item(submenu, "Change speed", self._anonymity_cb)
      GTKUtils.append_menu_item(submenu, "Stop Firefox", self.controller.toggle_firefox)
      
    image = gtk.Image()
    iconPath = os.path.join(self.app.appBasePath, self.app.name, "App", "AppInfo", "appicon.ico")
    if os.path.exists(iconPath):
      pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(iconPath, 24, 24)
      image.set_from_pixbuf(pixbuf)
    else:
      image.set_from_pixbuf(Images.GREY_CIRCLE)
      
    headerLabel = gtk.Label()
    headerLabel.set_markup("<span weight='bold'>%s</span>" % (self.app.name))
    box = gtk.HBox(spacing=10)
    box.pack_start(image, False, False, 0)
    box.pack_start(headerLabel, False, False, 0)
    header = gtk.MenuItem()
    header.add(box)
    header.set_submenu(submenu)
    header.show_all()
    
    newMenu.append(header)

    return submenu
  
  def _new_circuit_cb(self, widget=None):
    if self.app.is_running():
      self.app.make_new_identity()
    
  def _anonymity_cb(self, widget=None):
    self.anonymityDialog = AnonymityLevelDialog.AnonymityLevelDialog(self.app, False)
    
  def on_settings_changed(self):
    """changes the anonymity toggle button image/label to the current state"""
    pixbuf = AnonymityLevelDialog.get_path_length_image(self.app.pathLength, 32)
    self.anonButton.image.set_from_pixbuf(pixbuf)
    
  def toggle_firefox(self, widget=None):
    if self.app.is_running():
      self.app.stop()
    else:
      self.app.start()
    
  def _hide_cb(self, widget=None):
    self.stop()
    
