#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Let the user manually edit tracker URLs"""

import re

import gtk

from gui import GUIController

class TrackerEditDialog():
  def __init__(self, trackerList, callback, root):
    self.callback = callback
    self.originalTrackerList = trackerList
    buttons = (gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
    dia = gtk.Dialog("Edit Trackers", root, gtk.DIALOG_DESTROY_WITH_PARENT, buttons)
    dia.connect("response", self.on_response)
    
    instructions = gtk.Label("Enter trackers, one per line:")
    dia.vbox.pack_start(instructions, False, False, 5)
    
    #make the editable list of trackers
    self.textbuffer = gtk.TextBuffer(table=None)
    self.textbuffer.set_text("\n".join(trackerList))
    textview = gtk.TextView(self.textbuffer)
    textview.set_editable(True)
    textview.set_cursor_visible(True)
    textview.set_wrap_mode(gtk.WRAP_WORD)
    
    #create a new scrolled window.
    scrolled_window = gtk.ScrolledWindow()
    scrolled_window.set_border_width(10)
    scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
    scrolled_window.set_size_request(300, 350)
    scrolled_window.add_with_viewport(textview)
    dia.vbox.pack_start(scrolled_window, True, True, 0)
    
    self.dia = dia
    self.dia.show_all()
    
  def show(self):
    self.dia.show()

  #handle the result of the dialog:
  def on_response(self, dialog, responseId):
    if responseId == gtk.RESPONSE_OK:
      startiter = self.textbuffer.get_start_iter()
      enditer = self.textbuffer.get_end_iter()
      buf = self.textbuffer.get_text(startiter, enditer)
      buf = buf.replace("\r", "")
      buf = buf.replace(" ", "")
      buf = buf.replace("\t", "")
      trackerList = buf.split("\n")
      #remove duplicates
      newTrackerSet = set(trackerList)
      #figure out what lines are invalid
      toRemove = []
      badTrackerList = []
      trackerRegex = re.compile("^https?://.*$", re.IGNORECASE)
      for line in newTrackerSet:
        if not trackerRegex.match(line):
          toRemove.append(line)
          if line:
            badTrackerList.append(line)
      if badTrackerList:
        GUIController.get().show_msgbox("Bad format for tracker(s).  These trackers were ignored:  \n%s\n\nShould be like this:\nhttp://something.com/whatever" % ("\n".join(badTrackerList)), title="Bad format!")
        return
      #then remove them
      for line in toRemove:
        newTrackerSet.remove(line)
      if len(newTrackerSet) <= 0:
        self.callback(None)
      else:
        self.callback(list(newTrackerSet))
    elif responseId in (gtk.RESPONSE_CANCEL, gtk.RESPONSE_DELETE_EVENT):
      self.callback(None)
    else:
      raise Exception("Unknown gtk response:  %s" % (responseId))
    self.dia.destroy()
    
