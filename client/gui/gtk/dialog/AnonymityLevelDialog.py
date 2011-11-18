#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Window for controlling FireFox settings"""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.utils import Images
from gui.gtk.utils import WrapLabel
from gui.gtk.utils import GTKUtils
from gui.gtk.dialog import BaseDialog
from core import ClientUtil

PADDING = 10
helperText = [_("No Anonymity: your traffic is not proxied at all and exits directly to the Internet from your local address."),
              _("Speedy: fast but not very anonymous since the single relay knows both who you are and the destination of your traffic."),
              _("Recommended: a decent compromise as it provides some anonymity from the proxies themselves and is reasonably fast."),
              _("The Tor Standard: the strongest anonymity possible but also the slowest and the most expensive.")]
                      
infoText = _("BitBlinder gives you the option of making your traffic more or less anonymous.  \
A tradeoff exists between speed and anonymity, so you should choose whats right for you.")

greaterInfoText = _("     \
The numbers below the slider correspond to the number of relays that your traffic is proxied through.  \
Longer path lengths entail better anonymity but also come at the price of higher latency, lower throughput, and higher cost in credits. \
Specifically, longer paths introduce some latency for each relay and also restrict the throughput to the smallest of the relays in the path.  \
Similarly, you must pay credits to each relay in your path so longer paths are proportionally more expensive.\
\n    \
In terms of anonymity, a path of length two is significantly better than a path of length one since no relay knows the complete picture;  \
the first relay knows who you are, but not the destination of your traffic while the second relay knows the opposite information.  \
A path of length three is most likely better than a length of two though the degree to which is difficult to know.  \
Paths of lenghths longer than three offer no benefit over three and may actually make your traffic less anonymous, so they are not an option.")

def get_path_length_image(pathLen, size=24):
  pixbuf = Images.make_icon(Images.pathLengthToImageName[pathLen], size)
  return pixbuf

class AnonymityLevelDialog(BaseDialog.BaseDialog):
  def __init__(self, app, allowNonanonymousMode=True):
    BaseDialog.BaseDialog.__init__(self, "%s Anonymity Selector" % (app.name), ("ok", "cancel"), None)
    self.app = app
    self.allowNonanonymousMode = allowNonanonymousMode
    
    titleLabel = gtk.Label()
    titleLabel.set_markup("<span size='x-large' weight='bold'>%s Anonymity Selector</span>"  % (self.app.name))
    titleLabel.set_justify(gtk.JUSTIFY_CENTER)
    
    vbox = gtk.VBox()
    vbox.pack_start(titleLabel, False, False, 5)
    infoTextLabel = WrapLabel.WrapLabel(infoText)
    infoTextLabel.set_justify(gtk.JUSTIFY_FILL)
    #keep the label from having no width
    infoTextLabel.set_size_request(300, -1)
    
    infoAndSlider = gtk.VBox()
    infoAndSlider.pack_start(infoTextLabel, False, False, 0)
    instructionBox = self._make_instruction_box()
    infoAndSlider.pack_start(instructionBox, False, False, 0)
    #get the appropriate path length from the app
    if not self.allowNonanonymousMode or self.app.useTor:
      pathLength = self.app.settings.pathLength
    else:
      pathLength = 0
    anonymityBox = self._make_slider_box(pathLength)  
    infoAndSlider.pack_start(anonymityBox, False, False, 0)
    infoAndSlider = GTKUtils.add_padding(infoAndSlider, 5)
    infoAndSlider = GTKUtils.add_frame(infoAndSlider, name='Choose Your Anonymity Level')
    vbox.pack_start(infoAndSlider, False, False, 0)
    
    optionalInfos = self._make_optional_info_box()
    optionalInfos = GTKUtils.add_padding(optionalInfos, 0, 5, 5, 5)
    vbox.pack_start(optionalInfos, False, False, 0)
    
    self.dia.vbox.pack_start(vbox, False, False, 0)
    self.dia.vbox.show_all()
    self.optionalInfosBox.hide()
    self.dia.window.raise_()
    
  def _make_instruction_box(self):
    instructionLabel = gtk.Label()
    
    box = gtk.VBox(spacing=PADDING)

    box.pack_start(instructionLabel, False, False, 0)
    box.show_all()
    return box
    
  def _make_slider_box(self, startingValue):
    if self.allowNonanonymousMode:
      lowestLimit = 0
    else:
      lowestLimit = 1
    adjustment = gtk.Adjustment(value=startingValue, lower=lowestLimit, upper=3, step_incr=1, page_incr=0, page_size=0)
    anonymityScale = gtk.HScale(adjustment)
    anonymityScale.set_digits(0)
    anonymityScale.set_draw_value(True)
    anonymityScale.set_value_pos(gtk.POS_BOTTOM)
    anonymityScale.connect("value_changed", self._on_anonymity_slider_changed)
    self.anonymityScale = anonymityScale
    
    anonLabel = gtk.Label()
    anonLabel.set_markup('<span weight="bold" size="large">Anonymity</span>')
    anonLabel.set_alignment(0, 0)
    anonLabel = GTKUtils.add_padding(anonLabel, 1, 0, 0, 0)
    speedLabel = gtk.Label()
    speedLabel.set_markup('<span weight="bold" size="large">Speed</span>')
    speedLabel.set_alignment(0, 0)
    speedLabel = GTKUtils.add_padding(speedLabel, 1, 0, 0, 0)
    
    sliderBox = gtk.HBox()
    sliderBox.pack_start(speedLabel, False, False, 0)
    sliderBox.pack_start(anonymityScale, True, True, 1)
    sliderBox.pack_start(anonLabel, False, False, 0)
    
    vbox = gtk.VBox()
    vbox.pack_start(sliderBox, True, True, 5)
    
    hbox = gtk.HBox()
    self.AnonymousPerson = gtk.Image()
    self.AnonymousPerson.set_from_pixbuf(get_path_length_image(startingValue))
    hbox.pack_start(self.AnonymousPerson, False, False, 0)
    
    self.helperTextLabel = gtk.Label()
    self.helperTextLabel.set_line_wrap(True)
    self.helperTextLabel.set_justify(gtk.JUSTIFY_FILL)
    hbox.pack_start(self.helperTextLabel, True, True, 5)
    self._normalize_helper_label_height()
    
    vbox.pack_start(hbox, True, True, 5)
    
    self._update_helper_text(startingValue)
  
    return vbox
  
  def _normalize_helper_label_height(self):
    """normalize widths, then heights (or else it breaks)"""
    widths = []
    for text in helperText:
      self.helperTextLabel.set_text(text)
      widths.append(self.helperTextLabel.size_request())
    maxWidth = max(widths)[0]
    self.helperTextLabel.set_size_request(maxWidth, -1)
    
    heights = []
    for text in helperText:
      self.helperTextLabel.set_text(text)
      heights.append(self.helperTextLabel.size_request())
    maxHeight = max(heights)[1]
    self.helperTextLabel.set_size_request(maxWidth, maxHeight)
  
  def _update_helper_text(self, value):
    self.helperTextLabel.set_text(helperText[value])
  
  def _update_anonymous_person(self, value):
    self.AnonymousPerson.set_from_pixbuf(get_path_length_image(value))
    
  def _on_anonymity_slider_changed(self, widget):
    newAnonymityLevel = int(widget.get_value())
    self._update_helper_text(newAnonymityLevel)
    self._update_anonymous_person(newAnonymityLevel)
    
  def _make_optional_info_box(self):
    """shows extra information that will scare away most users"""
    #make entry rows
    moreInfos = WrapLabel.WrapLabel(greaterInfoText)
    moreInfos.set_justify(gtk.JUSTIFY_FILL)
    
    #make a box for hiding
    self.optionalInfosBox = gtk.VBox()
    self.optionalInfosBox.pack_start(moreInfos, False, False, 0)
    self.optionalInfosBox = GTKUtils.add_padding(self.optionalInfosBox, 5)

    #make a frame with a built-in expander for showing and hiding these entry rows
    frame = GTKUtils.add_frame(self.optionalInfosBox, width=0)
    frameWidget = gtk.Expander("Learn More")
    frameWidget.connect("notify::expanded", self._toggle_optional_infos)
    frame.set_label_widget(frameWidget)
    return frame
    
  def _toggle_optional_infos(self, expander, param_spec):
    if expander.get_expanded():
      self.optionalInfosBox.show_all()
    else:
      self.optionalInfosBox.hide()
    self.dia.resize(*self.dia.size_request())
    
  def on_response(self, responseId):
    if responseId == gtk.RESPONSE_OK:
      newHops = int(self.anonymityScale.get_value())
      if self.allowNonanonymousMode:
        self.app.settings.useTor = newHops != 0
      if newHops > 0:
        self.app.settings.pathLength = newHops
      self.app.settings.on_apply(self.app, "")

