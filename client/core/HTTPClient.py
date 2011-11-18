#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Class for testing the bandwidth of a circuit."""

import time
import os
import StringIO
from urlparse import urlparse


import twisted.protocols.policies as policies
#from OpenSSL import SSL, crypto
from M2Crypto import SSL
from twisted.protocols.policies import WrappingFactory
from twisted.internet.defer import TimeoutError
from twisted.protocols import basic
#from twisted.internet.ssl import CertificateOptions
from twisted.internet import reactor
from twisted.web import client, http

from core import BWHistory
from common import Globals
from common.utils import Basic
from common.Errors import DownloadSizeError
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import Scheduler
  
#: list of HTTPDownloads that are currently running:
_httpDownloads = []

def stop_all():
  #end all the debugging test threads that might have been launched
  for t in _httpDownloads:
    t.shutdown()
  
class ClosableStringIO(StringIO.StringIO):
  """Used because we cannot read from StringIO's after they are closed,
  and I want HTTP downloads stored in them at times."""
  def close(self):
    pass
  def really_close(self):
    StringIO.StringIO.close(self)
  def __del__(self):
    try:
      StringIO.StringIO.close(self)
    except:
      pass
  
class HTTPDownload:
  """Download a file from a website, possibly through a circuit"""
  #TODO:  call failureCB if there is an improper address or other exception here
  def __init__(self, bbApp, url, circ, successCB, failureCB=None, progressCB=None, fileName=None, timeout=None):
    """Signal the main thread to launch an external connection and let us
    handle which circuit to attach it to.
    @param url:  location to download from
    @type  url:  str (URL)
    @param circ:  a circuit to tunnel the request over, if necessary
    @type  circ:  Circuit or None
    @param successCB:  function to call when the download has finished successfully
    @type  successCB:  function(data, httpDownloadInstance)
    @param failureCB:  function to call when the download has finished successfully
    @type  failureCB:  function(reason, httpDownloadInstance) or None if you dont care about failures
    @param progressCB: function to call as there is periodic progress
    @type  progressCB: function(progress)
    @param fileName:  file to store the data to, if necessary.  If None, data will be returned to the success function.  If non-None, the filename will be returned instead
    @type  fileName:  str
    @param timeout:  how long to wait for a response before assuming that it failed
                     IMPORTANT NOTE:  this is how long to wait for the SERVER.  Total timeout will be timeout + time to wait for circuit, if there is a circuit
                     Note that circuits have timeouts for being built, and setting up PAR
    @type  timeout:  float (seconds) or None"""
    self.url = url
    if circ:
      assert not circ.is_done(), "Cannot download through a circuit (%s) that is finished" % (circ.id)
    self.circ = circ
    
    self.fileName = fileName
    if not self.fileName:
      self.file = ClosableStringIO()
    else:
      self.file = open(self.fileName, "wb")
    
    self.successCB = successCB
    self.failureCB = failureCB
    self.progressCB = progressCB
    self.start_time = time.time()
    self.factory = None
    #: will eventually point to the protocol object for this test
    self.protocolInstance = None
    self.wrappingFactory = None
    self.requestDone = False
    #whether to use a TLS connection
    self.useTLS = False
    if self.url[0:5].lower() == "https":
      self.useTLS = True
    #extract the host to connect to:
    self.remoteHost = urlparse(self.url)[1]
    #extract the port to connect to:
    self.remotePort = 80
    if self.useTLS:
      self.remotePort = 443
    if self.remoteHost.find(":") != -1:
      self.remoteHost, self.remotePort = self.remoteHost.split(":")
      self.remotePort = int(self.remotePort)
      
    log_msg("HTTP REQUEST:  %s" % (Basic.clean(self.url)), 4)
    
    self.factory = TestHTTPClientFactory(self, self.url, self.file)
    if self.progressCB:
      self.factory.protocol = MonitoredHTTPPageDownloader
      
    if self.useTLS:
      wrappingFactory = policies.WrappingFactory(self.factory)
      def wrap_protocol(factory, wrappedProtocol):
        checker = SSL.Checker.Checker(host=self.remoteHost)
        p = SSL.TwistedProtocolWrapper.TLSProtocolWrapper(factory,
                           wrappedProtocol,
                           startPassThrough=0,
                           client=1,
                           contextFactory=ClientContextFactory(),
                           postConnectionCheck=checker)
        factory.protocolInstance = p
        return p
      wrappingFactory.protocol = wrap_protocol
      wrappingFactory.deferred = self.factory.deferred
      self.factory = wrappingFactory
    
    _httpDownloads.append(self)
    try:
      if self.circ:
        d = bbApp.launch_external_factory(self.remoteHost, self.remotePort, self.factory, self.circ.handle_stream, "REQUEST: %s" % (self.url))
      else:
        Globals.reactor.connectTCP(self.remoteHost, self.remotePort, self.factory)
    except Exception, e:
      self.failure(e)
      return
    #and add the callbacks
    self.factory.deferred.addCallback(self.success)
    self.factory.deferred.addErrback(self.failure)
    
    #schedule a timeout if there is one:
    self.timeout = timeout
    if self.timeout:
      if self.circ:
        setupDoneDeferred = self.circ.get_built_deferred()
        setupDoneDeferred.addCallback(self._schedule_timeout)
      else:
        self._schedule_timeout()
  
  def _schedule_timeout(self, result=None):
    Scheduler.schedule_once(self.timeout, self.failure, TimeoutError())
    
  def success(self, data):
    """Called when all data has finished downloading.  Validates the the length of the data is proper given any relevant headers, and calls successCB or failure appropriately
    @param data:  the data downloaded from the HTTPDownloader (None if we were saving to a file)
    @type  data:  str or None"""
    if not self.requestDone:
      self.requestDone = True
      try:
        #validate that the file length is right if there were headers:
        if not self.fileName:
          data = self.file.getvalue()
          self.file.really_close()
          dataSize = len(data)
        else:
          dataSize = os.path.getsize(self.fileName)
        if self.protocolInstance.headers.has_key('content-length'):
          headerSize = int(self.protocolInstance.headers['content-length'][0])
          if not headerSize == dataSize:
            raise DownloadSizeError("Downloaded size was %s.  Header content-length size was %s." % (dataSize, headerSize))
      except Exception, e:
        self.failure(e)
      else:
        try:
          if not self.fileName:
            self.successCB(data, self)
          else:
            self.successCB(self.fileName, self)
        except Exception, e:
          log_ex(e, "HTTPClient failed during success callback.  url=%s" % (self.url))
      finally:
        if self in _httpDownloads:
          _httpDownloads.remove(self)
      
  def failure(self, failure):
    """Called when a download fails for any reason
    @param failure:  the reason that the download failed
    @type  failure:  Exception, Failure, or str"""
    if not self.requestDone:
      try:
        self.requestDone = True
        #ensure that the network connection is closed (so it doesnt keep writing to our buffer)
        if self.protocolInstance and self.protocolInstance.transport:
          self.protocolInstance.transport.loseConnection()
        #and close our buffer:
        if not self.fileName:
          self.file.really_close()
        #call the registered failure handler
        if self.failureCB:
          self.failureCB(failure, self)
        #and if there is not one, log the error by default
        else:
          log_ex(failure, "HTTPClient failed.  url=%s" % (self.url))
      except Exception, e:
        log_ex(e, "HTTPClient failed during failure callback.  url=%s" % (self.url))
      finally:
        if self in _httpDownloads:
          _httpDownloads.remove(self)
          
  def circuit_is_alive(self):
    if not self.circ:
      return False
    return not self.circ.is_done()
  
  def shutdown(self):
    """Join with the thread running the test."""
    if self.factory and self.factory.protocolInstance and self.factory.protocolInstance.transport:
      self.factory.protocolInstance.transport.loseConnection()
      
class ClientContextFactory:
  """Needed to created the context for connectSSL"""    
  
  def verify_cb(self, connection, x509, errNum, errDepth, returnCode):
    """Simple callback, we don't really do anything with it but return the pre-callback error code or log an appropriate error."""
    if returnCode:
      return True
    else:
      raise Exception("TLS failed!\nerrNum=%s\nerrDepth=%s" % (errNum, errDepth))
    return returnCode
    
  def getContext(self):
    """Get an SSL context object for use in authenticating an HTTPS connection
    @returns:  some kind of context object"""
    ctx = SSL.Context()
    ctx.load_verify_locations(os.path.join("data", "master.pem"))
    ctx.set_verify(SSL.verify_peer, 16, self.verify_cb)
    ctx.load_client_ca(os.path.join("data", "server.crt"))
    return ctx
    
class TestHTTPPageDownloader(client.HTTPPageDownloader):
  """Integrating with Twisted class to handle TLS and notify our class of failures and success"""

  def connectionMade(self):
    """Installs a wrapper function to record how much data we write (for the bandwidth graphs, etc)
    This is only necessary in the case where the connection is NOT being proxied (it will be recorded by Tor in that case)"""
    self.followRedirect = 1
    client.HTTPPageGetter.connectionMade(self)
    #record writes if necessary
    if not self.factory.httpDownloadInstance.circ:
      def writeWrapper(data, oldWriteCall=self.transport.write):
        BWHistory.localBandwidth.handle_bw_event(0, len(data))
        oldWriteCall(data)
      self.transport.write = writeWrapper
      
  def dataReceived(self, data):
    #only handle data if the test instance is not finished:
    if not self.factory.httpDownloadInstance.requestDone:
      basic.LineReceiver.dataReceived(self, data)
    #record reads if necessary
    if not self.factory.httpDownloadInstance.circ:
      BWHistory.localBandwidth.handle_bw_event(len(data), 0)
    
class MonitoredHTTPPageDownloader(TestHTTPPageDownloader):
  """Extending download class to notify progressCB when each piece of data is downloaded, for user feedback"""
  def handleEndHeaders(self):
    client.HTTPPageGetter.handleEndHeaders(self)
    self.finalLength = self.length
    if self.finalLength != None:
      self.factory.httpDownloadInstance.progressCB(0.0)
    else:
      self.factory.httpDownloadInstance.progressCB(None)
      
  def rawDataReceived(self, data):
    http.HTTPClient.rawDataReceived(self, data)
    if self.finalLength != None:
      percentDone = (float(self.finalLength) - float(self.length)) / float(self.finalLength)
      self.factory.httpDownloadInstance.progressCB(percentDone)
      
  def handleResponse(self, response):
    client.HTTPPageGetter.handleResponse(self, response)
    self.factory.httpDownloadInstance.progressCB(1.0)

class TestHTTPClientFactory(client.HTTPDownloader):
  protocol = TestHTTPPageDownloader
  def __init__(self, httpDownloadInstance, *args, **kwargs):
    client.HTTPDownloader.__init__(self, *args, **kwargs)
    self.httpDownloadInstance = httpDownloadInstance
    self.protocolInstance = None
    
  def buildProtocol(self, addr):
    p = client.HTTPClientFactory.buildProtocol(self, addr)
    if self.protocolInstance:
      log_msg("Handling a 302 I guess?", 1)
      if self.protocolInstance.transport:
        self.protocolInstance.transport.loseConnection()
    self.protocolInstance = p
    self.httpDownloadInstance.protocolInstance = p
    return p
  
  def clientConnectionFailed(self, connector, reason):
    client.HTTPClientFactory.clientConnectionFailed(self, connector, reason)
    self.httpDownloadInstance.failure(reason)
  
  def clientConnectionLost(self, connector, reason):
    client.HTTPClientFactory.clientConnectionLost(self, connector, reason)
    self.protocolInstance.connectionLost(reason)
    
