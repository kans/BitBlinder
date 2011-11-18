#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""GUI for BitTorrent"""

import os
import urllib

import gtk
import gobject
 
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Basic
from common.utils import Format
from common.events import GlobalEvents
from common.events import GeneratorMixin 
from common.events import ListenerMixin
from common.contrib import FileHandler
from gui import GUIController
from gui.gtk.utils import GTKUtils
from gui.gtk.utils import Images
from gui.gtk.widget import BaseMenuBar
from gui.gtk.widget import ClosableTabNotebook
from gui.gtk.dialog import PriorityDialog
from gui.gtk.dialog import AnonymityLevelDialog
from gui.gtk.dialog import TrackerEditDialog
from gui.gtk.display import PriorityDisplay
from gui.gtk.display import PeerDisplay
from gui.gtk.display import BWGraph
from gui.gtk.window import TopWindow
from core import ClientUtil
from core.bank import Bank
from Applications import BitBlinder
from Applications import Tor

class TorrentPopupMenu(gtk.Menu, ListenerMixin.ListenerMixin):
  def __init__(self, display):
    """Creates a drop-down menu to interact with the torrent"""
    gtk.Menu.__init__(self)
    ListenerMixin.ListenerMixin.__init__(self)
    self.display = display
    baseMenu = self
    #create menu items
    self.openItem = GTKUtils.append_menu_item(baseMenu, "Open Containing Folder", display._open_folder)
    if not display._any_selected_torrent_running():
      self.pauseItem = GTKUtils.append_menu_item(baseMenu, "Resume", display._pause_cb)
    else:
      self.pauseItem = GTKUtils.append_menu_item(baseMenu, "Pause", display._pause_cb)
    #create a right-click option to update the tracker
    def update_cb(widget):
      torrentsToUpdate = display._get_selected_torrents()
      for torrentHash in torrentsToUpdate:
        display.app.btInstance.downloads[torrentHash].rerequest.update(True)
    self.updateItem = GTKUtils.append_menu_item(baseMenu, "Update Tracker", update_cb)
    self.editItem = GTKUtils.append_menu_item(baseMenu, "Edit Trackers...", display._open_tracker_edit)
    
    #create the secondary menu:
    deleteMenu = gtk.Menu()
    def delete_cb(widget, deleteTorrent, deleteData):
      torrentsToDelete = display._get_selected_torrents()
      for torrentHash in torrentsToDelete:
        display.app.remove_download(torrentHash, deleteTorrent, deleteData)
    #add the entries:
    GTKUtils.append_menu_item(deleteMenu, "Just Remove From List", delete_cb, False, False)
    GTKUtils.append_menu_item(deleteMenu, "Torrent File Only", delete_cb, True, False)
    GTKUtils.append_menu_item(deleteMenu, "Data Only", delete_cb, False, True)
    GTKUtils.append_menu_item(deleteMenu, "Both Torrent and Data", delete_cb, True, True)
    #add the submenu:
    self.deleteItem = GTKUtils.append_menu_item(baseMenu, "Delete", deleteMenu)
    
    self.allItems = [self.openItem, self.pauseItem, self.updateItem, self.editItem, self.deleteItem]

    baseMenu.show_all()
    baseMenu.hide()
    self.baseMenu = baseMenu
    
  def update(self,  torrents):
    #if nothing selected, grey out the list
    if not torrents:
      for item in self.allItems:
        item.set_sensitive(False)
      return
    for item in self.allItems:
      item.set_sensitive(True)
    
    #toggle text on pause, resume item using the first torrent selected
    if torrents[0].unpauseflag.isSet():
      self.pauseItem.child.set_label('Pause')
    else:
      self.pauseItem.child.set_label('Resume')
      
class BitTorrentMenuBar(BaseMenuBar.BaseMenuBar):
  def __init__(self, controller, display):
    BaseMenuBar.BaseMenuBar.__init__(self, controller)
    self.display = display
    
  def _show_pane(self, parentWidget, widget):
    self.display.notebook.show_display(widget)
    
  def create_torrent_menu(self):
    self.torrentMenu = TorrentPopupMenu(self.display)
    self.torrentMenuRoot = gtk.MenuItem("Torrent")
    self.torrentMenuRoot.set_submenu(self.torrentMenu)
    def on_dropdown(*args):
      self.torrentMenu.update(self.display.get_selected_downloads())
    self.torrentMenuRoot.connect("activate", on_dropdown)
    self.torrentMenuRoot.show()
    return self.torrentMenu
    
  def create_file_menu(self):
    fileMenu = BaseMenuBar.BaseMenuBar.create_file_menu(self)
    fileMenu.prepend(gtk.SeparatorMenuItem())
    GTKUtils.prepend_menu_item(fileMenu, "Load .torrent", self.display._add_file_cb)
    GTKUtils.prepend_menu_item(fileMenu, "Open Torrent Folder", self.display._open_folder)
    
  def create_view_menu(self):
    viewMenu = BaseMenuBar.BaseMenuBar.create_view_menu(self)
    viewMenu.prepend(gtk.SeparatorMenuItem())
    GTKUtils.prepend_menu_item(viewMenu, "Torrent Priorities", self.display._show_pane, self.display.priorityBox)
    GTKUtils.prepend_menu_item(viewMenu, "Peers", self.display._show_pane, self.display.peerBox)
    GTKUtils.prepend_menu_item(viewMenu, "Bandwidth", self.display._show_pane, self.display.bwGraph)
    return viewMenu
    
  def create_menus(self):
    self.create_torrent_menu()
    return BaseMenuBar.BaseMenuBar.create_menus(self)
    
  def create_menu_bar(self):
    # Create a menu-bar to hold the menus and add it to our main window
    self.menuBar = gtk.MenuBar()
    self.menuBar.show()
    self.menuBar.append(self.fileMenuRoot)
    self.menuBar.append(self.torrentMenuRoot)
    self.menuBar.append(self.viewMenuRoot)
    self.menuBar.append(self.debugMenuRoot)
    self.menuBar.append(self.helpMenuRoot)
    return self.menuBar

class BTUtilityStatusRow(gtk.Frame):
  """I am a frame that contains some nice infos for the user"""
  def __init__(self, btApp, maggicPadding):
    gtk.Frame.__init__(self)
    #bottom row
    self.btApp = btApp
    row = gtk.HBox()
    self.dhtText = gtk.Label('')
    self.dhtText.set_markup('<span size="large">DHT Nodes:  0 (0)</span>')
    self.upText = gtk.Label('')
    initialInfos = (Format.bytes_per_second(0), Format.format_bytes(0))
    self.upText.set_markup('<span size="large">D: %s  %s</span>' % initialInfos)
    self.downText = gtk.Label('')
    self.downText.set_markup('<span size="large">U: %s  %s</span>' % initialInfos)
    self.creditText = gtk.Label('')
    self.creditText.set_markup('<span size="large">Credits: Unknown</span>')
    for item in [self.dhtText, self.upText, self.downText]:
      row.pack_start(item, True, True, 0)
      row.pack_start(gtk.VSeparator(), False, False, 0)
    row.pack_start(self.creditText, True, True, 0)
    self.set_shadow_type(gtk.SHADOW_IN)
    self.add(row)
    
  def update(self, globalDownRate, globalUpRate, globalDownAmount, globalUpAmount):
    if self.btApp.is_ready():
      try:
        nodes = self.btApp.btInstance.dht.get_dht_peers()
      except:
        nodes = ("unknown", "disabled")
      self.dhtText.set_markup('<span>DHT Nodes:  %s (%s)</span>' % nodes)
    globalDownRate = Format.bytes_per_second(globalDownRate)
    globalDownAmount = Format.format_bytes(globalDownAmount)
    self.downText.set_markup('<span>U:  %s  %s</span>' % (globalDownRate, globalDownAmount))
    globalUpRate = Format.bytes_per_second(globalUpRate)
    globalUpAmount = Format.format_bytes(globalUpAmount)
    self.upText.set_markup('<span>D:  %s  %s</span>' % (globalUpRate, globalUpAmount))
    credits = Bank.get().get_total_asset_value()
    self.creditText.set_markup('<span>Credits:  %s (%s)</span>' % (credits, Format.convert_to_gb(credits)))
    
class BTUtilityButtonRow(gtk.Alignment, GlobalEvents.GlobalEventMixin,  GeneratorMixin.GeneratorMixin):
  def __init__(self, btApp, maggicPadding):
    """a button row that controls the bit torrent client and also gives the user some anon info, etc
    buttons trigger events to get to the parent window instead of slef passing"""
    GeneratorMixin.GeneratorMixin.__init__(self)
    gtk.Alignment.__init__(self, 0, 0, 1, 1)
    self._add_events("add_file", "remove_file", "pause_torrent", "toggle_anonymity")
    self.catch_event("settings_changed")
    self.btApp = btApp
   
    self.pausePixbuf = Images.make_icon("pause.png", 16)
    self.resumePixbuf = Images.make_icon("resume.png", 16)
    self.relayOnPixbuf = Images.STOP_RELAY_PIXBUF
    self.relayOnLabel = '<span size="large">Stop Relay</span>'
    self.relayOffPixbuf = Images.START_RELAY_PIXBUF
    self.relayOffLabel = '<span size="large">Start Relay</span>'
    
    #top row of buttons
    self.searchEntry = gtk.Entry(35)
    self.searchEntry.connect("activate", self._search_cb)
    self.searchEntry.set_text("Find a torrent...")
    self.searchEntry.grab_focus()
    # row- note the padding hack
    buttonRow = gtk.HBox(spacing=0) 
    buttonRow.pack_start(self.searchEntry, False, False, 0)
    # search
    self.searchButton = GTKUtils.make_image_button("Search", self._search_cb, "search.png")
    buttonRow.pack_start(self.searchButton, False, False, 0)
    # add
    self.addButton = GTKUtils.make_image_button('Add', self._connect_to_trigger("add_file"), "add.png")
    buttonRow.pack_start(self.addButton, False, False, maggicPadding + 1)
    #remove
    self.removeButton = GTKUtils.make_image_button('Remove', self._connect_to_trigger("remove_file"), "delete.png") 
    buttonRow.pack_start(self.removeButton, False, False, 0)
    # pause/resume
    self.pauseButton = GTKUtils.make_image_button('Pause', self._connect_to_trigger("pause_torrent"), "pause.png")
    buttonRow.pack_start(self.pauseButton, False, False, maggicPadding + 1)
    # relay toggle
    self.relayToggleButton = GTKUtils.make_image_button('relay toggle', self._toggle_relay_cb, "warning.png")
    buttonRow.pack_end(self.relayToggleButton, False, False, 0)
    # anon toggle
    self.anonButton = GTKUtils.make_image_button('Anonymity', self._connect_to_trigger("toggle_anonymity"), "warning.png")
    
    #Normalize button sizes
    #add padding to anon button label
    width = self.anonButton.label.size_request()[0]
    self.anonButton.label.set_size_request(width + maggicPadding, -1)
    buttonRow.pack_end(self.anonButton, False, False, maggicPadding + 1)
    
    #normalize other button sizes
    buttonList = [self.pauseButton, self.removeButton, self.addButton, self.searchButton]
    buttonWidth = maggicPadding + max([button.size_request()[0] for button in buttonList])
    [button.set_size_request(buttonWidth, -1) for button in buttonList]
    self.set_padding(maggicPadding + 3, 0, maggicPadding + 3, maggicPadding + 3)
    self.add(buttonRow)
    
    #fix relay toggle button width
    testLabel = self.relayToggleButton.label
    widths = []
    for text in [self.relayOffLabel, self.relayOnLabel]:
      testLabel.set_markup(text)
      widths.append(self.relayToggleButton.size_request()[0])
    maxWidth = max(widths)
    self.relayToggleButton.set_size_request(maxWidth + maggicPadding, -1)
    
    #initialize the buttons/labels to the correct state (since settings change does a pull :))
    self.on_settings_changed()
    
  def _toggle_relay_cb(self, widget=None):
    """toggles the relay on or off"""
    #accesses the root controllers relay toggle switch in a stupid way
    self.btApp.display.controller.toggle_relay()
    
  def _connect_to_trigger(self, event):
    """simple wrapper for connecting pygtk triggers to our own (external) trigger event handler-
    remains to be seen if this is stupid and something else like slef passing is indeed better
    maybe our events should be reworked so this doesn't need a wrapper?"""
    def trigger(widget, *args):
      self._trigger_event(event, *args)
    return trigger
    
  def _search_cb(self, widget, event=None):
    """launches the browser to do a google search for a torrent-
    it would be nice if this were moved to a reputable torrent site and 
    we returned something within the gui itself"""
    url = "http://google.com/search?"
    searchTerms = self.searchEntry.get_text() + " torrent"
    url += urllib.urlencode({"q" : searchTerms})
    log_msg("torrent search:  %s" % (url), 3, "gui")
    GlobalEvents.throw_event("open_web_page_signal", url, not self.btApp.settings.useTor)
    
  def _set_anonymity_toggle_face(self):
    """changes the anonymity toggle button image/label to the current state"""
    if self.btApp.useTor:
      length = self.btApp.pathLength
    else:
      length = 0
    pixbuf = AnonymityLevelDialog.get_path_length_image(length, 16)
    self.anonButton.image.set_from_pixbuf(pixbuf)
  
  def on_settings_changed(self):
    """toggle buttom images/labels as appropriate"""
    self._set_anonymity_toggle_face()
    self._set_relay_toggle_face()
    
  def _set_relay_toggle_face(self):
    """changes the image and label on the relay toggle button to be the opposite of the current state"""
    if self.btApp.torApp.settings.beRelay:
      self.relayToggleButton.image.set_from_pixbuf(self.relayOnPixbuf)
      self.relayToggleButton.label.set_markup(self.relayOnLabel)
    else:
      self.relayToggleButton.image.set_from_pixbuf(self.relayOffPixbuf)
      self.relayToggleButton.label.set_markup(self.relayOffLabel)
   
  def set_pauseButton(self, resume):
    """changes the pause button image/label to the opposite of the current state"""
    if resume:
      self.pauseButton.image.set_from_pixbuf(self.resumePixbuf)
      self.pauseButton.label.set_markup('<span size="large">Resume</span>')
    else:
      self.pauseButton.image.set_from_pixbuf(self.pausePixbuf)
      self.pauseButton.label.set_markup('<span size="large">Pause</span>')
      
  def change_sensitivity(self, sensitivity):
    self.pauseButton.set_sensitive(sensitivity)

class BitTorrentWindow(TopWindow.Window):
  def __init__(self, controller, app):
    TopWindow.Window.__init__(self, "BitBlinder %s" % (Globals.VERSION),  app)
    self.controller = controller
    
  def create(self):
    self.connect("destroy", self.destroy_cb)
    
    ClientUtil.add_updater(self)
    self.catch_event("no_credits")
    
    def on_launched(button):
      self.start()
    self._start_listening_for_event("launched", self.app, on_launched)
    
    self.popupMenu = TorrentPopupMenu(self)
      
    #everything changes in relation to this magic number
    maggicPadding = 2
    
    self.statusRow = BTUtilityStatusRow(self.app, maggicPadding)
    self.buttonRow = BTUtilityButtonRow(self.app, maggicPadding)
    self._start_listening_for_event("add_file", self.buttonRow, self._add_file_cb)
    self._start_listening_for_event("remove_file", self.buttonRow, self._remove_file_cb) 
    self._start_listening_for_event("pause_torrent", self.buttonRow, self._pause_cb) 
    self._start_listening_for_event("toggle_anonymity", self.buttonRow, self._toggle_anon_cb)
    
    self.rows = {}
    self.curDownload = None
    self.exitDialog = None
    self.trackerEditDialog = None
    
    #create a liststore with one string column to use as the model
                #COLUMNS:
                #0:  File name
    typeList = [gobject.TYPE_STRING,
                #1:  Amount done
                gobject.TYPE_FLOAT,
                #2:  Status
                gobject.TYPE_STRING,
                #3:  ETA
                gobject.TYPE_STRING,
                #4:  Peers
                gobject.TYPE_STRING,
                #5:  Seeds
                gobject.TYPE_STRING,
                #6:  Download Rate
                gobject.TYPE_STRING,
                #7:  Upload Rate
                gobject.TYPE_STRING,
                #8:  Download Amount
                gobject.TYPE_STRING,
                #9:  Upload Amount
                gobject.TYPE_STRING,
                #10:  Upload Amount
                gobject.TYPE_STRING,
                #11:  the hash for the download.  Stored hex-encoded, because nulls mess up gtk
                gobject.TYPE_STRING,
                #12:  is the row visible?
                gobject.TYPE_BOOLEAN
                ]
    self.attrIdx = {}
    self.attrIdx["name"]         = 0
    self.attrIdx["progress"]     = 1
    self.attrIdx["progressMsg"]  = 2
    self.attrIdx["status"]       = 3
    self.attrIdx["peers"]        = 4
    self.attrIdx["seeds"]        = 5
    self.attrIdx["rateUp"]       = 6
    self.attrIdx["rateDown"]     = 7
    self.attrIdx["amountUp"]     = 8
    self.attrIdx["amountDown"]   = 9
    self.attrIdx["copies"]       = 10
    self.attrIdx["hash"]         = 11
    self.attrIdx["visibility"]   = 12
    self.liststore = gtk.ListStore(*typeList)
    COLUMN_NAMES = ["Name", "Progress", "Time Left", "Peers", "Seeds", "Down Rate", "Up Rate", "Down Amt", "Up Amt", "Copies"]
    
    modelfilter, treeview = GTKUtils.make_listview(self.liststore, COLUMN_NAMES)
    GTKUtils.make_text_cell(treeview.columns[0], 0)
    GTKUtils.make_progress_cell(treeview.columns[1], 1, 2)
    for i in range (2, len(COLUMN_NAMES)):
      GTKUtils.make_text_cell(treeview.columns[i], i+1)
    
    #make treeview searchable
    treeview.set_search_column(0)
    #attach the filtermodel and treeview
    treeview.set_model(gtk.TreeModelSort(modelfilter))
    treeview.connect("cursor-changed", self.row_change_cb)
    treeview.connect("button-press-event", self.button_press_cb)
    treeview.connect("button-press-event", self.button_press_cb)
#    treeview.set_size_request(-1, 30)
    treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
    
    self.treeview, self.modelfilter = treeview, modelfilter
    self.modelfilter.set_visible_func(self.visible_cb)
    
    topBox = gtk.VBox()
    topBox.pack_start(self.buttonRow, False, False, 0)
    scrolledTorrentsBox = GTKUtils.make_scroll_box(treeview, hPolicy=gtk.POLICY_AUTOMATIC, vPolicy=gtk.POLICY_AUTOMATIC)
    scrolledTorrentsBoxAlign = gtk.Alignment(0, 0, 1, 1) 
    scrolledTorrentsBoxAlign.set_padding(0, maggicPadding, maggicPadding, maggicPadding)
    scrolledTorrentsBoxAlign.add(scrolledTorrentsBox)

    topBox.pack_start(scrolledTorrentsBoxAlign, True, True, 0)
    
    self.priorityBox = gtk.HBox()
    self.priorityBox.pack_start(gtk.Label("Select a torrent to set the priority for its files."), True, True, 0)
    self.priorityBox.set_border_width(0)
    
    self.peerBox = gtk.HBox()
    self.peerBox.pack_start(gtk.Label("Select a torrent to see your peers in the swarm."), True, True, 0)
    
    self.bwGraph = BWGraph.BWGraph(self.app, root=self)
    self.bwGraph.container.set_size_request(-1, 150)

    self.notebook = ClosableTabNotebook.ClosableTabNotebook()
    self.notebook.set_show_border(True)
    self.notebook.set_border_width(0)
    self.bwGraph.label = gtk.Label("BitTorrent Traffic")
    self.priorityBox.label = gtk.Label("Priorities")
    self.priorityBox.container = self.priorityBox
    self.peerBox.label = gtk.Label("Peers")
    self.peerBox.container = self.peerBox
    self.notebook.show_display(self.bwGraph)
    self.notebook.show_display(self.priorityBox)
    self.notebook.show_display(self.peerBox)
    self.notebook.show_display(self.bwGraph)
    
    alignBottom = gtk.Alignment(0, 0, 1, 1)
    alignBottom.set_padding(0, maggicPadding + 3, maggicPadding + 2, maggicPadding + 2)
    alignBottom.add(self.notebook)
    
    vBoxBottom = gtk.VBox()
    vBoxBottom.pack_start(alignBottom, True, True, 0)
    vBoxBottom.pack_end(self.statusRow, False, False, 0)
    
    vpane = gtk.VPaned()
    
    self.menuBar = BitTorrentMenuBar(self.controller, self)    
    
    frame = gtk.Frame()
    frame.set_shadow_type(gtk.SHADOW_OUT)
    frame.add(topBox)
    
    alignTop = gtk.Alignment(1, 1, 1, 1)
    alignTop.set_padding(10, 0, maggicPadding + 3, maggicPadding + 3)
    alignTop.add(frame)
    
    topContainer = gtk.VBox()
    topContainer.pack_start(self.menuBar.create_menus(), False, False, 0)
    topContainer.pack_start(alignTop, True, True, 0)
    
    vpane.pack1(topContainer, resize=True, shrink=False)
    vpane.pack2(vBoxBottom, resize=False, shrink=False)
    
    self.label = gtk.Label("")
    self.label.set_markup("<span size='x-large' weight='bold'>Bit Twister</span>")
    self.container = vpane
    vpane.set_position(400)
    self.add(self.container)
    self.container.show_all()
    
  def on_no_credits(self):
    if self.app.is_running() and self.app.useTor:
      pass
#      if not self.app.settings.showedOutOfMoneyHint:
#        self.app.settings.showedOutOfMoneyHint = True
#        self.app.settings.save()
#        GUIController.get().show_msgbox("If you disable anonymity, BitTorrent will continue downloading, but you will NOT be anonymous!\n\nClick the button in the upper right to disable anonymity.")
  
  def make_popup_menu(self, newMenu):
    """creates a drop down menu on the system tray icon when right clicked hopefully"""      
#    GTKUtils.append_menu_item(newMenu, "Show BitTorrent Window", self._start_cb)
    submenu = gtk.Menu()
    if not self.app.is_running():
      GTKUtils.append_menu_item(submenu, "Start BitTorrent", self.controller.toggle_bittorrent)
    else:
      GTKUtils.append_menu_item(submenu, "Show BitTorrent Window", self._start_cb)
      GTKUtils.append_menu_item(submenu, "Add Torrent", self._add_file_cb)
      GTKUtils.append_menu_item(submenu, "Open Torrent Folder", self._open_folder)
      GTKUtils.append_menu_item(submenu, "Stop BitTorrent", self.controller.toggle_bittorrent)
    
    menuItem = GTKUtils.make_menu_item_with_picture("BitTorrent", "bb_logo.png")
    menuItem.set_submenu(submenu)
    menuItem.show_all()
    
    newMenu.append(menuItem)

    return submenu
    
  def make_torrent_displays(self, download, torrentData, priority):
    priorityInterface = PriorityDisplay.PriorityDisplay(self.app, hash, torrentData, True)
    priorityInterface.set_priorities(priority)
    priorityInterface.download = download
    peerInterface = PeerDisplay.PeerDisplay(self.app, hash, torrentData)
    peerInterface.download = download
    return (priorityInterface, peerInterface)
    
  def show_tracker_shutdown_prompt(self):
    def callback(dialog, response):
      self.exitDialog = None
      if response == gtk.RESPONSE_OK:
        self.app.force_stop()
    self.exitDialog = GUIController.get().show_msgbox("Bitblinder is sending shutdown events to trackers.  If you are using only public trackers, you can safely exit immediately.", cb=callback, buttons=("Exit Now", gtk.RESPONSE_OK))
    
  def hide_tracker_shutdown_prompt(self):
    if self.exitDialog:
      self.exitDialog.response(gtk.RESPONSE_CANCEL)
      self.exitDialog = None
  
  def _show_pane(self, parentWidget, widget):
    self.notebook.show_display(widget)

  def destroy_cb(self, widget=None, event=None):
    return 
    
  #REFACTOR:  what's the difference/need for this vs _do_quit
  def quit_cb(self, widget, event=None, data=None):
    """called by user clicking the quit button"""
    quitDeferred = self.app.stop()
    quitDeferred.addCallback(self._stop_done)
    quitDeferred.addErrback(self._stop_done)
    
  def launch_cb(self, widget, event=None, data=None):
    self.app.start()
    
  def _stop_done(self, result):
    Basic.validate_result(result, "BitTorrentWindow::_stop_done")
    if not BitBlinder.get().is_running():
      GlobalEvents.throw_event("quit_signal")
    else:
      #are there any other apps using bitblinder?
      for app in BitBlinder.get().applications.values():
        #if there is another app, dont bother shutting down everything
        if app.is_running() and app != Bank.get():
          return
      #ok, check if there is a relay then
      if Tor.get().settings.beRelay:
        #then we should prompt about shutdown
        def callback(dialog, response):
          if response == gtk.RESPONSE_YES:
            self._do_quit()
        msgText = "BitBlinder is acting as a server and help others be anonymous, and earning you more credits!\n\nDo you also want to stop the server?"
        GUIController.get().show_preference_prompt(msgText, "Stop Relay?", callback, "promptAboutRelayQuit")
      else:
        #otherwise shutdown completely:
        self._do_quit()
        
  def _do_quit(self):
    quitDeferred = BitBlinder.get().stop()
    quitDeferred.addCallback(self._quit_done)
    quitDeferred.addErrback(self._quit_done)
    
  def _quit_done(self, result):
    Basic.validate_result(result, "BitTorrentWindow::_quit_done")
    GlobalEvents.throw_event("quit_signal")
      
  def show_settings_cb(self, widget=None):
    self.show_settings({'BitTorrent': self.app})

  def show_help(self, widget):
    GUIController.get().show_msgbox("See our website... and visit the chatroom to let us know if you have questions!", title="Help", width=400)
  
  def visible_cb(self, model, rowIter):
    return model.get_value(rowIter, self.attrIdx["visibility"])
    
  def _toggle_anon_cb(self, widget=None):
    self.anonymityDialog = AnonymityLevelDialog.AnonymityLevelDialog(self.app)
      
  def update_pause_button(self):
    isAnythingRunning = self._any_selected_torrent_running()
    if not isAnythingRunning:
      self.buttonRow.set_pauseButton(True)
    else:
      self.buttonRow.set_pauseButton(False)
    return
  
  def _any_selected_torrent_running(self):
    isAnythingRunning = False
    downloads = self.get_selected_downloads()
    for download in downloads:
      if download.unpauseflag.isSet():
        isAnythingRunning = True
        break
    return isAnythingRunning
  
  def _pause_cb(self, widget, event=None):
    shouldPause = self._any_selected_torrent_running()
    log_msg("torrent pause:  %s" % (shouldPause), 3, "gui")
    downloads = self.get_selected_downloads()
    for download in downloads:
      if shouldPause:
        if download.unpauseflag.isSet():
          download.Pause()
      else:
        if not download.unpauseflag.isSet():
          download.Unpause()
    self.update_pause_button()
      
  def get_selected_downloads(self):
    downloads = []
    if not self.app.is_ready():
      return downloads
    hashes = self._get_selected_torrents()
    for torrentHash in hashes:
      if not self.app.btInstance.downloads.has_key(torrentHash):
        raise Exception("Couldnt find torrent!")
      downloads.append(self.app.btInstance.downloads[torrentHash])
    return downloads
  
  def _add_file_cb(self, widget=None, event=None):
    def on_response(filename):
      self.app.load_torrent(filename)
    GTKUtils.launch_file_selector(on_response, self.app.settings.torrentFolder, ("Torrent Files", "*.torrent"))
    
  def _get_selected_torrents(self):
    torrentList = []
    def foreach_cb(model, path, rowIter):
      torrentHash = model.get_value(rowIter, self.attrIdx["hash"]).decode("hex")
      torrentList.append(torrentHash)
    self.treeview.get_selection().selected_foreach(foreach_cb)
    return torrentList
  
  def _remove_file_cb(self, widget=None, event=None):
    torrentsToDelete = self._get_selected_torrents()
    if len(torrentsToDelete) <= 0:
      return
    def do_remove(dialog, response):
      for torrentHash in torrentsToDelete:
        if response in (0, -4):
          return
        elif response == 1:
          self.app.remove_download(torrentHash, False, False)
        elif response == 2:
          self.app.remove_download(torrentHash, True, False)
        elif response == 3:
          self.app.remove_download(torrentHash, False, True)
        elif response == 4:
          self.app.remove_download(torrentHash, True, True)          
        else:
          raise Exception("Got bad response from delete torrent dialog! %s" % (response))
    GUIController.get().show_msgbox("Would you like to delete both the torrent file and all data that has been downloaded?", title="Delete Torrent?", cb=do_remove, buttons=("Cancel", 0, "Remove from list", 1, "Delete .torrent ONLY", 2, "Delete data ONLY", 3, "Delete .torrent AND data", 4), width=400)
  
  def row_change_cb(self, treeview):
    self.buttonRow.change_sensitivity(True)
    self.update_pause_button()
    
  def freeze(self):
    self.buttonRow.change_sensitivity(False)
    self.treeview.set_sensitive(False)
    
  def unfreeze(self):
    self.buttonRow.change_sensitivity(True)
    self.treeview.set_sensitive(True)
  
  def on_update(self):
    globalDownRate = 0
    globalUpRate = 0
    globalDownAmount = 0
    globalUpAmount = 0
    torrentInfo = None
    if self.app.is_ready():
      torrentInfo = self.app.btInstance.stats(False)
    if not torrentInfo:
      #generate it from the pending downloads:
      torrentInfo = []
      for torrentHash, data in self.app.pendingDownloads.iteritems():
        name = data[0]['metainfo']['info']['name']
        torrentInfo.append([name, "Waiting for Tor...", "0%", 0, 0, "", 0,
        0, 0, 0, 0, 0, "0 seconds", "", torrentHash, 0, 0])
    #log_msg("update: %s" % (len(self.lastData)))
    #mark everything as invisible unless it was in this update:
    visible = {}
    for ref in self.rows.values():
      visible[ref] = False
    #update each of the active torrents:
    for torrent in torrentInfo:
      ( name, status, progress, peers, seeds, seedsmsg, numCopies,
        dnrate, uprate, dnamt, upamt, size, timeLeft, msg, torrentHash, knownSeeds, knownPeers ) = torrent
      globalDownRate += dnrate
      globalUpRate += uprate
      globalDownAmount += dnamt
      globalUpAmount += upamt
      progress = float(progress.replace("%", ""))
      pathname, filename = os.path.split(name)
      #status = status+"|"+seedsmsg+"|"+msg
      progressMsg = "%.0f" % (progress)
      uprate = Format.bytes_per_second(uprate)
      dnrate = Format.bytes_per_second(dnrate)
      upamt = Format.format_bytes(upamt)
      dnamt = Format.format_bytes(dnamt)
      
#      if progress >= 100:
#        status = "Seeding"
        
      try:
        if self.app.btInstance and self.app.btInstance.downloads.has_key(torrentHash):
          if not self.app.btInstance.downloads[torrentHash].unpauseflag.isSet():
            status = "Paused"
        if self.app.forcedStatus:
          status = self.app.forcedStatus
      except Exception, error:
        log_ex(error, "Could not find torrent")
      
      peers = "%s (%s)" % (peers, knownPeers)
      seeds = "%s (%s)" % (seeds, knownSeeds)
      
      if not self.rows.has_key(torrentHash):
        rowIter = self.liststore.append([filename, progress, progressMsg, status, peers, seeds, uprate, dnrate, upamt, dnamt, numCopies, torrentHash.encode("hex"), True])
        self.rows[torrentHash] = gtk.TreeRowReference(self.liststore, self.liststore.get_string_from_iter(rowIter))
      else:
        rowIter = self.liststore[self.rows[torrentHash].get_path()].iter
        self.liststore.set_value(rowIter, self.attrIdx["name"], filename)
        self.liststore.set_value(rowIter, self.attrIdx["progress"], progress)
        self.liststore.set_value(rowIter, self.attrIdx["progressMsg"], progressMsg)
        self.liststore.set_value(rowIter, self.attrIdx["status"], status)
        self.liststore.set_value(rowIter, self.attrIdx["peers"], peers)
        self.liststore.set_value(rowIter, self.attrIdx["seeds"], seeds)
        self.liststore.set_value(rowIter, self.attrIdx["rateUp"], uprate)
        self.liststore.set_value(rowIter, self.attrIdx["rateDown"], dnrate)
        self.liststore.set_value(rowIter, self.attrIdx["amountUp"], upamt)
        self.liststore.set_value(rowIter, self.attrIdx["amountDown"], dnamt)
        self.liststore.set_value(rowIter, self.attrIdx["copies"], numCopies)
        if not self.liststore.get_value(rowIter, self.attrIdx["visibility"]):
          self.liststore.set_value(rowIter, self.attrIdx["visibility"], True)
      visible[self.rows[torrentHash]] = True
    self.statusRow.update(globalDownRate, globalUpRate, globalDownAmount, globalUpAmount)

    #mark everything as invisible unless it was in this update:
    for ref in self.rows.values():
      if not visible[ref]:
        self.liststore.set_value(self.liststore[ref.get_path()].iter, self.attrIdx["visibility"], False)
    if self.curDownload:
      self.curDownload.priorityInterface.update_completion()
      
  def _open_folder(self, widget, *args):
    torrentsToOpen = self._get_selected_torrents()
    pathsToOpen = set()
    if not torrentsToOpen:
      pathsToOpen.add(self.app.settings.torrentFolder)
    else:
      for torrentHash in torrentsToOpen:
        saveAsFile = self.app.btInstance.downloads[torrentHash].rawTorrentData["saveas"]
        pathName, fileName = os.path.split(saveAsFile)
        pathsToOpen.add(pathName)
    #open them all:
    for pathName in pathsToOpen:
      FileHandler.default_file_open(pathName)
      
  def _open_tracker_edit(self, *args):
    if self.trackerEditDialog:
      self.trackerEditDialog.show()
      return
    selectedTorrents = self._get_selected_torrents()
    if len(selectedTorrents) != 1:
      return
    #is an infohash
    selectedTorrent = selectedTorrents[0]
    trackerList = self.app.btInstance.get_trackers(selectedTorrent)
    if trackerList is None:
      return
    def response(trackerList, selectedTorrent=selectedTorrent):
      self._done_editing_trackers(trackerList, selectedTorrent)
    self.trackerEditDialog = TrackerEditDialog.TrackerEditDialog(trackerList, response, self)
    
  def _done_editing_trackers(self, trackerList, selectedTorrent):
    self.trackerEditDialog = None
    if trackerList is None:
      return
    self.app.btInstance.set_trackers(selectedTorrent, trackerList)
      
  def popup_menu(self, activationTime=None):
    selectedTorrents = self.get_selected_downloads()
    self.popupMenu.update(selectedTorrents)
    self.popupMenu.baseMenu.popup(None, None, None, 0, activationTime)
    
  def set_priority_box(self, newChild):
    children = self.priorityBox.get_children()
    for child in children:
      self.priorityBox.remove(child)
    if newChild:
      self.priorityBox.pack_start(newChild, True, True, 0)
      self.priorityBox.show_all()
      
  def set_peer_box(self, newChild):
    children = self.peerBox.get_children()
    for child in children:
      self.peerBox.remove(child)
    if newChild:
      self.peerBox.pack_start(newChild, True, True, 0)
      self.peerBox.show_all()
    
  def button_press_cb(self, treeview, event):
    """called whenever someone clicks on the treeview.
    this function only watches for a right click to launch the drop down menu."""
    if not self.app.is_ready():
      return
      
    if event.button in (1, 3):
      x = int(event.x)
      y = int(event.y)
      vals = treeview.get_path_at_pos(x, y)
      if not vals:
        self._set_current_download(None)
        return True
      path, col, xOffset, yOffset = vals
      rowIter = self.modelfilter.get_iter(path)
      torrentHash = self.modelfilter.get_value(rowIter, self.attrIdx["hash"]).decode("hex")
      if not self.app.btInstance.downloads.has_key(torrentHash):
        raise Exception("Couldnt find torrent!")
      clickedDownload = self.app.btInstance.downloads[torrentHash]
      originalButton = event.button
      
#      log_msg("%s" % (self.app.btInstance.downloads[torrentHash].getFilename()))
      #download.config['responsefile']
      
      if originalButton == 1 or clickedDownload not in (self.get_selected_downloads()):
        if event.button == 3:
          event.button = 1
          #and do the selection early:
          #NOTE:  strange...  calling just select_iter did not work properly (because we later call foreach on the selected, maybe it uses path instead of iter?)
#          self.treeview.get_selection().select_iter(rowIter)
          self.treeview.get_selection().select_path(path)
        self._set_current_download(clickedDownload)
      
      if originalButton == 3:
        self.popup_menu(event.time)
        if event.button == 3:
          return True
      
  def do_priority_prompt(self, torrentHash, data):
    PriorityDialog.PriorityDialog(self.app, torrentHash, data)
    
  def _set_current_download(self, download):
    self.curDownload = download
    if download:
      self.set_priority_box(download.priorityInterface.container)
      self.set_peer_box(download.peerInterface.container)
    else:
      self.set_priority_box(None)
      self.set_peer_box(None)
      self.treeview.get_selection().unselect_all()
