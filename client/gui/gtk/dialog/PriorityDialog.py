#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Prompt the user for where to store a download, and which files in a torrent to actually download"""

import os
import re

import gtk
 
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.utils import GTKUtils
from gui.gtk.display import PriorityDisplay

class PriorityDialog():
  """Prompt the user for which files to download, which to ignore"""
  def __init__(self, app, torrentHash, data):
    self.app = app
    self.torrentHash = torrentHash
    self.torrentData = data
    self.succeeded = False
    #download location:
    saveasRow = gtk.HBox()
    self.filenameEntry = gtk.Entry()
    
    #figure out if this is a single file, or a folder:
    torrentInfo = self.torrentData['metainfo']['info']
    self.isFile = False
    self.defaultFileName = os.path.join(self.app.settings.torrentFolder, torrentInfo['name'])
    self.fileType = "folder"
    if torrentInfo.has_key('length'):
      self.isFile = True
      match = re.compile("^.*\\.(.+)$").match(self.defaultFileName)
      if match:
        self.fileType = match.group(1)
      else:
        self.fileType = "all files"
    elif torrentInfo.has_key('files'):
      pass
    else:
      raise Exception("Cannot handle torrent without length or files keys")
    
    self.filenameEntry.set_text(os.path.join(os.getcwdu(), self.defaultFileName))
    self.filenameEntry.set_width_chars(len(self.defaultFileName) + 20)
    self.filenameEntry.connect("activate", self.enter_cb)    
    filenameButton = gtk.Button("Browse...")
    filenameButton.connect('clicked', self.filename_cb)
    saveasRow.pack_start(gtk.Label("Save torrent in folder:  "), False, False, 5)
    saveasRow.pack_start(self.filenameEntry, True, True, 5)
    saveasRow.pack_start(filenameButton, False, False, 5)
    #file selection button row:
    buttonRow = gtk.HBox()
    selectAllButton = gtk.Button("Select All")
    selectAllButton.connect('clicked', self.select_all_cb)
    selectNoneButton = gtk.Button("Select None")
    selectNoneButton.connect('clicked', self.select_none_cb)
    toggleSelectedButton = gtk.Button("Toggle Selected")
    toggleSelectedButton.connect('clicked', self.toggle_selected_cb)
    buttonRow.pack_start(selectAllButton, False, False, 5)
    buttonRow.pack_start(selectNoneButton, False, False, 5)
    buttonRow.pack_start(toggleSelectedButton, False, False, 5)
    #file selection interface:
    self.fileSelectionInterface = PriorityDisplay.PriorityDisplay(self.app, hash, data, False)
    #create the actual dialog
    self.dia = gtk.Dialog("Choose Files",
      app.display,  #the toplevel wgt of your app
      gtk.DIALOG_DESTROY_WITH_PARENT,
      None)
    self.dia.vbox.pack_start(saveasRow, False, False, 10)
    self.dia.vbox.pack_start(buttonRow, False, False, 10)
    self.dia.vbox.pack_start(self.fileSelectionInterface.container, True, True, 10)
    #add response buttons:
    self.okButton = self.dia.add_button("Ok", gtk.RESPONSE_OK)
    self.cancelButton = self.dia.add_button("Cancel", gtk.RESPONSE_CANCEL)
    self.dia.show_all()
    #connect the handlers:
    self.dia.connect("response", self.on_response)
    self.dia.connect("destroy", self.destroy_cb)
    
  def filename_cb(self, widget, event=None):
    def on_response(filename):
      #ensure that the filter is right:
      if self.fileType not in ("folder", "all files"):
        if not re.compile("^.*\\.%s$" % (self.fileType)).match(filename):
          filename += "." + self.fileType
      if len(filename) > self.filenameEntry.get_width_chars():
        self.filenameEntry.set_width_chars(len(filename) + 10)
      self.filenameEntry.set_text(filename)
    if self.fileType == "all files":
      fileTypeFilter = ("All Files", "*.*")
    elif self.fileType == "folder":
      fileTypeFilter = None
    else:
      fileTypeFilter = ("%s Files" % (self.fileType.upper()), "*.%s" % (self.fileType))      
    GTKUtils.launch_file_selector(on_response, self.filenameEntry.get_text(), fileTypeFilter, True)
    
  def enter_cb(self, widget):
    self.on_response(self.dia, gtk.RESPONSE_OK)
    
  def select_all_cb(self, widget):
    self.fileSelectionInterface.set_all(1)
    
  def select_none_cb(self, widget):
    self.fileSelectionInterface.set_all(-1)
    
  def toggle_selected_cb(self, widget):
    self.fileSelectionInterface.toggle_selected() 
    
  def on_response(self, dialog, response_id):
    """What to do when the dialog is done"""
    if response_id == gtk.RESPONSE_OK:
      #assign the priorities appropriately:
      priorityList = self.fileSelectionInterface.get_priorities()
      priority = ','.join(str(r) for r in priorityList)
      saveAsFile = unicode(self.filenameEntry.get_text())
      self.succeeded = True
      #start the download
      self.app.add_torrent(self.torrentHash, self.torrentData, saveAsFile, priority)
    else:
      #cancel the download:
      pass
    self.dia.destroy()
    
  def destroy_cb(self, *kw):
    if not self.succeeded:
      self.on_response(self.dia, gtk.RESPONSE_CANCEL)
      