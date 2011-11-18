#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Offers a console gui."""

import time
import sys
import atexit
import os
import webbrowser
import getpass
import Queue
from twisted.internet import threads

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.system import System
from common import Globals
from common.classes import Scheduler
from common.events import GlobalEvents
from common.events import ListenerMixin
from gui.utils import Strings
from core import HTTPClient
from core import ProgramState
from core.bank import Bank
from Applications import GlobalSettings

class Controller(GlobalEvents.GlobalEventMixin, ListenerMixin.ListenerMixin):
  def __init__(self):
    ListenerMixin.ListenerMixin.__init__(self)
    self.catch_event("no_credits")
    self.catch_event("some_credits")
    
  def on_applications_created(self, bankApp, torApp, bbApp, btApp, ffApp):
    #make the displays:
    bbApp.display = self
    btApp.display = self

    self.bankApp = bankApp
    self.torApp = torApp
    self.bbApp = bbApp
    self.btApp = btApp
    self.ffApp = ffApp
    
    self._start_listening_for_event("launched", bankApp, self.do_verification_prompt)
    self._start_listening_for_event("login_success", bankApp, self.on_login_success)
    self._start_listening_for_event("login_failure", bankApp, self.on_login_failure)
    
  def on_no_credits(self):
    self.show_msgbox("BitBlinder ran out of credits.  You will earn credits slowly over time, or faster if you have a properly working server.")

  def on_some_credits(self):
    self.show_msgbox("BitBlinder accumulated enough credits to start again.")

  def print_wrapper(self, *args):
    for arg in args:
      print arg[0]
    
  def show_about(self, widget):
    log_msg(Strings.ABOUT_TEXT, 0)
    
  def show_website(self, widget):
    log_msg('go to %s/' % (ProgramState.Conf.BASE_HTTP), 3)
  
  def on_tor_ready(self):
    log_msg("Connected to Tor", 3)

  def on_tor_done(self):
    log_msg("Stopping", 3)
    
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
    #this has to go in the console as it isn't seen otherwise
    self.shutdown_func = ""
    msg = "Port %s is taken by program %s (pid=%s).  Please kill the program or otherwise free the port and restart BitBlinder."% (portNum, programName, pid)
    log_msg(msg, 0)
    atexit.register(self.print_wrapper, msg)
    GlobalEvents.throw_event("quit_signal")
  
  #Launches a message box and keeps the main thread going.  cb will be called
  #when the messagebox is finished.
  def show_msgbox(self, text, title="Notice", cb=None, buttons=None, args=None, width=200, link=None):
    text = "%s:  %s" % (title, text)
    if buttons != None:
      text += "\nDefaulted to %s" % (buttons[0])
    if link != None:
      text += "\nLink: %s" % (link)
    log_msg(text, 2)
    if cb:
      if not args:
        args = []
      args.insert(0, 0)
      args.insert(0, None)
      Scheduler.schedule_once(0.1, cb, *args)
      
  def hide(self):
    pass
  
  def hide_tracker_shutdown_prompt(self):
    log_msg("Exit prompt was hidden.", 4)
    
  def do_verification_prompt(self, bankApp):
    #load a global config that said whether to store the last user that logged in (and his password)
    settings = GlobalSettings.load()
      
    #just directly login:
    self.username = str(settings.username)
    self.password = str(settings.password)
    self.savePass = settings.save_password
    while not self.username or not self.password:
      self.username = str(raw_input('Enter your username: '))
      self.password = str(raw_input('Enter your password: '))
      shouldSave = str(raw_input('Should save password? (yes/no) '))
      self.savePass = shouldSave.lower() in ("yes", "y")
      
    #just directly login:
    Bank.get().login(self.username, self.password)
    
  def status_update(self, *args, **kwargs):
    pass
    
  def new_tube_socks(self, stats):
    pass
    
  def tube_socks_update(self, stats):
    pass
      
  def tube_socks_died(self, app):
    pass
    
  def on_low_credits(self):
    log_msg("You only have %s credits remaining.  Make sure that your ports are forwarded and you are acting as a relay, otherwise you will run out!" % (Bank.get().get_expected_balance()))
  
  def on_login_success(self, bankApp, loginMessage=None):
    log_msg("Bank login succeeded!\nBank Welcome Message:  %s" % (loginMessage), 2)
    #save all this information to the settings files if necessary:
    settings = GlobalSettings.get()
    settings.save_password = self.savePass
    if not settings.save_password:
      self.username = ""
      self.password = ""
    settings.username = self.username
    settings.password = self.password
    settings.save()

  def on_login_failure(self, bankApp, err, text=None):
    log_msg("Bank login failed:  %s\n%s" % (err, text), 1)
  
  def update_prompt(self, newVersion, prompt, cb):
    log_msg("A new version is available:  %s.  Go to %s/download/ to download it!" % (newVersion, ProgramState.Conf.BASE_HTTP), 4)
    
  def on_server_status_update(self, status, address=None, reason=None):
    log_msg("server status:  %s %s %s" % (status, address, reason), 2)
    
  def on_new_external_address(self, address, method):
    log_msg("external ip address:  %s %s" % (address, method), 3)
          
  def message(self, s):
    log_msg( "### "+s , 2)

  def exception(self, s): 
    raise s
  
  def is_visible(self):
    return True
    
  def do_priority_prompt(self, *args, **kwargs):
    pass
    
  def start(self):
    pass
    
  def display(self, data):
    pass
    
  def stop(self):
    pass
    
  def freeze(self):
    pass
    
  def unfreeze(self):
    pass
  
  def set_priority_box(self):
    pass
  
  def set_peer_box(self):
    pass

  def toggle_visibility(self):
    pass

  def show_tracker_shutdown_prompt(self, *args, **kwargs):
    pass
    
