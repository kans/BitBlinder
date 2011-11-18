#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""GUI for generic socks applications"""

import gtk
import gobject

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from gui import GUIController
from gui.gtk.utils import GTKUtils
from gui.gtk.widget import BaseMenuBar
from gui.gtk.display import BWGraph
from gui.gtk.window import TopWindow
from core import ClientUtil
from core import BWHistory
from Applications import Application
from Applications import Tor
from Applications import BitBlinder
from gui.gtk.display import SettingsDisplay
from gui.gtk.display import BankDisplay
from gui.gtk.display import CircuitList
from gui.gtk.display import Console
from gui.gtk.widget import ClosableTabNotebook
from gui.gtk.widget import BaseMenuBar

class SocksServerMenuBar(BaseMenuBar.BaseMenuBar):
  def __init__(self, controller, display):
    BaseMenuBar.BaseMenuBar.__init__(self, controller)
    self.display = display
    
  def _show_pane(self, parentWidget, widget):
    self.display.notebook.show_display(widget)
    
  def create_debug_menu(self):
    debugMenu = BaseMenuBar.BaseMenuBar.create_debug_menu(self)
    debugMenu.prepend(gtk.SeparatorMenuItem())
    GTKUtils.prepend_menu_item(debugMenu, "Console", self._show_pane, self.display.console)
    GTKUtils.prepend_menu_item(debugMenu, "Bank", self._show_pane, self.display.bankDisplay)
    return debugMenu
    
  def create_view_menu(self):
    viewMenu = BaseMenuBar.BaseMenuBar.create_view_menu(self)
    viewMenu.prepend(gtk.SeparatorMenuItem())
    GTKUtils.prepend_menu_item(viewMenu, "Circuit List", self._show_pane, self.display.circuitList)
    GTKUtils.prepend_menu_item(viewMenu, "Bandwidth Graph", self._show_pane, self.display.bwGraph)
    return viewMenu

class SocksClientWindow(TopWindow.Window):
  def __init__(self, root, bbApp):
    TopWindow.Window.__init__(self, "SOCKS Clients %s" % (Globals.VERSION),  bbApp)
    self.root = root
    
  def create(self):
    #Stores references to the program rows
    self.rows = {}
    self.selectedApp = None
    
    ClientUtil.add_updater(self)
    
    #create a liststore with one string column to use as the model
                #COLUMNS:
                #0:  Program name
    typeList = [gobject.TYPE_STRING,
                #1:  Number of hops
                gobject.TYPE_INT,
                #2:  Download Rate
                gobject.TYPE_STRING,
                #3:  Upload Rate
                gobject.TYPE_STRING,
                #4:  Coins spent
                gobject.TYPE_INT
                ]
    self.attrIdx = {}
    self.attrIdx["name"]         = 0
    self.attrIdx["numHops"]      = 1
    self.attrIdx["rateDown"]     = 2
    self.attrIdx["rateUp"]       = 3
    self.attrIdx["numCredits"]     = 4
    self.liststore = gtk.ListStore(*typeList)
    COLUMN_NAMES = ['Name','Anonymity Level', "Down Rate", "Up Rate", "Credits Used"]
    viewName = "Anonymous Programs"

    modelfilter, treeview = GTKUtils.make_listview(self.liststore, COLUMN_NAMES)
    for i in range (0, len(COLUMN_NAMES)):
      GTKUtils.make_text_cell(treeview.columns[i], i)
    
    #make treeview searchable
    treeview.set_search_column(0)
    #attach the filtermodel and treeview
    treeview.set_model(gtk.TreeModelSort(modelfilter))
#    treeview.connect("row-activated", self.row_activate_cb)
    treeview.connect("cursor-changed", self.row_change_cb)
    treeview.connect("button-press-event", self.button_press_cb)
    treeview.set_size_request(-1, 80)
    treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
      
    def make_button(text, cb, picFile):
      return GTKUtils.make_image_button(text, cb, picFile)
    
    bottomRow = gtk.HBox()
    self.removeButton = make_button('Stop', self.stop_cb, ClientUtil.get_image_file("stop.png"))
    bottomRow.pack_start(self.removeButton, False, False, 1)
    self.anonEntry = SettingsDisplay.make_entry("anonymity level", 1)
    self.anonEntry.connect_user_changed(self.toggle_anon_cb)
    bottomRow.pack_end(self.anonEntry.get_gtk_element(), False, False, 5)
    label = gtk.Label("")
    label.set_markup('<span size="large" weight="bold">Number of Hops: </span>')
    bottomRow.pack_end(label, False, False, 5)
    
    self.treeview, self.modelfilter = treeview, modelfilter
#    self.modelfilter.set_visible_func(self.visible_cb)

    self.bankDisplay = BankDisplay.BankDisplay()
    self.circuitList = CircuitList.CircuitList()
    self.console = Console.Console(Tor.get())

    self.bwGraph = BWGraph.BWGraph(BWHistory.localBandwidth, root=self)
    self.bwGraph.container.set_size_request(-1, 200)
    self.bwGraphLabel = gtk.Label("All Traffic")
    
    self.notebook = ClosableTabNotebook.ClosableTabNotebook()
    self.notebook.show_display(self.bwGraph)
    
    notebookAlign = gtk.Alignment(0, 0, 1, 1)
    notebookAlign.set_padding(5, 5, 0, 5)
    notebookAlign.add(self.notebook)
    
    self.topBox = gtk.VBox()
    self.topBox.pack_start(GTKUtils.make_scroll_box(treeview, hPolicy=gtk.POLICY_AUTOMATIC, vPolicy=gtk.POLICY_AUTOMATIC), True, True, 10)
    self.topBox.pack_start(bottomRow, False, True, 10)
    
    alignBottom = gtk.Alignment(1, 1, 1, 1)
    alignBottom.set_padding(10, 3, 1, 1)
    alignBottom.add(notebookAlign)
    vpane = gtk.VPaned()
     
    frame = gtk.Frame()
    frame.set_shadow_type(gtk.SHADOW_OUT)
    frame.add(self.topBox)
    
    alignTop = gtk.Alignment(1, 1, 1, 1)
    alignTop.set_padding(10, 10, 7, 7)
    alignTop.add(frame)
    
    topContainer = gtk.VBox()
    topContainer.pack_start(alignTop, True, True, 0)
    
    vpane.pack1(topContainer, resize=True, shrink=False)
    vpane.pack2(alignBottom, resize=True, shrink=False)
    vpane.set_position(400)
    
    self.label = gtk.Label("")
    self.label.set_markup("<span size='x-large' weight='bold'>Applications</span>")
    self.container = vpane
    
    self.catch_event("settings_changed")
    
    self.menuBar = SocksServerMenuBar(self.root, self)
    
    vbox = gtk.VBox() 
    vbox.pack_start(self.menuBar.create_menus(), False, False, 0)
    vbox.pack_start(self.container, True, True, 0)
    self.add(vbox)
    vbox.show_all()
    
  def on_settings_changed(self):
    if self.selectedApp:
      self.anonEntry.set_value(self.selectedApp.settings.pathLength)
    else:
      self.anonEntry.set_value(self.app.settings.pathLength)
    
  def toggle_anon_cb(self, widget):
    def apply(app):
      app.settings.pathLength = self.anonEntry.get_value()
      app.settings.on_apply(app, "")
      app.settings.save()
    app = self.selectedApp
    if not app:
      apply(self.app)
      return
    def cb(dialog, response, app=app):
      if response == gtk.RESPONSE_OK:
        apply(app)
      elif response in (gtk.RESPONSE_CANCEL, gtk.RESPONSE_DELETE_EVENT):
        self.anonEntry.set_value(app.settings.pathLength)
      else:
        raise Exception("Unknown response:  %s" % (response))
    if app.settings.pathLength != self.anonEntry.get_value():
      if app.is_running():
        GUIController.get().show_msgbox("Changing the mode will restart %s.  Ok?" % (app.name), title="Restart?", cb=cb, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
      else:
        cb(None, gtk.RESPONSE_OK)
        
  def on_update(self):
    #update the client display if it's visible:
    if self.is_visible():
      updatedApps = set()
      appInfos = BitBlinder.get().get_app_info()
      #update each socks applications:
      for appInfo in appInfos:
        (appName, numHops, dnrate, uprate, numCredits) = appInfo
        #insert a row for the app if it doesnt exist:
        if appName not in self.rows:
          iter = self.liststore.append(appInfo)
          self.rows[appName] = gtk.TreeRowReference(self.liststore, self.liststore.get_string_from_iter(iter))
        #update the information in the row
        else:
          iter = self.liststore[self.rows[appName].get_path()].iter
          self.liststore.set(iter, self.attrIdx["rateUp"], uprate, 
                             self.attrIdx["rateDown"], dnrate, 
                             self.attrIdx["numHops"], numHops,
                             self.attrIdx["numCredits"], numCredits)
        #note thate we've updated this row:
        updatedApps.add(appName)
      #remove all apps that were not updated:
      for appName in self.rows.keys():
        if appName not in updatedApps:
          treeRow = self.rows[appName]
          iter = self.liststore[treeRow.get_path()].iter
          self.liststore.remove(iter)
          del self.rows[appName]
                         
  def stop_cb(self, widget, event=None):
    if not self.selectedApp:
      return
    self.selectedApp.stop()
    
  def row_change_cb(self, treeview):
    return
    
  def make_popup_menu(self, newMenu):
    """creates a drop down menu on the system tray icon when right clicked"""
  
    submenu = gtk.Menu()
    if not self.app or not self.app.is_running() or not self.is_visible():
      GTKUtils.append_menu_item(submenu, "Show SOCKS Interface", self.toggle_window_state)
    else:
      GTKUtils.append_menu_item(submenu, "Hide SOCKS Interface", self.toggle_window_state)
      
    header = GTKUtils.make_menu_item_with_picture('SOCKS Interface', "network.png")
    header.set_submenu(submenu)
    header.show_all()
    
    newMenu.append(header)

    return submenu
    
  def popup_menu(self, activationTime=None):
    """"""
    #create the first menu:
    baseMenu = gtk.Menu()
    if self.selectedApp:
      GTKUtils.append_menu_item(baseMenu, "Stop", self.stop_cb)
    
    #create the secondary menu:
    pathLenMenu = gtk.Menu()
    def path_len_cb(widget, pathLen):
      self.anonEntry.set_value(pathLen)
    #add the entries:
    GTKUtils.append_menu_item(pathLenMenu, "1 (Fastest)", path_len_cb, 1)
    GTKUtils.append_menu_item(pathLenMenu, "2 (Normal)", path_len_cb, 2)
    GTKUtils.append_menu_item(pathLenMenu, "3 (Best Anonymity)", path_len_cb, 3)
    #add the submenu:
    if self.selectedApp:
      GTKUtils.append_menu_item(baseMenu, "Set Path Length", pathLenMenu)
    else:
      GTKUtils.append_menu_item(baseMenu, "Set Default Path Length", pathLenMenu)

    baseMenu.show_all()
    baseMenu.popup(None, None, None, 3, activationTime)

  def set_graph_data_source(self, source):
    self.bwGraph.dataSource = source
    if hasattr(source, "__class__") and issubclass(source.__class__, Application.Application):
      self.bwGraphLabel.set_text(source.name + " Traffic")
    else:
      self.bwGraphLabel.set_text("All Traffic")
    
  def button_press_cb(self, treeview, event):
    """called whenever someone clicks on the treeview.
    this function only watches for a right click to launch the drop down menu."""
    if not self.app.is_running():
      return
      
    if event.button in (1, 3):
      x = int(event.x)
      y = int(event.y)
      vals = treeview.get_path_at_pos(x, y)
      if not vals:
        self.selectedApp = None
        self.set_graph_data_source(BWHistory.localBandwidth)
        self.treeview.get_selection().unselect_all()
        return True
      path, col, xOffset, yOffset = vals
      iter = self.modelfilter.get_iter(path)
      appName = self.modelfilter.get_value(iter, self.attrIdx["name"])
      if not self.app.applications.has_key(appName):
        raise Exception("Couldnt find Application %s!" % (appName))
      newApp = self.app.applications[appName]
      originalButton = event.button

      if originalButton == 1 or newApp != self.selectedApp:
        if event.button == 3:
          event.button = 1
          #and do the selection early:
          #NOTE:  strange...  calling just select_iter did not work properly (because we later call foreach on the selected, maybe it uses path instead of iter?)
#          self.treeview.get_selection().select_iter(iter)
          self.treeview.get_selection().select_path(path)
        self.selectedApp = newApp
        self.set_graph_data_source(newApp)
      
      if originalButton == 3:
        self.popup_menu(event.time)
        if event.button == 3:
          return True

    
