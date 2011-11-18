#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Settings/preferences for each Application class.  Handles saving, loading, and validating."""

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.events import GlobalEvents
from Applications import Settings

class ApplicationSettings(Settings.Settings):
  """All normal applications should derive from this so it can easily be saved
  and loaded.  Just store settings as attributes of the child object."""

  def __init__(self):
    """Set the default values of all your settings.  Be sure that child classes call this parent method."""
    Settings.Settings.__init__(self)
    self.pathLength = self.add_attribute("pathLength", 2, (1, 3), "Number of Hops", 
"""<span weight='bold'>1:</span>  Hides IP address.  Pretty fast.

<span weight='bold'>2:</span>  Hides IP address.  Protects against single bad relay.  Slow.

<span weight='bold'>3:</span>  Hides IP address.  Best possible protection.  Very slow.
""", isVisible=False)
    
  def apply_anon_mode(self, app):
    """Toggle which anonymity mode (how many hops) we are currently using, restart applications as necessary."""      
    if self.pathLength != app.pathLength:
      app.pathLength = self.pathLength
      if app.is_ready():
        app.restart()
      self.save()
      GlobalEvents.throw_event("settings_changed")
      
  def on_apply(self, app, category):
    self.apply_anon_mode(app)
    return True
    