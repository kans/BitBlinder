#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Show a list of all files in the torrent, with priorities and percent complete for each"""

import os

import gtk
import gobject
 
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.utils import GTKUtils

class PriorityDisplay():
  def __init__(self, app, torrentHash, data, showDoneColumn):
    self.app = app
    self.torrentHash = torrentHash
    self.torrentData = data
    self.download = None
    self.showDoneColumn = showDoneColumn
                #0:  File name
    typeList = [gobject.TYPE_STRING,
                #1:  Priority
                gobject.TYPE_INT,
                #2:  Size
                gobject.TYPE_INT64,
                #3:  Percent done
                gobject.TYPE_FLOAT]
    self.liststore = gtk.ListStore(*typeList)
    COLUMN_NAMES = ['File', 'Size', 'Priority']
    if showDoneColumn:
      COLUMN_NAMES += ['Completion']
      
    def format_priority(value):
      if value == -1:
        return ""
      elif value == 0:
        return "High"
      elif value == 1:
        return "Normal"
      elif value == 2:
        return "Low"
      else:
        log_msg("Bad priority value for format_priority:  %s" % (value), 3)
        return str(value)
    
    def format_size(value):
      value = float(value) / (1024.0 * 1024.0)
      if value < 1.0:
        return "%.2f MB" % (value)
      return "%.0f MB" % (value)
    modelfilter, treeview = GTKUtils.make_listview(self.liststore, COLUMN_NAMES)
    GTKUtils.make_toggle_cell(treeview.columns[0], 1)
    GTKUtils.make_text_cell(treeview.columns[0], 0)
    GTKUtils.make_text_cell(treeview.columns[1], 2, format_size)
    GTKUtils.make_text_cell(treeview.columns[2], 1, format_priority)
    if showDoneColumn:    
      GTKUtils.make_progress_cell(treeview.columns[3], 3)
    
    #make treeview searchable
    treeview.set_search_column(0)
    #attach the filtermodel and treeview
    treeview.set_model(gtk.TreeModelSort(modelfilter))
    treeview.connect("row-activated", self.row_activate_cb)
    treeview.connect("button-press-event", self.button_press_cb)
    treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
    self.modelfilter, self.treeview = modelfilter, treeview
    scrolled_window = GTKUtils.make_scroll_box(self.treeview, hPolicy=gtk.POLICY_AUTOMATIC, vPolicy=gtk.POLICY_AUTOMATIC)
    scrolled_window.set_size_request(-1, 200)
    scrolled_window.set_border_width(0)
    treeview.set_border_width(0)
    self.container = scrolled_window
    
    #now add the actual data:
    fileList = []
    i = self.torrentData['metainfo']['info']
    if i.has_key('length'):
      fileList.append([self.torrentData['file'].replace(".torrent", ""), self.torrentData['length']])
    elif i.has_key('files'):
      for entry in i['files']:
        folderList = entry['path']
        fileList.append([os.path.join(*folderList), entry['length']])
    else:
      raise Exception("Cannot handle torrent without length or files keys")
    #stick it in the gui
    for fileName, size in fileList:
      #TODO:  When you try putting some torrents in here, you get this error message:
      #  C:\Projects\web\innominet\gui\BTDisplay.py:386: PangoWarning: Invalid UTF-8 string passed to pango_layout_set_text()
      #  self.dia.show_all()
      #tried these, but they didnt work:
      #fileName = fileName.encode("UTF-8")
      #fileName = unicode( fileName, "utf-8" )
      self.liststore.append([fileName, 1, size, 0.0])
    
  def get_priorities(self):
    priorities = []
    for row in self.liststore:
      priorities.append(row[1])
    return priorities
  
  def apply(self):
    if self.download:
      priorityList = self.get_priorities()
      self.download.fileselector.set_priorities(priorityList)
      self.download.rawTorrentData['priority'] = ','.join(str(r) for r in priorityList)
      self.app.save_torrent_data(self.download.rawTorrentData)
      
  def update_completion(self):
    #dont bother if we are not visible:
    if not GTKUtils.is_visible(self.container):
      return
    if self.download and self.download.storagewrapper:
      have = self.download.storagewrapper.have
      i = 0
      for filePieces in self.download.fileselector.filepieces:
        completion = 0.0
        for piece in filePieces:
          completion += float(have[piece])
        fileLen = float(len(filePieces))
        if fileLen <= 0:
          completion = 100.0
        else:
          completion /= fileLen
          completion *= 100.0
        rowIter = self.liststore.get_iter(str(i))
        self.liststore.set_value(rowIter, 3, completion)
        i += 1
  
  def set_priorities(self, priorities):
    assert priorities, "cannot set null priorities"
    priorities = [int(i) for i in priorities.split(",")]
    for i in range(0, len(priorities)):
      rowIter = self.liststore.get_iter(str(i))
      self.liststore.set_value(rowIter, 1, priorities[i])
    self.apply()
  
  def set_all(self, val):
    def update_row(model, path, rowIter):
      model.set_value(rowIter, 1, val)
    self.liststore.foreach(update_row)
    self.apply()
  
  def toggle_selected(self):
    #get all rows:
    pathList = self.get_selected_rows()
    #invert:
    for path in pathList:
      #get the value the row:
      rowIter = self.liststore.get_iter(path)
      val = self.liststore.get_value(rowIter, 1)
      if val != -1:
        val = -1
      else:
        val = 1
      val = self.liststore.set_value(rowIter, 1, val)
    self.apply()
  
  def set_selected(self, val):
    #get all rows:
    pathList = self.get_selected_rows()
    for path in pathList:
      self.liststore.set_value(self.liststore.get_iter(path), 1, val)
    self.apply()
      
  def get_selected_rows(self):
    pathlist = []
    def foreach_cb(model, path, rowIter):
      pathlist.append(path)
    self.treeview.get_selection().selected_foreach(foreach_cb)
    return pathlist
  
  def row_activate_cb(self, treeview, rowIter, column):
    return
  
  def popup_menu(self, activationTime=None):
    def set_priority(widget, priority):
      self.set_selected(priority)
    menu = gtk.Menu()
    priorities = [0, 1, 2, -1]
    labels = ["Set High Priority", "Set Normal Priority", "Set Low Priority", "Dont Download"]
    for label, priority in zip(labels, priorities):
      item = gtk.MenuItem(label)
      item.connect("activate", set_priority, priority)
      menu.append(item)
    menu.show_all()
    menu.popup(None, None, None, 3, activationTime)
    
  def button_press_cb(self, treeview, event):
    """called whenever someone clicks on the treeview.
    this function only watches for a right click to launch the drop down menu.
    this callback is disgusting, but then again so are treeviews :("""
    if event.button == 3:
      self.popup_menu(event.time)
      return True
    elif event.button == 1:
      xPos = int(event.x)
      yPos = int(event.y)
      path = treeview.get_path_at_pos(xPos, yPos)
      if path:
        path, col, cellx, celly = path
        if hasattr(col, "toggleCell"):
          selected = self.get_selected_rows()
          pos = col.cell_get_position(col.toggleCell)
          if xPos >= pos[0] and xPos <= pos[1]:            
            #get the value the row:
            rowIter = self.liststore.get_iter(path)
            val = self.liststore.get_value(rowIter, 1)
            if val != -1:
              val = -1
            else:
              val = 1
            if path in selected and len(selected) > 1:
              self.set_selected(val)
              return True
            else:
              self.liststore.set_value(rowIter, 1, val)
              self.apply()
              