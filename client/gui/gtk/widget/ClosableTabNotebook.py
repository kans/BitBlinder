#!/usr/bin/env python
#Copyright 2008-2009 InnomiNet
"""An improved GTK Notebook class that puts little close buttons on tabs.
Adapted from here:
http://coding.debuntu.org/python-gtk-how-set-gtk.notebook-tab-custom-widget"""

import types

import gtk

from core import ClientUtil

class ClosableTabNotebook(gtk.Notebook):
  """A gtk.Notebook that makes little close buttons next to tabs."""
  def __init__(self):
    gtk.Notebook.__init__(self)
    #set the tab properties
    self.set_property('homogeneous', True)
    #we do not show the tab if there is only one tab i total
    self.set_property('show-tabs', False)
    
  def show_display(self, display=None):
    pageNum = self.page_num(display.container)
    if pageNum == -1:
      self._create_tab(display.container, display.label)
      display.container.show_all()
    else:
      self.set_current_page(pageNum)

  def _create_tab(self, child, label):
    """Create and select a new tab with the given element and title text"""
    self.append_page(child)
    
    #we want to show the tabs if there is more than 1
    numPages = self.get_n_pages()
    if numPages > 1:
      self.set_property('show-tabs', True)
      
    #make the label for the tab title
    if type(label) == types.StringType:
      label = gtk.Label(label)
    label.show()
    tabLabel = self._create_tab_label(label, child)
    
    #put the child into the tab
    self.set_tab_label_packing(child, True, True, gtk.PACK_START)
    self.set_tab_label(child, tabLabel)
    self.set_tab_reorderable(child, True)
    
    #select the new tab
    self.set_current_page(numPages-1)

  def _create_tab_label(self, label, child):
    
    text = label.get_text()
    label.set_markup('<span>%s</span>' % text)
    image = gtk.Image()
    imagePath = ClientUtil.get_image_file('square_x.png')
    pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(imagePath, 8, 8)
    image.set_from_pixbuf(pixbuf)
#    image.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)
#    image.set_size_request(6, 6)
    closeButton = gtk.Button()
    closeButton.set_name("LittleButton")
    closeButton.connect("clicked", self._close_tab, child)
    closeButton.set_image(image)
    closeButton.set_relief(gtk.RELIEF_NONE)
    sizeRequest = closeButton.size_request()
    closeButton.show()
    
    box = gtk.HBox()
    box.pack_start(label, True, True)
    box.pack_end(closeButton, False, False)
    box.show()
    
    return box

  def _close_tab(self, widget, child):
    pageNum = self.page_num(child)
    if pageNum != -1:
      self.remove_page(pageNum)
      if self.get_n_pages() == 1:
        self.set_property('show-tabs', False)
        

