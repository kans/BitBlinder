#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Window interacting with the Tor relay"""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.display import ServerSetupDisplay
from gui.gtk.display import ServerStatusDisplay
from gui.gtk.display import ExitTrafficDisplay
from gui.gtk.dialog import ServerSettingsDialog
from gui.gtk.utils import Images
from gui.gtk.utils import GTKUtils
from gui.gtk.window import TopWindow
from Applications import Tor

class ServerWindow(TopWindow.Window):
  def __init__(self, controller):
    TopWindow.Window.__init__(self, "Server Setup",  None)
    self.controller = controller
    self.currentDisplay = None
    self.settingDialog = None
    self.torApp = Tor.get()
    
  def create(self):
    #create each of the 3 displays
    self.setupDisplay = ServerSetupDisplay.ServerSetupDisplay(self.controller)
    self.statusDisplay = ServerStatusDisplay.ServerStatusDisplay(self.controller)
    self.exitDisplay = ExitTrafficDisplay.ExitTrafficDisplay()
    
    #respond to events from the setup display:
    def on_resized(display):
      self.refit()
    self._start_listening_for_event("size_changed", self.setupDisplay, on_resized)
    self._start_listening_for_event("success", self.setupDisplay, self._on_setup_success)
    self._start_listening_for_event("failure", self.setupDisplay, self._on_setup_failure)
    
    #respond to events from the exit traffic settings display:
    def on_success(display):
      self._use_display(self.statusDisplay)
    self._start_listening_for_event("done", self.exitDisplay, on_success)
    
    #respond to events from the status display:
    def on_show_setup(display):
      self._use_display(self.setupDisplay)
    self._start_listening_for_event("show_setup", self.statusDisplay, on_show_setup)
    def on_show_settings(display):
      self.show_server_settings()
    self._start_listening_for_event("show_settings", self.statusDisplay, on_show_settings)
    def on_toggle_server(display):
      self.toggle_server()
    self._start_listening_for_event("toggle_server", self.statusDisplay, on_toggle_server)
    def on_done(display):
      self.hide()
    self._start_listening_for_event("done", self.statusDisplay, on_done)
    
  def start(self):
    self.torApp.start_server()
    #decide which to display--if the server has never been successfully run, do setup, 
    if not self._was_server_setup_completed():
      self._use_display(self.setupDisplay)
    #otherwise do status
    else:
      self._use_display(self.statusDisplay)
    TopWindow.Window.start(self)
    
  def _was_server_setup_completed(self):
    return self.torApp.settings.completedServerSetup
    
  def _on_setup_success(self, display):
    #have we set up successfully before?  If so, show the status
    if self._was_server_setup_completed():
      self._use_display(self.statusDisplay)
    #otherwise, show the exit traffic selection
    else:
      self._use_display(self.exitDisplay)
    
  def _on_setup_failure(self, display=None):
    def callback(dialog, responseId):
      if responseId == gtk.RESPONSE_YES:
        self.torApp.stop_server()
        self.stop()
    self.controller.show_msgbox("Are you sure you want to stop being a server?", 
                                                title="Warning", cb=callback, 
                                                buttons=(gtk.STOCK_YES, gtk.RESPONSE_YES, gtk.STOCK_NO, gtk.RESPONSE_NO), 
                                                root=self)
    
  def _use_display(self, display):
    #remove the old display
    if self.currentDisplay:
      self.currentDisplay.stop()
      self.remove(self.currentDisplay.container)
    
    #set the new display
    self.currentDisplay = display
    self.add(self.currentDisplay.container)
    self.set_title(self.currentDisplay.label.get_text())
    self.currentDisplay.start()
    self.refit()
      
  def make_popup_menu(self, newMenu):
    """creates a drop down menu on the system tray icon when right clicked hopefully"""
    #make appropriate submenu
    submenu = gtk.Menu()
    if not self.torApp.is_running() or not self.torApp.is_server():
      GTKUtils.append_menu_item(submenu, "Start Relay", self.controller.toggle_relay)
    else:
      GTKUtils.append_menu_item(submenu, "Show Server Window", self._start_cb)
      GTKUtils.append_menu_item(submenu, "Settings", self.show_server_settings)
      GTKUtils.append_menu_item(submenu, "Stop Relay", self.controller.toggle_relay)
    
    menuItem = GTKUtils.make_menu_item_with_picture("Relay",  "network2.png")
    menuItem.set_submenu(submenu)
    menuItem.show_all()
    
    newMenu.append(menuItem)
    return submenu
    
  def toggle_server(self, widget=None):
    if not self.torApp.is_server():
      self.start()
    else:
      self.torApp.stop_server()
    
  def show_server_settings(self, widget=None):
    if not self.settingDialog:
      def cb(result):
        self.settingDialog = None
        if result not in (True, False):
          log_ex(result, "Server settings dialog failed")
        return result
      self.settingDialog = ServerSettingsDialog.ServerSettingsDialog()
      self.settingDialog.dialogDeferred.addCallback(cb)
      self.settingDialog.dialogDeferred.addErrback(cb)
    self.settingDialog.show()
    return self.settingDialog.dialogDeferred
