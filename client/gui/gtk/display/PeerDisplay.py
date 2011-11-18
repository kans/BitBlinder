#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Show a list of all files in the torrent, with priorities and percent complete for each"""

import gtk
import gobject
 
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Format
from common.events import GlobalEvents
from gui.gtk.utils import GTKUtils
from core import ClientUtil

class PeerDisplay(GlobalEvents.GlobalEventMixin):
  def __init__(self, app, torrentHash, data):
    self.app = app
    ClientUtil.add_updater(self)
    self.torrentHash = torrentHash
    self.torrentData = data
    self.download = None
    #a mapping from peer id to row
    self.peerRows = {}
    self.attrIdx = {}
    
    self.COLUMNS = [ ("ip",           "IP",        "string"),
                     ("upRate",       "uRate",     "rate"),
                     ("downRate",     "dRate",     "rate"),
                     ("upTotal",      "uTotal",    "amount"),
                     ("downTotal",    "dTotal",    "amount"),
                     ("upChoked",     "uChoked",   "string"),
                     ("downChoked",   "dChoked",   "string"),
                     ("snub",         "Snub",      "string"),
                     ("upInterest",   "uInterest", "string"),
                     ("downInterest", "dInterest", "string"),
                     ("speed",        "Speed",     "rate"),
                     ("requests",     "Requests",  "string"),
                     ("circ",         "Circ",      "string"),
                     ("amountDone",   "Done",      "percent"),
                     ("client",       "Client",    "string"),
                     ("id",           "ID",        "string")]
    COLUMN_NAMES = [columnTuple[1] for columnTuple in self.COLUMNS]
    TYPE_LIST = []
    for columnTuple in self.COLUMNS:
      columnType = columnTuple[2]
      if columnType in ("string"):
        TYPE_LIST.append(gobject.TYPE_STRING)
      elif columnType == "amount":
        TYPE_LIST.append(gobject.TYPE_INT)
      elif columnType in ("rate", "percent"):
        TYPE_LIST.append(gobject.TYPE_FLOAT)
      else:
        raise Exception("Bad type for column:  %s" % (columnType))

    self.liststore = gtk.ListStore(*TYPE_LIST)
    modelfilter, treeview = GTKUtils.make_listview(self.liststore, COLUMN_NAMES)
    for i in range(0, len(self.COLUMNS)):
      attrName = self.COLUMNS[i][0]
      attrType = self.COLUMNS[i][2]
      self.attrIdx[attrName] = i
      if attrType == "string":
        GTKUtils.make_text_cell(treeview.columns[i], i, makeSortable=True)
      else:
        cellFunc = getattr(self, "_cell_data_" + attrType)
        self._make_number_cell(treeview.columns[i], i, cellFunc)
        
    #make treeview searchable
    treeview.set_search_column(0)
    #attach the filtermodel and treeview
    self.model = gtk.TreeModelSort(modelfilter)
    treeview.set_model(self.model)
    treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
    self.modelfilter, self.treeview = modelfilter, treeview
    scrolled_window = GTKUtils.make_scroll_box(self.treeview, hPolicy=gtk.POLICY_AUTOMATIC, vPolicy=gtk.POLICY_AUTOMATIC)
    scrolled_window.set_size_request(-1, 200)
    self.container = scrolled_window
    
  def _make_number_cell(self, column, valueNum, cellDataFunc):
    column.numberCell = gtk.CellRendererText()
    column.valueNum = valueNum
    column.pack_start(column.numberCell, True)
    column.set_cell_data_func(column.numberCell, cellDataFunc)
    column.set_sort_column_id(valueNum)
    #set properties to make the column interact intuitively.
    column.set_properties(reorderable=True, expand=False, clickable=True)
    
  def _cell_data_rate(self, column, cell, model, row):
    value = model.get_value(row, column.valueNum)
    text = Format.bytes_per_second(value)
    cell.set_property("text", text)
    
  def _cell_data_amount(self, column, cell, model, row):
    value = model.get_value(row, column.valueNum)
    text = Format.format_bytes(value)
    cell.set_property("text", text)
    
  def _cell_data_percent(self, column, cell, model, row):
    value = model.get_value(row, column.valueNum)
    text = "%.1f%%" % (value * 100.0)
    cell.set_property("text", text)
    
  def on_update(self):
    if not GTKUtils.is_visible(self.container):
      return    

    if not self.download.started:
      return
    
    #now add the actual data:
    stats = self.download.startStats(True)
    peers = stats['spew']
    peersUpdated = set()
    
    if not peers:
      return
    
    for peerInfo in peers:
      #format all data for this peer
      def format_bool(val):
        if val is True:
          return '1'
        if val is False:
          return '0'
        return str(val)
        
      peerId = peerInfo['id']
      peerClient = peerInfo['client']
      peerIp = peerInfo['ip']
      upRate = float(peerInfo['uprate'])
      downRate = float(peerInfo['downrate'])
      totalUp = int(peerInfo['utotal'])
      totalDown = int(peerInfo['dtotal'])
      chokedUp = format_bool(peerInfo['uchoked'])
      chokedDown = format_bool(peerInfo['dchoked'])
      snubbed = format_bool(peerInfo['snubbed'])
      interestedUp = format_bool(peerInfo['uinterested'])
      interestedDown = format_bool(peerInfo['dinterested'])
      speed = float(peerInfo['speed'])
      requests = str(peerInfo['pendingRequests'])
      circId = str(peerInfo['circId'])
      completed = float(peerInfo['completed'])
      allValues = [peerIp, upRate, downRate, totalUp, totalDown, chokedUp, chokedDown,
        snubbed, interestedUp, interestedDown, speed, requests, circId, completed, peerClient, peerId]
        
      #do we have a row already for this peer?
      if peerId in self.peerRows:
        #then just update the row
        peerIter = self.liststore[self.peerRows[peerId].get_path()].iter
        valuesArg = []
        for columnTuple, value in zip(self.COLUMNS, allValues):
          idx = self.attrIdx[columnTuple[0]]
          valuesArg.append(idx)
          valuesArg.append(value)
        self.liststore.set(peerIter, *valuesArg)
      else:
        #otherwise have to make a new one
        peerIter = self.liststore.append(allValues)
        self.peerRows[peerId] = gtk.TreeRowReference(self.liststore, self.liststore.get_string_from_iter(peerIter))
      peersUpdated.add(peerId)
      
    toRemove = set()
    for peerId, row in self.peerRows.iteritems():
      if peerId not in peersUpdated:
        toRemove.add(peerId)
    for row in toRemove:
      del self.peerRows[row]
      
