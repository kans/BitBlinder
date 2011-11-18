#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Base class for all menu bars.  Handles common menu entries."""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.events import GlobalEvents
from common.events import ListenerMixin
from common.classes import Profiler
from core import ProgramState
from gui.gtk.utils import GTKUtils
from gui.utils import Strings
from Applications import Tor
from BitTorrent import BitTorrentClient
from Applications import FirefoxPortable

class BaseMenuBar(ListenerMixin.ListenerMixin):
  def __init__(self, controller):
    ListenerMixin.ListenerMixin.__init__(self)
    self.controller = controller
    
  def create_menus(self):
    """creates the menu of course- could use some cleaning"""        
    # Init the menu-widget, and remember -- never
    # show() the menu widget!!
    
    self.create_file_menu()
    self.create_debug_menu()
    self.create_view_menu()
    self.create_help_menu()
    
    self.create_menu_bar()
    return self.menuBar
    
  def create_file_menu(self):
    self.fileMenu = gtk.Menu()
    self.fileMenuRoot = gtk.MenuItem("File")
    
    def make_toggle_app_entry(app, is_running_func, toggle_func, name, stopEvent, startEvent):
      menuItem = GTKUtils.append_menu_item(self.fileMenu, " ", toggle_func)
      def on_toggled(app):
        if is_running_func():
          menuItem.child.set_text("Stop %s" % (name))
        else:
          menuItem.child.set_text("Start %s" % (name))
      on_toggled(app)
      self._start_listening_for_event(startEvent, app, on_toggled)
      self._start_listening_for_event(stopEvent, app, on_toggled)
      return menuItem
      
    self.serverMenuItem = make_toggle_app_entry(Tor.get(), Tor.get().is_server, 
      self.controller.toggle_relay, "Relay", "server_stopped", "server_started")
    self.bittorrentMenuItem = make_toggle_app_entry(BitTorrentClient.get(), BitTorrentClient.get().is_running, 
      self.controller.toggle_bittorrent, "BitTorrent", "stopped", "started")
    firefox = FirefoxPortable.get()
    if firefox:
      self.firefoxMenuItem = make_toggle_app_entry(firefox, firefox.is_running, 
        self.controller.toggle_firefox, "Browser", "stopped", "started")
    
    self.fileMenu.append(gtk.SeparatorMenuItem())
    GTKUtils.append_menu_item(self.fileMenu, "Update", self.controller.update_check)
    GTKUtils.append_menu_item(self.fileMenu, "Quit", self.controller.quit_cb)
    self.fileMenuRoot.set_submenu(self.fileMenu)
    self.fileMenuRoot.show()
    return self.fileMenu
    
  def create_debug_menu(self):
    #Debug Menu
    self.debugMenu = gtk.Menu()
    self.profileMenuItem = GTKUtils.append_menu_item(self.debugMenu, "Start Profiler", self.toggle_profiler)
    def on_profiler_started(profiler):
      self.profileMenuItem.child.set_text("Stop Profiler")
    self._start_listening_for_event("started", Profiler.get(), on_profiler_started)
    def on_profiler_stopped(profiler):
      self.profileMenuItem.child.set_text("Start Profiler")
    self._start_listening_for_event("stopped", Profiler.get(), on_profiler_stopped)
   
    self.debugMenuRoot = gtk.MenuItem("Debug")
    self.debugMenuRoot.set_submenu(self.debugMenu)
    self.debugMenuRoot.show()
    return self.debugMenu
    
  def create_view_menu(self):
    self.viewMenu = gtk.Menu()
    self.viewMenuRoot = gtk.MenuItem("View")
    
    GTKUtils.append_menu_item(self.viewMenu, "Help", self.show_help)
    self.viewMenu.append(gtk.SeparatorMenuItem())
    
    def make_toggle_window_entry(window, name):
      menuItem = GTKUtils.append_menu_item(self.viewMenu, " ", window.toggle_window_state)
      def on_toggled(window):
        if window.is_visible():
          menuItem.child.set_text("Hide %s" % (name))
        else:
          menuItem.child.set_text("Show %s" % (name))
      on_toggled(window)
      self._start_listening_for_event("shown", window, on_toggled)
      self._start_listening_for_event("hidden", window, on_toggled)
      return menuItem
      
    make_toggle_window_entry(self.controller.btWindow, "BitTorrent")
    firefox = FirefoxPortable.get()
    if firefox:
      make_toggle_window_entry(self.controller.firefoxWindow, "Firefox")
    make_toggle_window_entry(self.controller.serverWindow, "Server")
    make_toggle_window_entry(self.controller.socksClientWindow, "SOCKS Clients")
    
    self.viewMenu.append(gtk.SeparatorMenuItem())
    GTKUtils.append_menu_item(self.viewMenu, "Preferences", self.controller.show_settings_cb)
    self.viewMenuRoot.set_submenu(self.viewMenu)
    self.viewMenuRoot.show()
    return self.viewMenu
    
  def create_help_menu(self):
    self.helpMenu = gtk.Menu()
    self.helpMenuRoot = gtk.MenuItem("Help")
    GTKUtils.append_menu_item(self.helpMenu, "Instructions", self.show_help)
    GTKUtils.append_menu_item(self.helpMenu, "Read Online Help...", self.show_website)
    GTKUtils.append_menu_item(self.helpMenu, "Visit Forums...", self.show_forums)
    GTKUtils.append_menu_item(self.helpMenu, "Report an Issue...", self.controller.show_trac)
    GTKUtils.append_menu_item(self.helpMenu, "About", self.show_about)
    self.helpMenuRoot.set_submenu(self.helpMenu)
    self.helpMenuRoot.show()
    return self.helpMenu
    
  def create_menu_bar(self):
    # Create a menu-bar to hold the menus and add it to our main window
    self.menuBar = gtk.MenuBar()
    self.menuBar.show()
    self.menuBar.append(self.fileMenuRoot)
    self.menuBar.append(self.viewMenuRoot)
    self.menuBar.append(self.debugMenuRoot)
    self.menuBar.append(self.helpMenuRoot)
    return self.menuBar
    
  def toggle_profiler(self, widget=None):
    if Profiler.get().isProfiling:
      Profiler.get().stop()
    else:
      Profiler.get().start()

  def show_about(self, widget):
    self.controller.show_msgbox(Strings.ABOUT_TEXT, title="About")
    
  #TODO:  this needs to have links that go to the website with appropriate guides
  #this should be more prominent, and more useful, since we need to do a significant amount of user education
  def show_help(self, widget):
    self.controller.show_msgbox("See our website... and visit the chatroom to let us know if you have questions!", title="Help", width=400)
    
  def show_website(self, widget):
    GlobalEvents.throw_event("open_web_page_signal", '%s/learn/about/' % (ProgramState.Conf.BASE_HTTP), True)
    
  def show_forums(self, widget):
    GlobalEvents.throw_event("open_web_page_signal", '%s/forum/' % (ProgramState.Conf.BASE_HTTP), True)
    
