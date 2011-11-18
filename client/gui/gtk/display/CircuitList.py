#!/usr/bin/python
#Copyright 2009 InnomiNet
"""List all circuits and streams in a shallow tree list"""

import pygtk
pygtk.require('2.0')
import gtk, gobject
import time
import types
import sys
import struct
from twisted.internet import protocol
from twisted.protocols.basic import Int32StringReceiver

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.classes import Scheduler
from common.events import GlobalEvents
from gui.gtk.utils import GTKUtils
from gui import GUIController
from core import ClientUtil
from core.bank import Bank
from Applications import BitBlinder

#Basic usage is much like Vidalia.  There is a list of circuits, expandable to
#see the streams that are attached to these circuits.  The data structure 
#(TreeStore) doesnt quite fit because it assumes that all rows have the same 
#values, while streams and circuits have some different data to display.  For 
#example, right now the circuit.currentPath and stream.targetHost/port are shown in
#the same column.  I think it will work out all right though
class CircuitList(GlobalEvents.GlobalEventMixin):
  """ The CircuitList class displays a tree of circuits and attached streams """
  def __init__(self):
    bbApp = BitBlinder.get()
    self.bbApp = bbApp
    self.torApp = bbApp.torApp
    self.catch_event("tor_ready")
    self.catch_event("tor_done")
    self.catch_event("new_relay")
    ClientUtil.add_updater(self)
    #create the view and store for all the data columns:
    #TODO:  make display text prettier (transition to MB as appropriate, etc)
    self.mdl = gtk.TreeStore( gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, int, str, str, "gboolean" )
    modelfilter = self.mdl.filter_new()
    self.visColumn = 10
    modelfilter.set_visible_column(self.visColumn)
    self.view = gtk.TreeView( modelfilter )
    self.columnLabels = ["ID", "Status", "Path", "BW (down)", "Reason", "Age", "Total (Down)"]

    #add each of the columns
    for i in range(0,len(self.columnLabels)):
      name = self.columnLabels[i]
      colId = i
      #make column
      column = gtk.TreeViewColumn(name)
      #basic string renderer for the data in the column
      column.cell = gtk.CellRendererText()
      #add the renderer to the column...  idk if you can add more than one
      column.pack_start(column.cell, True)
      #add the column to the treeview
      self.view.append_column(column)
      ##TODO:  this gave an exception last time for some reason
      ##this acts as a macro to set a bunch of properties that make this column sortable
      #column.set_sort_column_id(colId)
      #tell the column where to get it's string data, and the data for colors
      column.set_attributes(column.cell, text=colId, background=len(self.columnLabels)+1, foreground=len(self.columnLabels)+2)
      #set properties to make the column interact intuitively.
      column.set_properties(reorderable=True, expand=True, clickable=True, resizable=True)
      
    hbox = gtk.HBox()
    self.showCircuits = False
    self.showStreams = False
    button = gtk.CheckButton("Show closed Streams:")
    button.connect("toggled", self.toggle_cb, "streams")
    hbox.pack_start(button)
    button = gtk.CheckButton("Show closed Circuits:")
    button.connect("toggled", self.toggle_cb, "circuits")
    hbox.pack_start(button)
      
    self.vbox = gtk.VBox()
    #make scrollwindow because the circuit list gets really long
    self.scrolled_window = gtk.ScrolledWindow()
    self.scrolled_window.set_border_width(10)
    self.scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
    #self.scrolled_window.set_size_request(500, 500)
    self.scrolled_window.add_with_viewport(self.view)
    self.scrolled_window.show()
    self.comboRow = gtk.HButtonBox()
    self.buttonRow = gtk.HButtonBox()
#    self.testRow = gtk.HBox()
    self.vbox.pack_start(hbox, False)
    self.vbox.pack_start(self.scrolled_window)
    self.vbox.pack_start(self.comboRow, False)
    self.vbox.pack_start(self.buttonRow, False)
#    self.vbox.pack_start(self.testRow, False)
    
    self.testStreams = []
    self.objects = set()
    
    self.routerCombos = []
    for i in range(0,3):
      combo = gtk.combo_box_new_text() 
      self.routerCombos.append(combo)
      combo.set_size_request(100, -1)
      self.comboRow.pack_start(combo)
      
    self.countryCombo = gtk.combo_box_new_text()
    self.countryCombo.append_text("")
    self.countryCombo.set_size_request(150, -1)
    self.comboRow.pack_start(self.countryCombo)
    self.countryCombo.connect("changed", self.country_changed_cb)
      
    b = gtk.Button("Launch Circuit")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.launch_circuit)
    
    b = gtk.Button("Download")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.launch_test_download)
    
    b = gtk.Button("Upload")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.launch_test_upload)
    
    b = gtk.Button("PAR Test")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.launch_par_test)
    
    b = gtk.Button("DHT")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.dht_cb)
    
    b = gtk.Button("Inspect")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.inspect_cb)
    
    b = gtk.Button("Kill Selected")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.kill_selected)
    
    self.vbox.show()
    self.comboRow.show()
    self.buttonRow.show()
    
    #these are used by GTK Controller to easily add the component to the main window
    self.label = gtk.Label("Circuit List")
    self.container = self.vbox
    
  def on_tor_done(self):
    self.mdl.clear()
    for combo in self.routerCombos:
      model = combo.get_model()
      model.clear()
    #end all of the streams:
    for stream in self.testStreams:
      stream.close("Disconnected from Tor")
    return
  
  def on_new_relay(self, r):
    try:
      assert isinstance(r.desc.nickname, basestring), "nickname must be a string"
      assert type(r.desc.idhex) == types.StringType, "idhex must be a string"
      for i in range(0,3):
        self.routerCombos[i].append_text(r.desc.nickname + "~" + r.desc.idhex)
    except Exception, e:
      log_ex(e, "Problem while updating routers in circuitlist")
    
  def toggle_cb(self, widget, data=None):
    if data == "streams":
      self.showStreams = widget.get_active()
    elif data == "circuits":
      self.showCircuits = widget.get_active()
    
  #called to inspect the events of a Circuit or Stream in detail
  #NOTE:  this is kind of hackish
  def inspect_cb(self, widget, event=None):
    return
    
  def remove_object(self, obj):
    if obj.treeRow:
      iter = self.mdl[obj.treeRow.get_path()].iter
      self.mdl.remove(iter)
      obj.treeRow = False
    
  #called to update both Circuits AND streams, because they have so much in common:
  #should NOT be called by outside objects!
  def update_object(self, obj, type):
    #get the row to update
    iter = self.mdl[obj.treeRow.get_path()].iter
    background = "white"
    foreground = "black"
    pathString = ""
    if type == "circuit":
      for r in obj.currentPath:
        pathString += r.desc.nickname + ", "
    elif type == "stream":
      pathString = obj.targetHost + ":" + str(obj.targetPort)
      if obj.source or obj.sourceAddr:
        pathString = " -> " + pathString
      if obj.source:
        pathString = obj.source + pathString
      if obj.sourceAddr:
        pathString = obj.sourceAddr + "|" + pathString
    else:
      log_msg("You probably mispelled circuit or stream...", 3)
    reasonString = ""
    if obj.reason:
      reasonString += "REASON="+obj.reason
    if obj.remoteReason:
      reasonString += "/REMOTE_REASON="+obj.remoteReason
    
    #update all the data for the stream
    self.mdl.set(iter, 0, obj.id)
    self.mdl.set(iter, 1, obj.status)
    self.mdl.set(iter, 2, pathString)
    self.mdl.set(iter, 4, reasonString)
    
    #set the color based on the status of the stream
    if obj.status in ("REMAP", "SENTCONNECT", "EXTENDED", "LAUNCHED", "PAR_SETUP", "PAR_SETUP2"):
      background = "yellow"
    if obj.status in ("DETACHED"):
      background = "orange"
    if obj.status in ("FAILED"):
      background = "red"
    if obj.status in ("CLOSED"):
      background = "grey"
    self.mdl.set(iter, len(self.columnLabels)+1, background)
      
    #figure out if this row should be visible or not
    isVisible = True
    if type == "circuit":
      if obj.status in ("FAILED", "CLOSED"):
        if not self.showCircuits:
          isVisible = False
    else:
      if obj.circuit:
        if obj.circuit.status in ("FAILED", "CLOSED"):
          if not self.showCircuits:
            isVisible = False
        else:
          if obj.status in ("FAILED", "CLOSED"):
            if not self.showStreams:
              isVisible = False
      else:
        if obj.status in ("FAILED", "CLOSED"):
          if not self.showStreams:
            isVisible = False
    self.mdl.set(iter, self.visColumn, isVisible)
    
    down, up = obj.get_instant_bw()
    #convert to KBps
    down = float(down) / 1000.0
    up = float(up) / 1000.0
    self.mdl.set(iter, 3, "%.1f KBps / %.1f KBps" % (down, up))
    totalDown = obj.totalRead
    #convert to KBps
    totalDown = float(totalDown) / 1000.0
    self.mdl.set(iter, 6, "%.1f KB" % totalDown)
    
    endTime = obj.endedAt
    if not endTime:
      endTime = time.time()
    timeStr = "%d sec" % int(endTime - obj.createdAt)
    self.mdl.set(iter, 5, timeStr)
    
  #called once every INTERVAL_BETWEEN_UPDATES after bws have been calculated
  def on_update(self):
    #dont bother if we are not visible:
    if not GTKUtils.is_visible(self.container):
      return
      
    #track which rows still exist:
    updateObjects = set()
    appList = self.bbApp.applications.values() + [self.bbApp, self.bbApp.torApp]
    #update each app:
    for app in appList:
      #make sure a row exists for it
      if not hasattr(app, "treeRow") or not app.treeRow:
        #insert into the model
        iter = self.mdl.append(None, (app.name, "", "", "", "", "", "", 1, "white", "black", True))
        #set treeRow so we can more easily update in the future
        app.treeRow = gtk.TreeRowReference(self.mdl, self.mdl.get_string_from_iter(iter))
    #update each circ:
    for app in appList:
      for circuit in app.circuits:
        self.objects.add(circuit)
        #if circuit.treeView is not set, this must be a new circuit
        if not hasattr(circuit, "treeRow") or not circuit.treeRow:
          #insert into the model
          iter = self.mdl.append(self.mdl[circuit.app.treeRow.get_path()].iter, (str(circuit.id), circuit.status, "path", "0", "", "0 sec", "0", 1, "white", "black", True))
          #set circuit.treeRow so we can more easily update in the future
          circuit.treeRow = gtk.TreeRowReference(self.mdl, self.mdl.get_string_from_iter(iter))
        #update the information in the row
        updateObjects.add(circuit)
        self.update_object(circuit, "circuit")
    #update each stream:
    for app in appList:
      for stream in app.streams.values():
        self.objects.add(stream)
        #if stream.circuit.treeRow is not set, this must be a new circuit
        if not stream.treeRow:
          #this might happen if the stream is new and hasnt been assigned a circuit yet
          if not stream.circuit:
            return
          #this should never happen.
          if not stream.circuit.treeRow:
            log_msg("%s has a circuit %s with no treeRow?" % (stream.id, stream.circuit.id), 0)
            return
          #get the row of the circuit
          iter = self.mdl[stream.circuit.treeRow.get_path()].iter
          #insert the stream as a child of the circuit
          iter = self.mdl.append(iter, (str(stream.id), stream.status, stream.targetHost, "0", "", "0 sec", "0", 0, "white", "black", True))
          #set stream.treeRow for easy updating later
          stream.treeRow = gtk.TreeRowReference(self.mdl, self.mdl.get_string_from_iter(iter))
        else:
          #check that we are under the RIGHT circuit (in case of being reattached):
          parent = None
          shouldUpdate = False
          #do we have a circuit?
          if stream.circuit:
            #is that circuit in the GUI yet?
            if stream.circuit.treeRow:
              parent = self.mdl[stream.circuit.treeRow.get_path()].iter
              iter = self.mdl[stream.treeRow.get_path()].iter
              iter = self.mdl.iter_parent(iter)
              #do we have a parent row?
              if iter:
                #check if it is the RIGHT parent row or not
                id = int(self.mdl.get_value(iter, 0))
                if id != stream.circuit.id:
                  shouldUpdate = True
              else:
                shouldUpdate = True
            else:
              log_msg("Stream "+str(stream.id)+" has Circuit "+str(stream.circuit.id)+" with no treeRow?", 0)
          else:
            #can justput at the end of the list, top level:
            shouldUpdate = True
          #remove old row and insert new row if necessary:
          if shouldUpdate:
            oldIter = self.mdl[stream.treeRow.get_path()].iter
            n_columns = self.mdl.get_n_columns()
            values = self.mdl.get(oldIter, *range(n_columns))
            self.mdl.remove(oldIter)
            newIter = self.mdl.append(parent, values)
            stream.treeRow = gtk.TreeRowReference(self.mdl, self.mdl.get_string_from_iter(newIter))
        #update the information in the row
        self.update_object(stream, "stream")
        updateObjects.add(stream)
    #remove any of our rows that were NOT updated:
    toRemove = []
    for obj in self.objects:
      if obj not in updateObjects:
        toRemove.append(obj)
    for obj in toRemove:
      self.remove_object(obj)
      self.objects.remove(obj)
      
  #get the selected Stream or Circuit object corresponding to the selected row
  #does not handle multiple simultaneous selections
  def getSelected(self):
    obj = None
    #get the selection
    sel = self.view.get_selection()
    #get the selected row
    model, iter = sel.get_selected()
    if iter:
      #get the "id" value for the row
      try:
        id = int(model.get_value(iter, 0))
      except:
        #TODO:  again, a really bad way of seeing that this is a Application treeRow
        return None
      isCircuit = int(model.get_value(iter, len(self.columnLabels)))
      #get the "path" of the row.  This is a way of describing the position of 
      #the row in the TreeView.  If the path is one element long, the row is in 
      #the top level of the tree.  If it is two elements long, it is in the
      #second level, etc.  IN this case, first level always means that it is a 
      #circuit, so we can use that to decide whether to return the obj from 
      #.streams or .circuits
      path = model.get_path(iter)
      #then this is a stream:
      if not isCircuit:
        obj = BitBlinder.get().get_stream(id)
      else:
        obj = BitBlinder.get().get_circuit(id)
    return obj
    
  def on_tor_ready(self):
    for i in range(0,3):
      self.routerCombos[i].append_text("")
  
  def country_changed_cb(self, combobox, args=None):
    country = self.countryCombo.get_active_text()
    if not country:
      country = None
    else:
      country = country.split(":")[0]
    BitBlinder.get().set_exit_country(country)
    
  def launch_circuit(self, widget, event=None):
    path = []
    len = 0
    for i in range(0,3):
      str = self.routerCombos[i].get_active_text()
      if not str or str == "":
        pass
      else:
        len = i+1
    if len == 0:
      BitBlinder.get().build_circuit("", 80)
      return
    for i in range(0,3):
      str = self.routerCombos[i].get_active_text()
      r = None
      if not str or str == "":
        r = self.torApp.make_path(1)[0]
      else:
        hexId = str.split("~")[1]
        r = self.torApp.get_relay(hexId)
      path.append(r)
      if i+1 >= len:
        break
    circ = BitBlinder.get().create_circuit(path)
    
  def launch_test_download(self, widget, event=None):    
    test = None
    #get the selected item (either a Stream or Circuit)
    circ = self.getSelected()
    #if there was no selection or the selection was a stream, let BitBlinder pick the circuit
    if not circ or circ.__class__.__name__ != "Circuit":
      #TODO:  actually use the test URL/port here...
      circ = BitBlinder.get().find_or_build_best_circuit("", 80)
      #make sure there is a circuit:
      if not circ:
        log_msg("Failed to find an appropriate circuit", 1)
        return
    #make sure we dont try to attach to a close circuit
    if not circ.is_open():
      log_msg("Circuit %d is closed" % circ.id, 2)
      return
    
    def page_done(data, httpDownloadInstance):
      self.end_time = time.time()
      log_msg("Test downloaded " + str(len(data)) + " bytes", 2)
    test = BitBlinder.http_download(Globals.TEST_URL, circ, page_done)
    
    #GUIController.get().relayScreen.orPort.circ = circ
    #GUIController.get().relayScreen.orPort._start_probe(True)
    
  def launch_test_upload(self, widget, event=None):    
    test = None
    #get the selected item (either a Stream or Circuit)
    circ = self.getSelected()
    #if there was no selection or the selection was a stream, let BitBlinder pick the circuit
    if not circ or circ.__class__.__name__ != "Circuit" or not circ.is_open():
      log_msg("Cannot upload through that %s" % (circ), 0)
      return
      
    class TestUploader(Int32StringReceiver):
      def connectionMade(self):
        self.bytesLeft = 2 * 1024 * 1024
        self.transport.write(struct.pack("!I", self.bytesLeft))
        self.sendEvent = Scheduler.schedule_repeat(0.1, self.send_more, 1024 * 10)
        
      def send_more(self, numBytes):
        self.transport.write("1"*numBytes)
        self.bytesLeft -= numBytes
        if self.bytesLeft <= 0:
          return False
        else:
          return True
          
      def stringReceived(self,  data):
        log_msg("Upload hopefully done?")
        return
        
    factory = protocol.ClientFactory()
    factory.protocol = TestUploader
    #connect to the bank and send some trash:
    d = BitBlinder.get().launch_external_factory(Bank.get().host, Bank.get().port, factory, circ.handle_stream, "Test Upload")
    
  def dht_cb(self, widget=None):
    selectedTorrents = GUIController.get().btWindow._get_selected_torrents()
    if len(selectedTorrents) != 1:
      log_msg("Select a torrent for the DHT request in the BitTorrent window", 0)
      return
    infohash = selectedTorrents[0]
    def callback(*args):
      log_msg("Got DHT response!  %s" % (str(args)))
    GUIController.get().btWindow.app.btInstance.dht.circ = self.getSelected()
    GUIController.get().btWindow.app.btInstance.dht.get_peers(infohash, callback)
    
  def message_cb(self, widget, event=None):
    pass
#    #get the selected item (either a Stream or Circuit)
#    circ = self.getSelected()
#    #if there was no selection or the selection was a stream, let BitBlinder pick the circuit
#    if not circ or circ.__class__.__name__ != "Circuit":
#      return
#    #make sure we dont try to attach to a close circuit
#    if not circ.is_ready():
#      log_msg("Circuit %d is not ready for message test" % circ.id, 2)
#      return
#    
#    def add_padding(tmp, desiredLen):
#      extraChars = desiredLen - len(tmp)
#      return tmp + (" " * extraChars)
#    msg = "Hey this is my message!!"
#    msg = add_padding(msg, 507)
#    #msg = msg.encode("base64").replace('\n', '*')
#    msg = msg.encode("base64").replace('\n', '').replace('=', '')
#    msg = "SENDPAYMENT %s 0 %s %s\r\n" % (circ.finalPath[0].desc.idhex, circ.id, msg)
#    result = self.torApp.conn.sendAndRecv(msg)
#    log_msg(str(result), 3)
    
  def launch_par_test(self, widget, event=None):
    #get the selected item (either a Stream or Circuit)
    circ = self.getSelected()
    #if there was no selection or the selection was a stream, let BitBlinder pick the circuit
    if not circ or circ.__class__.__name__ != "Circuit":
      return
    numReadCells = Globals.CELLS_PER_PAYMENT/2
    numWriteCells = Globals.CELLS_PER_PAYMENT - numReadCells
    circ.parClient.send_payment_request(numReadCells, numWriteCells)
    
  def kill_selected(self, widget, event=None):
    #get the selected item (either a Stream or Circuit)
    obj = self.getSelected()
    #if there is something selected:
    if obj:
      #close it:
      obj.close()
    
