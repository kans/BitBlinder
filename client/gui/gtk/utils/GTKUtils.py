#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Misc. GUI functions"""

import types
import os
import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.system import System
from common.events import GlobalEvents
from gui.gtk.utils import WrapLabel
from gui.gtk.utils import Images
from core import ClientUtil

def is_visible(element):
  if not element.get_property("visible"):
    return False
  #also have to check if we are some remote child of a Notebook, and if so, if the right tab is selected:
  child = element
  parent = element.get_parent()
  #if this hasnt even been added yet, it's obviously not visible
  if parent == None:
    return False
  while parent != None:
    if not parent.get_property("visible"):
      return False
    if issubclass(type(parent), gtk.Notebook):
      if parent.page_num(child) == parent.get_current_page():
        return True
      else:
        return False
    child = parent
    parent = parent.get_parent()
  #well, I guess we must be visible!
  return True
  
def refit(widgetWithNewSize):
  #the parent widget must be resized to get rid of excess space
  parent = widgetWithNewSize.get_parent()
  if not parent:
    log_msg('%s is an orphan :(' % (widgetWithNewSize), 4)
    return
    
  #need to go up the food chain until we reach some parent that has a resize method
  hasResizeInterface = None
  while parent != None:
    hasResizeInterface = getattr(parent, "resize", None)
    #sweet, we found one
    if hasResizeInterface:
      break
    #oh noes, try again
    parent = parent.get_parent()
  #was it turtles all the way down?
  if hasResizeInterface:
    parent.resize(*parent.size_request())
  else:
    log_msg('Could not resize a parent widget, %s is looking stupid in the mean time' % (widgetWithNewSize), 4)


def make_listview(liststore, columnNames):
  modelfilter = liststore.filter_new()
  treeview = gtk.TreeView()
  #create the TreeViewColumns to display the data
  treeview.columns = []
  for item in columnNames:
    column = gtk.TreeViewColumn(item)
    treeview.columns.append(column)
    treeview.append_column(column)
  return modelfilter, treeview

def make_pic_cell(column, columnDataIdx, make_pb):
  column.picCell = gtk.CellRendererPixbuf()
  column.pack_start(column.picCell, True)
  column.set_cell_data_func(column.picCell, make_pb, columnDataIdx)
  #set properties to make the column interact intuitively.
  column.set_properties(reorderable=True, expand=True)
  
#TODO:  had to disable sorting because it messes up our custom row selection function for some unknown reason...  get_path_at_pos doesnt play nicely with sorting?
#we could fix it by moving away from using such a custom selection function probably...
def make_text_cell(column, columnTextIdx, formatFunc=None, makeSortable=False):
  column.textCell = gtk.CellRendererText()
  column.pack_start(column.textCell, True)
  #column.set_attributes(column.textCell, text=columnTextIdx, foreground=self.FG_COLOR_COLUMN, background=self.BG_COLOR_COLUMN)
  if not formatFunc:
    column.set_attributes(column.textCell, text=columnTextIdx)
  else:
    def set_text(tvcolumn, cell, model, iter, columnTextIdx):
      val = model.get_value(iter, columnTextIdx)
      cell.set_property('text', formatFunc(val))
    column.set_cell_data_func(column.textCell, set_text, columnTextIdx)
  #this acts as a macro to set a bunch of properties that make this column sortable
  if makeSortable:
    column.set_sort_column_id(columnTextIdx)
  #set properties to make the column interact intuitively.
  column.set_properties(reorderable=True, expand=True, clickable=True)
  column.set_resizable(True)
  
def make_progress_cell(column, valueNum, textNum=None):
  column.progressCell = gtk.CellRendererProgress()
  column.pack_start(column.progressCell, True)
  def cell_data_progress(column, cell, model, row):
    value = model.get_value(row, valueNum)
    if textNum:
      text = model.get_value(row, textNum)
    else:
      text = "%.2f%%" % (value)
    cell.set_property("value", int(value))
    cell.set_property("text", text)
  column.set_cell_data_func(column.progressCell, cell_data_progress)
  #this acts as a macro to set a bunch of properties that make this column sortable
  #column.set_sort_column_id(valueNum)
  #set properties to make the column interact intuitively.
  column.set_properties(reorderable=True, expand=False, clickable=True)
  #column.set_min_width(10)
  #column.set_resizable(True)
  
def make_toggle_cell(column, valueIdx):
  def set_checkmark(tvcolumn, cell, model, rowIter, valueIdx):
    val = model.get_value(rowIter, valueIdx)
    cell.set_property('active', val != -1)
  column.toggleCell = gtk.CellRendererToggle()
  column.toggleCell.set_property('activatable', True)
  #column.toggleCell.connect('toggled', self.row_toggled_cb)
  column.pack_start(column.toggleCell, True)
  column.set_cell_data_func(column.toggleCell, set_checkmark, valueIdx)
  #set properties to make the column interact intuitively.
  column.set_properties(reorderable=True, expand=True, clickable=True)

def make_html_link(text, url, size="small"):
  def realize_cb(widget, event=None):
    widget.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND1))
  def show_website(widget, event):
    #print widget
    widget.label.set_markup('<span underline="single" foreground="%s" size="%s">%s</span>' % ("purple", size, text))
    GlobalEvents.throw_event("open_web_page_signal", widget.url, True)
  button = gtk.EventBox()
  button.url = url
  button.set_events(gtk.gdk.BUTTON_PRESS_MASK)
  button.connect("button_release_event", show_website)
  button.label = gtk.Label("")
  box = gtk.HBox()
  button.add(box)
  button.connect("realize", realize_cb)  
  box.pack_start(button.label, True, True, 0)
  button.label.set_markup('<span underline="single" foreground="%s" size="%s">%s</span>' % ("blue", size, text))
  return button

def make_scroll_box(box, hPolicy=gtk.POLICY_NEVER, vPolicy=gtk.POLICY_AUTOMATIC):
  scrolled_window = gtk.ScrolledWindow()
  scrolled_window.set_border_width(5)
  scrolled_window.set_policy(hPolicy, vPolicy)
  hasNativeScrolling = False
  for klass in (gtk.TextView, gtk.TreeView, gtk.Layout):
    if issubclass(type(box), klass):
      hasNativeScrolling = True
      break
  if hasNativeScrolling:
    scrolled_window.add(box)
  else:
    scrolled_window.add_with_viewport(box)
  return scrolled_window

#def add_frame(box, type=gtk.SHADOW_IN, width=5):
def add_frame(box, shadingType=gtk.SHADOW_ETCHED_OUT, width=5, name=None):
  frame = gtk.Frame()
  frame.add(box)
  frame.set_shadow_type(shadingType)
  frame.set_border_width(width)
  if name != None:
    frame.set_label(name)
  return frame
  
def add_padding(box, paddingTopOrAll, paddingBottom=None, paddingLeft=None, paddingRight=None):
  align = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
  if paddingBottom and paddingLeft and paddingRight:
    align.set_padding(paddingTopOrAll, paddingBottom, paddingLeft, paddingRight)
  else:
    align.set_padding(paddingTopOrAll, paddingTopOrAll, paddingTopOrAll, paddingTopOrAll)
  align.add(box)
  return align

def make_text(text):
  label = WrapLabel.WrapLabel("")
  label.set_selectable(True)
  label.set_markup(text)
  return label

def make_image_button(labelText, callback, fileName, vertical=False, makeButton=True, iconSize=16):
  """Make a button that consists of an image and a label (joined either vertically or horizontally)"""
  if makeButton:
    button = gtk.Button()
  else:
    button = gtk.EventBox()
  if labelText != None:
    label = gtk.Label("")
    label.set_markup('<span size="large">%s</span>' % (labelText))
    button.label = label
  image = gtk.Image()
  #get the full path
  filePath = ClientUtil.get_image_file(fileName)
  pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(filePath, iconSize, iconSize)
  image.set_from_pixbuf(pixbuf)
  box = None
  if vertical:
    box = gtk.VBox()
  else:
    box = gtk.HBox()
  button.add(box)
  box.pack_start(image, False, False, 0)
  if labelText != None:
    align = gtk.Alignment(xalign=0.5, yalign=0.5, xscale=1.0, yscale=0.0)
    align.add(label)
    align.set_padding(1, 1, 1, 1)
    box.pack_start(align, True, False, 0)
  if callback:
    if makeButton:
      button.connect('clicked', callback)
    else:
      button.set_events(gtk.gdk.BUTTON_PRESS_MASK)
      button.connect("button_press_event", callback)
  button.show_all()
  button.image = image
  return button

def launch_file_selector(callback, defaultFile=None, filterParams=None, doSave=False):
  def on_response(dialog, response_id):
    if response_id == gtk.RESPONSE_OK:
      filename = System.decode_from_filesystem(dialog.get_filename())
      callback(filename)
    dialog.destroy()
  if filterParams:
    action = gtk.FILE_CHOOSER_ACTION_OPEN
    if doSave:
      action = gtk.FILE_CHOOSER_ACTION_SAVE
  else:
    action = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
    if doSave:
      action = gtk.FILE_CHOOSER_ACTION_CREATE_FOLDER
  dialog = gtk.FileChooserDialog("Open..",
                           None,
                           action,
                           (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                            gtk.STOCK_OPEN, gtk.RESPONSE_OK))
  if filterParams:
    fileFilter = gtk.FileFilter()
    fileFilter.set_name(filterParams[0])
    fileFilter.add_pattern(filterParams[1])
    dialog.add_filter(fileFilter)  
  dialog.set_default_response(gtk.RESPONSE_OK)
  dialog.set_current_folder(os.getcwdu())
  if not defaultFile:
    defaultFile = os.getcwdu()
  filename = os.path.abspath(defaultFile)
  dialog.set_filename(filename)
  if not os.path.exists(filename):
    os.path.split(filename)
    dialog.set_current_name(os.path.split(filename)[1])
  dialog.set_select_multiple(False)
  dialog.connect("response", on_response)
  dialog.show_all()
  
def append_menu_separator(menu):
  return _add_menu_separator(menu, False)
  
def prepend_menu_separator(menu):
  return _add_menu_separator(menu, True)
  
def _add_menu_separator(menu, isFront):
  sep = gtk.SeparatorMenuItem()
  sep.show()
  if isFront:
    menu.prepend(sep)
  else:
    menu.append(sep)
  return sep
  
def append_menu_item(menu, entry, action, *args, **kwargs):
  """Add an item (with a callback) or another menu to the end of the menu"""
  return _add_menu_item(menu, False, entry, action, *args, **kwargs)
  
def prepend_menu_item(menu, entry, action, *args, **kwargs):
  """Add an item (with a callback) or another menu to the start of the menu"""
  return _add_menu_item(menu, True, entry, action, *args, **kwargs)
  
def _add_menu_item(menu, isFront, entry, action, *args, **kwargs):
  """Add an item (with a callback) or another menu to the menu"""
  if type(entry) == types.StringType:
    newItem = gtk.MenuItem(entry)
  else:
    newItem = gtk.MenuItem()
    newItem.add(entry)
    entry.show()
  if isFront:
    menu.prepend(newItem)
  else:
    menu.append(newItem)
  if type(action) is gtk.Menu:
    newItem.set_submenu(action)
  elif action != None:
    newItem.connect("activate", action, *args, **kwargs)
  newItem.show()
  return newItem

def make_menu_item_with_picture(name, imagePath):
  """makes a menu entry with an image and a label in it"""
  image = gtk.Image()
  pixbuf = Images.make_icon(imagePath, 24)
  image.set_from_pixbuf(pixbuf)
  image.set_size_request(35, 24)
  image.set_alignment(0, .5)
  label = gtk.Label()
  label.set_alignment(0, .5)
  label.set_markup("<span weight='bold'>%s</span>" % (name))
  box = gtk.HBox(spacing=0)
  box.pack_start(image, False, False, 0)
  box.pack_start(label, False, False, 0)
  header = gtk.MenuItem()
  header.add(box)
  header.show_all()
  return header
