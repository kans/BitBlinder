#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Prompt the user for username and password so she can login"""

import time
import sys
import os
import gtk
from twisted.python.failure import Failure
from twisted.internet.error import ConnectionLost, ConnectionDone

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Basic
from common.Errors import BadLoginPasswordError
from common.events import GlobalEvents
from common.events import ListenerMixin
from core import ProgramState
from core.bank import Bank
from gui.gtk.utils import GTKUtils
from gui.gtk.utils import WrapLabel
from gui import GUIController
from Applications import GlobalSettings

class LoginDialog(GlobalEvents.GlobalEventMixin, ListenerMixin.ListenerMixin):
  def __init__(self, bankApp):
    ListenerMixin.ListenerMixin.__init__(self)
    self.username = None
    self.password = None
    
    self._start_listening_for_event("login_success", bankApp, self.on_login_success)
    self._start_listening_for_event("login_failure", bankApp, self.on_login_failure)

    dia = gtk.Dialog("Login", None, 0, None)

    dia.connect("destroy", self.destroy_cb)
#    dia.connect("expose_event", self.expose_cb)
    
    self.started = False
    self.succeeded = False
    
    self.loginButton = dia.add_button("Login", gtk.RESPONSE_OK)
    self.quitButton = dia.add_button("Quit", gtk.RESPONSE_CANCEL)
    
    #username field
    self.usernameLabel = gtk.Label("Username")
    self.nameEntry = gtk.Entry()
    self.nameEntry.set_max_length(50)
    self.nameEntry.connect("activate", self.enter_callback)
    
    #password field
    self.pwLabel = gtk.Label("Password")
    self.pwEntry = gtk.Entry()
    self.pwEntry.set_max_length(50)
    #so people cant see our password:
    self.pwEntry.set_visibility(False)
    self.pwEntry.connect("activate", self.enter_callback)
    
    resetPasswordLink = GTKUtils.make_html_link("Forgot your password?", "%s/accounts/resetPassword/" % (ProgramState.Conf.BASE_HTTP))
    makeAccountLink = GTKUtils.make_html_link("Need an account?", "%s/accounts/register/" % (ProgramState.Conf.BASE_HTTP))
    
    #put them in a nice little table
    table = gtk.Table(4, 2, True)
    table.attach(self.usernameLabel, 0, 1, 0, 1)
    table.attach(self.nameEntry, 1, 2, 0, 1)
    table.attach(makeAccountLink, 1, 2, 1, 2)
    table.attach(self.pwLabel, 0, 1, 2, 3)
    table.attach(self.pwEntry, 1, 2, 2, 3)
    table.attach(resetPasswordLink, 1, 2, 3, 4)
    
    self.savePassCheck = gtk.CheckButton("Remember Username/Password")
    
    #A text entry telling the user what to do:
    self.label = WrapLabel.WrapLabel()
    self.label.set_markup("<span weight='bold'>Use your account name and password from the BitBlinder website!</span>")
    align = gtk.Alignment(xalign=0.5, yalign=0.5, xscale=1.0, yscale=0.0)
    align.add(self.label)
    align.set_padding(10, 10, 5, 5)

    dia.vbox.pack_start(GTKUtils.add_frame(align), True, True, 10)
    dia.vbox.pack_start(table, True, True, 0)
    dia.vbox.pack_start(self.savePassCheck, True, True, 10)
    
    #load a global config that said whether to store the last user that logged in (and his password)
    settings = GlobalSettings.load()
    
    self.nameEntry.set_text(settings.username)
    self.pwEntry.set_text(settings.password)
    self.savePassCheck.set_active(settings.save_password)

    #connect the handler:
    dia.connect("response", self.on_response)
    self.dia = dia
    
  def start(self):
    self.dia.show_all()
    self.nameEntry.grab_focus()
    if not self.started:
      self.started = True
      #just log in right away if we're saving the password and username anyway:
      if GlobalSettings.get().save_password:
        self.on_response(self.dia, gtk.RESPONSE_OK)
    
  def enter_callback(self, widget):
    self.on_response(self.dia, gtk.RESPONSE_OK)
    
#  def expose_cb(self, widget, event=None):
#    if not self.started:
#      self.started = True
#      #just log in right away if we're saving the password and username anyway:
#      if GlobalSettings.get().save_password:
#        self.on_response(self.dia, gtk.RESPONSE_OK)
    
  def _do_quit(self):
    self.dia.hide()
    if Bank.get() and Bank.get().is_starting():
      Bank.get().stop()
    GlobalEvents.throw_event("quit_signal")
    #intentionally called twice, we dont want to be waiting around for bittorrent tracker shutdown if we havent even logged in
    GlobalEvents.throw_event("quit_signal")
    
  #handle the result of the dialog:
  def on_response(self, dialog, response_id):
    if (response_id == gtk.RESPONSE_OK):
      #get the login details, etc:
      self.username = str(self.nameEntry.get_text())
      self.password = str(self.pwEntry.get_text())
      if not self.username or not self.password:
        self.label.set_text("You must enter a non-empty username and password!")
        return
      #check that the username is possibly valid:
      if not Globals.USERNAME_REGEX.match(self.username):
        self.label.set_text("Usernames can only contain A-Z, a-z, 0-9, -, _, and spaces in the middle")
        return
      #log in to the bank:
      self.label.set_text("Connecting to bank...")
      Bank.get().login(self.username, self.password)
      self.nameEntry.set_sensitive(False)
      self.pwEntry.set_sensitive(False)
      self.loginButton.set_sensitive(False)
      self.quitButton.set_sensitive(False)
    elif (response_id == gtk.RESPONSE_CANCEL):
      self._do_quit()
    else:
      self.label.set_text("How did that even happen?")
      
  def on_login_success(self, bankApp, text):
    #show the server message if there was any:
    if text:
      GUIController.get().show_msgbox(text, "Server Notice")
    #save all this information to the settings files if necessary:
    settings = GlobalSettings.get()
    settings.save_password = self.savePassCheck.get_active()
    if not settings.save_password:
      self.username = ""
      self.password = ""
    settings.username = self.username
    settings.password = self.password
    settings.save()
    self.succeeded = True
    self.dia.destroy()
    
  #REFACTOR:  move this error handling logic into the Bank class
  def on_login_failure(self, bankApp, err, optionalServerResponse=None):
    text = None
    self.dia.window.raise_()
    eType = type(err)
    if eType is BadLoginPasswordError:
      text = str(err)
    elif eType is Failure:
      eType = type(err.value)
      if issubclass(eType, ConnectionDone) or issubclass(eType, ConnectionLost):
        text = "The login server is temporarily offline.  We are sorry for the inconvenience.  Please try again later."
    if not text:
      text = "Login failed for an unknown reason.  Please try again."
    text += "\nNOTE: You must restart the program to change users."
    if optionalServerResponse:
      force, optionalServerResponse = Basic.read_byte(optionalServerResponse)
      #concatenate
      if force is 0:
        text += '\n'+optionalServerResponse
      #nuke it
      else:
        text = optionalServerResponse
    self.label.set_text(text)
    self.nameEntry.set_sensitive(True)
    self.pwEntry.set_sensitive(True)
    self.loginButton.set_sensitive(True)
    self.quitButton.set_sensitive(True)

  def destroy_cb(self, *kw):
    if not self.succeeded:
      self._do_quit()
    