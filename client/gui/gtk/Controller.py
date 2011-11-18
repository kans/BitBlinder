#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Main GTK GUI class for Innominet"""

import time
import copy

import pygtk
pygtk.require('2.0')
import gtk
import gobject

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.system import System
from common.classes import Scheduler
from common.events import GlobalEvents, ListenerMixin
from common import Globals
from gui.gtk.utils import GTKUtils
from gui.gtk.utils import Images
from gui.gtk.dialog import PovertyDialog
from gui.gtk.dialog import MoneyLowDialog
from gui.gtk.dialog import WelcomeDialog
from gui.gtk.dialog import SettingsDialog
from gui.gtk.dialog import LoginDialog
from gui.gtk.dialog import UpdateDialog
from gui.gtk.dialog import ErrorReportDialog
from gui.gtk.widget import StatusIcon
from gui.gtk.window import ServerWindow
from gui.gtk.window import SocksClientWindow
from gui.gtk.window import BitTorrentWindow
from gui.gtk.window import FirefoxWindow
from core.bank import Bank
from core import ClientUtil
from core import Updater

from Applications import Tor
from BitTorrent import BitTorrentClient
from Applications import BitBlinder
from Applications import CoreSettings
from Applications import GlobalSettings

#Main GTK GUI class for the application
class Controller(GlobalEvents.GlobalEventMixin, ListenerMixin.ListenerMixin):
  """The GUI class is the controller for our application"""
  def __init__(self):
    ListenerMixin.ListenerMixin.__init__(self)
    
    #these are all the top-level windows that will ever be used.  This Controller is responsible for all of them.
    self.loginWindow = None
    self.btWindow = None
    self.firefoxWindow = None
    
    self.bankApp = None
    self.torApp = None
    self.bbApp = None
    self.btApp = None
    self.ffApp = None
    
    self.updateDialog = None
    self.lowMoneyDialog = None
    self.povertyDialog = None
    self.settingsDialog = None
    
    #listen for the events that we need to know about
    self.catch_event("no_credits")
    self.catch_event("shutdown")
    self.catch_event("new_args")
    
    #necessary for GTK to function properly:
    gobject.threads_init()
    
    #set the default image for the window
    defaultImage = ClientUtil.get_image_file(u"bb_logo.png")
    gtk.window_set_default_icon_from_file(defaultImage)
    
    #: windows which have been (de)iconified by left clickingon the status icon
    self.previouslyToggledWindows = []

    #sytem tray icon stuffs- handle when it is left clicked...
    statusIcon = ClientUtil.get_image_file("bb_favicon.ico")
    self.statusIcon = StatusIcon.StatusIcon(statusIcon)
    self.statusIcon.set_visible(False)
    self._start_listening_for_event("activated", self.statusIcon, self.on_status_icon_activated)
    self._start_listening_for_event("popup", self.statusIcon, self.on_status_icon_popup)
    
  #TODO:  handle this argument correctly
  def on_new_args(self, startingDir, options, args):
    if options.minimize:
      pass
    
  def _on_bank_launched(self, bankApp):
    try:
      self.loginWindow.start()
    except Exception, e:
      log_ex(e, "Failed to log in")
      self.show_msgbox("Failed to log in: %s\n\nTry removing your data directory:  %s" % (e, Globals.USER_DATA_DIR))
      
  def _on_bank_login(self, bankApp, text):
    self.statusIcon.set_visible(True)
    
  def _check_welcome_dialog(self, triggeringApp):
    if not self.torApp.is_ready() or not self.bankApp.is_ready():
      return
    if not self.torApp.settings.promptedAboutRelay:
      self.welcomeDialog = WelcomeDialog.WelcomeDialog(self)
      self.torApp.settings.promptedAboutRelay = True
      self.torApp.settings.save()
      #TODO:  remove this hack--need to schedule a _raise later so that the window doesnt get hidden by other stuff that happens when Tor launches
      def raise_later():
        if self.welcomeDialog:
          self.welcomeDialog.raise_()
      Scheduler.schedule_once(2.0, raise_later)
      
  def start_server_setup(self):
    self.serverWindow.start()
    
  def show_socks_window(self, widget=None):
    self.socksClientWindow.start()
    
  def show_firefox_controls(self, widget=None):
    self.firefoxWindow.start()
    
  def on_applications_created(self, bankApp, torApp, bbApp, btApp, ffApp):
    """Create all of the top level windows"""
    self.bankApp = bankApp
    self.torApp = torApp
    self.bbApp = bbApp
    self.btApp = btApp
    self.ffApp = ffApp
    
    #LoginWindow
    self.loginWindow = LoginDialog.LoginDialog(bankApp)
    self._start_listening_for_event("launched", bankApp, self._on_bank_launched)
    self._start_listening_for_event("login_success", bankApp, self._on_bank_login)
    
    #show a "would you like to be a server window" when Tor finishes launching for the first time (and you've logged in)
    self._start_listening_for_event("started", torApp, self._check_welcome_dialog)
    self._start_listening_for_event("started", bankApp, self._check_welcome_dialog)
    
    #create the windows
    self.btWindow = BitTorrentWindow.BitTorrentWindow(self, btApp)
    self.serverWindow = ServerWindow.ServerWindow(self)
    if self.ffApp:
      self.firefoxWindow = FirefoxWindow.FirefoxWindow(self, ffApp)
    self.socksClientWindow = SocksClientWindow.SocksClientWindow(self, bbApp)
    
    #populate the windows:
    self.btWindow.create()
    self.serverWindow.create()
    if self.ffApp:
      self.firefoxWindow.create()
    self.socksClientWindow.create()
    
    btApp.set_display(self.btWindow)
  
  def on_status_icon_activated(self, statusIcon):
    """called when the user left clicks the status icon-
    closes all open windows, or restores previously closed windows, or
    just opens the bt window"""
    
    #if any windows are open, close them
    openWindows = []
    #all windows
    windows = [self.btWindow, self.firefoxWindow, self.socksClientWindow, self.serverWindow]
    if self.ffApp:
      windows.append(self.firefoxWindow)
    for window in windows:
      if window and window.is_visible():
        openWindows.append(window)
        
    if openWindows:
      #a window(s) that has been closed through left clicking the status icon
      self.previouslyToggledWindows = []
      for window in openWindows:
        window.toggle_window_state()
        self.previouslyToggledWindows.append(window)
    #no window is open, so open previously closed ones if p[ossible
    elif self.previouslyToggledWindows:
      for window in self.previouslyToggledWindows:
        window.toggle_window_state()
    #else, open BT
    else:
      #show bt window, make sure its running of course
      if self.btWindow.app.is_running():
        self.btWindow.toggle_window_state()
      else:
        self.btWindow.app.start()
    return
    
  def on_status_icon_popup(self, statusIcon, newMenu,  submenus):
    """retrieves the correct menu items from the respective apps"""
    socksMenu = self.socksClientWindow.make_popup_menu(newMenu)
    submenu = self.serverWindow.make_popup_menu(newMenu)
    submenus.append(submenu)
    #don't make this for linux users who don't have a portable ff
    if self.ffApp:
      submenu = self.firefoxWindow.make_popup_menu(newMenu)
      submenus.append(submenu)
    submenu = self.btWindow.make_popup_menu(newMenu)
    if submenu:
      submenus.append(submenu)
    
    menuItem = GTKUtils.make_menu_item_with_picture("Quit", "exit.png")
    #menuItem.set_submenu(submenu)
    menuItem.connect("activate", self.quit_cb)
    menuItem.show_all()
    
    newMenu.append(menuItem)

    return submenu
    
  def on_shutdown(self, *args):
    """delete the statusIcon, hide the window, then deletes that too"""
    if self.statusIcon:
      del self.statusIcon
    self.statusIcon = None
    
  def show_msgbox(self, text, title="Notice", cb=None, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK), 
                  args=None, width=200, link=None, makeSafe=False, root=None):
    """Launches a message box and keeps the main thread going.  cb will be called
    when the messagebox is finished."""
    if not args:
      args = []
    log_msg(text, 3)
    dia = gtk.Dialog(title,
      root,
      0,
      buttons)
    #ensure that the dialog is modal if the parent window is, otherwise it's not selectable!
    if root and root.get_modal():
      dia.set_modal(True)
    label = gtk.Label("")
    if makeSafe:
      label.set_text(text)
    else:
      label.set_markup(text)
    label.set_selectable(True)
    label.set_size_request(width, -1)
    label.set_line_wrap(True)
    paddedLabel = GTKUtils.add_padding(label, 5)
    dia.vbox.pack_start(paddedLabel, True, True, 10)
    if link:
      dia.vbox.pack_start(link, True, True, 10)
    dia.show_all()
    #have to do a callback if you want to see the result of the dialog:
    def on_response(dialog, response_id, cb):
      if cb:
        cb(dialog, response_id, *args)
      dialog.destroy()
    #connect the handler:
    dia.connect("response", on_response, cb)
    return dia
    
  def show_preference_prompt(self, text, title, callback, prefName, defaultResponse=True):
    """A shortcut for dialogs where we say 'Are you sure you want to X?'"""
    #return immediately if there is a saved setting
    alwaysPrompt = getattr(GlobalSettings.get(), prefName, True)
    if alwaysPrompt == False:
      callback(defaultResponse)
      return
    
    #otherwise, define the callback for when the user is finished with the prompt
    def on_response(dialog, responseId, callback=callback):
      response = False
      if responseId == gtk.RESPONSE_YES:
        response = True
      callback(response)
      alwaysPrompt = dialog.checkbox.get_active()
      if alwaysPrompt == False:
        setattr(GlobalSettings.get(), prefName, alwaysPrompt)
        GlobalSettings.get().save()
        
    #then make the dialog
    dia = self.show_msgbox(text, title, on_response, (gtk.STOCK_YES, gtk.RESPONSE_YES, gtk.STOCK_NO, gtk.RESPONSE_NO))
    dia.checkbox = gtk.CheckButton("Always ask?")
    dia.checkbox.set_active(True)
    dia.checkbox.show()
    dia.vbox.pack_end(dia.checkbox)
    dia.set_modal(True)
    
  def prompt_about_port(self, portNum, successFunc):
    pid = System.get_pid_from_port(portNum)
    if pid <= 0:
      successFunc()
      return
    programs = System.get_process_ids()
    programName = "None"
    for p in programs:
      if p[1] == pid:
        programName = p[0]
        break
    def response_cb(dialog, response, portNum=portNum, successFunc=successFunc, programName=programName):
      pid = System.get_pid_from_port(portNum)
      if pid <= 0:
        successFunc()
        return
      if response == 0:
        System.kill_process(pid)
        startTime = time.time()
        while time.time() < startTime + 2:
          pid = System.get_pid_from_port(portNum)
          if pid <= 0:
            successFunc()
            return
          time.sleep(0.1)
        def try_again(dialog, response, portNum=portNum, successFunc=successFunc):
          self.prompt_about_port(portNum, successFunc)
        self.show_msgbox("Failed to kill program!  Try killing process yourself.  pid=%s, name=%s" % (pid, programName), cb=try_again)
      elif response == 1:
        self.prompt_about_port(portNum, successFunc)
    self.show_msgbox("Port %s is in use by another program (%s).  BitBlinder needs this port to run.  \n\nWould you like to kill that program or retry the port?" % (portNum, programName), "Port Conflict!", response_cb, buttons=("Kill", 0, "Retry", 1))
    
  def on_no_credits(self):
    bitBlinder = BitBlinder.get()
    showDialog = bitBlinder.is_running() and bitBlinder.settings.alwaysShowPovertyDialog
    if showDialog:
      if not self.povertyDialog:
        self.povertyDialog = PovertyDialog.PovertyDialog(self)
      self.povertyDialog.show()
      
  def on_low_credits(self):
    self.lowMoneyDialog = MoneyLowDialog.MoneyLowDialog(self)

  def update_prompt(self, newVersion, prompt, cb):
    if not self.updateDialog:
      self.updateDialog = UpdateDialog.UpdateDialog(newVersion, prompt, cb)
    else:
      self.updateDialog.dia.show()
    
  def show_settings_cb(self, widget=None):
    #TODO: global and core settings creating and manipulating fake Application ojects, and settings are currently generally stupid.  Change to a global settings obj
    apps = {}
    #create a fake Application wrapper for global settings: 
    globalSettingsObj = GlobalSettings.get()
    apps[globalSettingsObj.settingsName] = globalSettingsObj.app
    coreSettingsObj = CoreSettings.get()
    apps[coreSettingsObj.settingsName] = coreSettingsObj.app
    
    realApplications = [self.torApp, self.btApp]
#    #currently no ff settings... really should use introspection, but everything is about to change
#    if System.IS_WINDOWS:
#      realApplications.append(self.ffApp)
    for app in realApplications:
      apps[app.get_settings_name()] = app
    self.show_settings(apps)
    
  def quit_cb(self, widget, event=None, Data=None):
    #see if any components are even running
    runningPrograms = []
    if self.btApp.is_running():
      runningPrograms.append("BitTorrent")
    if self.ffApp and self.ffApp.is_running():
      runningPrograms.append("Firefox")
    if self.torApp.is_server():
      runningPrograms.append("your relay")
    #if not, just quit with no prompt
    if len(runningPrograms) <= 0:
      self._do_quit()
      return
      
    #formatting the warning message:
    if len(runningPrograms) > 1:
      runningPrograms[-1] = "and " + runningPrograms[-1]
    programList = ", ".join(runningPrograms)
    
    #prompt the user
    def callback(response):
      if response == True:
        self._do_quit()
    self.show_preference_prompt("This will stop %s.  Are you sure you want to quit?" % (programList), "Quit?", callback, "promptAboutQuit")
      
  def _do_quit(self):
    if self.firefoxWindow:
      self.firefoxWindow.stop()
    self.serverWindow.stop()
    self.socksClientWindow.stop()
    d = self.bbApp.stop()
    d.addCallback(self.quit_done)
    d.addErrback(self.quit_failed)
    
  def quit_failed(self, result):
    log_ex(result, "Failed while quitting BitBlinder")
    self.quit_done(None)
    
  def quit_done(self, result):
    GlobalEvents.throw_event("quit_signal")

  def launch_cb(self, widget, appName):
    if self.bbApp.applications.has_key(appName):
      self.bbApp.applications[appName].start()
    else:
      self.show_msgbox("Please wait until BitBlinder finishes starting up.")
      
  def launch_bit_twister(self, widget=None):
    """brings up the BT window"""
    #note, this is currently a bit stupid as we have to wait for tor, etc
    BitTorrentClient.get().start()
    
  def launch_ffportable(self, widget=None):
    #note, this is currently a bit stupid as we have to wait for tor, etc
    self.bbApp.applications["FirefoxPortable"].start()
      
  def show_settings(self, apps=None):
    if not self.bbApp:
      self.show_msgbox("Please log in before changing settings.")
    if not self.settingsDialog:
      self.settingsDialog = SettingsDialog.SettingsDialog(apps, self.btApp.display)
    else:
      self.settingsDialog.show()
    self.settingsDialog.set_app(None)
    
  def update_check(self, widget=None, event=None):
    def success_cb(data, httpDownloadInstance):
      if not Updater.get().update_request_done(data, httpDownloadInstance):
        self.show_msgbox("You are using the latest available packaged version.")
      else:
        self.show_msgbox("BitBlinder is downloading a new version.  It will prompt you when the update is ready.")
    def failure_cb(failure, httpDownloadInstance):
      log_ex(failure, "Failed to manually check for update")
      self.show_msgbox("A server is temporarily offline; check back later.")
    Updater.get().check_for_updates(success_cb=success_cb, failure_cb=failure_cb)
    
  def show_trac(self, widget):
    self.submitErrorDialog = ErrorReportDialog.ErrorReportDialog()
    
  def toggle_relay(self, widget=None):
    if not self.torApp.is_server():
      self.serverWindow.start()
    else:
      self.serverWindow.stop()
      self.torApp.stop_server()
    
  def toggle_firefox(self, widget=None):
    if not self.ffApp.is_running():
      self.firefoxWindow.start()
    else:
      self.firefoxWindow.stop()
    self.firefoxWindow.toggle_firefox()
    
  def toggle_bittorrent(self, *args):
    if not self.btApp.is_running():
      self.btWindow.start()
      self.btApp.start()
    else:
      self.btWindow.stop()
      self.btApp.stop()
    
