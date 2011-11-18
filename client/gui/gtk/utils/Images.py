#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""The images that we load from files"""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core import ClientUtil

def make_icon(fileName, iconSize=24):
  return gtk.gdk.pixbuf_new_from_file_at_size(ClientUtil.get_image_file(fileName), iconSize, iconSize)
  
RED_CIRCLE          = make_icon("red.png")
YELLOW_CIRCLE       = make_icon("yellow.png")
GREEN_CIRCLE        = make_icon("green.png")
GREY_CIRCLE         = make_icon("grey.png")
START_RELAY_PIXBUF  = make_icon("power_off.png", 16)
STOP_RELAY_PIXBUF   = make_icon("power_on.png", 16)

#: appropriate image to use with a path of given length 0 - 3
pathLengthToImageName =  ["identity_red.png",
                          "identity_yellow.png",
                          "identity.png",
                          "identity_teal.png"]
