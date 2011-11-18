#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Present the user with a welcome message.  Ask them nicely to be a relay!  :)"""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.utils import WrapLabel
from gui.gtk.dialog import BaseDialog
from core import ClientUtil

WELCOME_TEXT = "Welcome to the Beta!\n\nBitBlinder works by allowing peers to share some of their bandwidth with each other.  This dialog will guide you through the process of setting up a relay to help your peers.  You can cancel and do it later (by clicking Start Relay.)"

class WelcomeDialog(BaseDialog.BaseDialog):
  def __init__(self, root):
    BaseDialog.BaseDialog.__init__(self, "Welcome!", ("ok",), None)
    self.root = root
    width = 200
    padding = 20

    imagePath = ClientUtil.get_image_file("bb_logo.png")
    pixbuf = gtk.gdk.pixbuf_new_from_file(imagePath)
    pixbuf = pixbuf.scale_simple(width, int(width * 0.553), gtk.gdk.INTERP_TILES)
    
    image = gtk.Image()
    image.set_from_pixbuf(pixbuf)
    
    vBox = gtk.VBox()
    vBox.pack_start(image, False, False, padding-3)
    welcomeLabel = gtk.Label(WELCOME_TEXT)
    welcomeLabel.set_line_wrap(True)
    welcomeLabel.set_justify(gtk.JUSTIFY_FILL)
    welcomeLabel.set_size_request(width, -1)
    align = gtk.Alignment(0, 0, 1, 1)
    align.set_padding(0, padding, padding, padding)
    align.add(welcomeLabel)
    vBox.pack_start(align, False, False, 0)
    
    frame = gtk.Frame()
    frame.add(vBox)
    
    widgetHack = gtk.EventBox()
    widgetHack.add(frame)
    widgetHack.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))

    self.dia.vbox.pack_start(widgetHack, True, True, 0)
    self.dia.show_all()

  def on_response(self, responseId):
    if responseId == gtk.RESPONSE_OK:
      self.root.start_server_setup()
    
