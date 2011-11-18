#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Allow a user to type a description of an error report and submit it"""

import pygtk
import gtk

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.utils import GTKUtils
from gui import GUIController
from core import ClientUtil
from core import ErrorReporting
from core import ProgramState
from Applications import GlobalSettings

class ErrorReportDialog():
  def __init__(self):    
    self.host = Globals.FTP_HOST
    self.port = Globals.FTP_PORT
    self.user = Globals.FTP_USER
    self.pw   = Globals.FTP_PASSWORD
    self.submitThread = None
    
    buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
    
    dia = gtk.Dialog("Submit Error", None, 0, buttons)

    #username field
    usernameLabel = gtk.Label("Username")
    self.nameEntry = gtk.Entry()
    self.nameEntry.set_max_length(50)
    try:
      self.nameEntry.set_text(GlobalSettings.get().username)
    except:
      pass

    #comment field
    self.textbuffer = gtk.TextBuffer(table=None)
    self.textbuffer.set_text("Please describe the error or issue here.")
    textview = gtk.TextView(self.textbuffer)
    buffer=textview.get_buffer()
    textview.set_editable(True)
    textview.set_cursor_visible(True)
    textview.set_wrap_mode(gtk.WRAP_WORD)
    textview.show()
    
    # create a new scrolled window.
    scrolled_window = gtk.ScrolledWindow()
    scrolled_window.set_border_width(10)
    scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
    #scrolled_window.set_size_request(300, 350)
    scrolled_window.add_with_viewport(textview)
    scrolled_window.show()

    #put them in a nice little table
    table = gtk.Table(4, 2, True)
    table.attach(usernameLabel, 0, 1, 0, 1)
    table.attach(self.nameEntry, 1, 2, 0, 1)
    table.attach(scrolled_window, 0, 2, 1, 4)

    dia.vbox.pack_start(table, True, True, 0)

    self.nameEntry.set_text(GlobalSettings.get().username)

    dia.show_all()

    #connect the handler:
    dia.connect("response", self.on_response)
    self.dia = dia

  #handle the result of the dialog:
  def on_response(self, dialog, response_id):
    if (response_id == gtk.RESPONSE_OK):
      #get the login details, etc:
      self.username = str(self.nameEntry.get_text())
      if not self.username:
        GUIController.get().show_msgbox("You must enter a username of some sort.", title="Invalid Username")
        return
      #ship off to the ftp server!
      log_msg("archiving stuffs", 2)
      startiter = self.textbuffer.get_start_iter()
      enditer   = self.textbuffer.get_end_iter()
      buf = self.textbuffer.get_text(startiter, enditer)
      ClientUtil.create_error_archive(buf)
      log_msg("submiting archive", 2)
      def response(success):
        if success:
          GUIController.get().show_msgbox("The bug report was sent successfully.", title="Success!")
        else:
          if not ProgramState.DONE:
            GUIController.get().show_msgbox("The bug report failed.  You can submit the bug manually at:", title="Too Much Fail", link=GTKUtils.make_html_link("http://innomi.net/bugs/report/1", 'http://innomi.net/bugs/report/1'))
      ftpSubmitter = ErrorReporting.send_error_report()
      ftpSubmitter.cb = response
      GUIController.get().show_msgbox("The bug report is being sent.  BitBlinder will alert you when it is finished.", title="Thanks!")
      self.dia.destroy()
    elif (response_id == gtk.RESPONSE_CANCEL):
      self.dia.destroy()
    else:
      log_msg("canceled error submition", 2)
      