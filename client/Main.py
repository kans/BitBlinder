#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Call this script with the appropriate arguments to start BitBlinder"""
      
if __name__ == '__main__':
  #NOTE:  M2Crypto must be imported first because it causes crashes if imported after OpenSSL (which we don't use, but Twisted tries to import)
  import M2Crypto
  from core import Logging
  from common import Globals
  Globals.logger = Logging.Logger()
  try:
    #run startup code.  This will exit if we're not supposed to be starting BitBlinder 
    #(for example, when passing arguments to an existing instance)
    from core import Startup
    Startup.startup()

    #if we're still running, it's time to start the main class.
    from Applications import MainLoop
    mainApp = MainLoop.MainLoop()
    mainApp.start()
    #this call blocks and calls gtk.main or reactor.run as appropriate
    mainApp.main()
    #do any necessary cleanup before we exit
    mainApp.cleanup()
  #this will prompt the user in an appropriate fashion for their OS if they want to submit an error report
  #most exceptions will be caught by the main loop instead
  except Exception, error:
    Globals.logger.report_startup_error(error)
    
  import gc
  gc.collect()
