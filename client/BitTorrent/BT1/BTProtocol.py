# Written by Bram Cohen
# see LICENSE.txt for license information

from binascii import b2a_hex
from urllib import quote
from BitTorrent.BTcrypto import Crypto as CRYPTO
from BitTorrent.BT1 import ClientIdentifier

from twisted.internet import protocol

import BitTorrent.BitTorrentClient
from core import BWHistory
from common.utils import Basic
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

DEBUG = False

MAX_INCOMPLETE = 6
RESERVED_BYTES_LENGTH = 8
INFO_HASH_LENGTH = 20
PEER_ID_LENGTH = 20
protocol_name = 'BitTorrent protocol'

option_pattern = chr(0)*RESERVED_BYTES_LENGTH

def toint(s):
    return long(b2a_hex(s), 16)

def tobinary16(i):
    return chr((i >> 8) & 0xFF) + chr(i & 0xFF)

def make_readable(s):
    if not s:
        return ''
    if quote(s).find('%') >= 0:
        return b2a_hex(s).upper()
    return '"'+s+'"'

class BTProtocol(protocol.Protocol):
    def __init__(self, id=None, encrypted=None, proxied=False):
        self.Encoder = None
        self.isProxied = proxied
        self.connecter = None
        self.id = id
        self.locally_initiated = (id != None)
        self.readable_id = make_readable(id)
        self.complete = False
        self.keepalive = lambda: None
        self.closed = False
        self.buffer = ''
        self.bufferlen = None
        self.log = None
        self.clientName = None
        self.cryptmode = 0
        self.encrypter = None
        self.supposedlyEncrypted = encrypted
        #self.was_ext_handshake = ext_handshake
        #self.supplied_options = options
        self.readyToFlush = False
        self.btApp = BitTorrent.BitTorrentClient.get()
        self._read = self.read
        self._write = self.write

    def _log_start(self):   # only called with DEBUG = True
        self.log = open('peerlog.'+self.get_ip()+'.txt','a')
        self.log.write('connected - ')
        if self.locally_initiated:
            self.log.write('outgoing\n')
        else:
            self.log.write('incoming\n')
        self._logwritefunc = self.write
        self.write = self._log_write

    def _log_write(self, s):
        self.log.write('w:'+b2a_hex(s)+'\n')
        self._logwritefunc(s)
        
    def get_ip(self):
      if self.isProxied:
        return self.transport.host
      else:
        return self.transport.getPeer().host
      
    def get_port(self):
      if self.isProxied:
        return self.transport.port
      else:
        return self.transport.getPeer().port

    def get_id(self):
        """gets the peer id"""
        return self.id

    def get_readable_id(self):
        return self.readable_id
        
    def get_client_name(self):
      """This function caches the result for performance reasons (lots of regular expressions, and this is called often)"""
      #make sure we've learned their ID already
      peerId = self.get_id()
      if peerId == 0:
        return "never learned"
      #if we have not mapped their peer id to a torrent program yet
      if not self.clientName:
        #NOTE:  only doing this once to avoid tons of regular expression evaluations
        try:
          cleanName = ClientIdentifier.identify_client(peerId)
          self.clientName = " ".join(cleanName)
        except:
          self.clientName = "Unknown"
      return self.clientName

    def is_locally_initiated(self):
        return self.locally_initiated

    def is_encrypted(self):
        return bool(self.encrypted)

    #NOTE:  both of these functions need to be audited, not sure how to check about flushing in Twisted
    def is_flushed(self):
        return True
    
#    def connection_flushed(self, connection):
#      if self.complete:
#        self.connecter.connection_flushed(self)

    def _read_header(self, s):
        """ 'In version 1.0 of the BitTorrent protocol, pstrlen = 19, and pstr = "BitTorrent protocol". ' """
        if s == chr(len(protocol_name))+protocol_name:
            self.protocol = protocol_name
            return RESERVED_BYTES_LENGTH, self.read_options 
        return None

    def read_header(self, s):
        if self._read_header(s):
            if self.encrypted or self.Encoder.config['crypto_stealth']:
                return None
            return RESERVED_BYTES_LENGTH, self.read_options
        if self.locally_initiated and not self.encrypted:
            return None
        elif not self.Encoder.config['crypto_allowed']:
            return None
        if not self.encrypted:
            self.encrypted = True
            self.encrypter = CRYPTO(self.locally_initiated)
        self._write_buffer(s)
        return self.encrypter.keylength, self.read_crypto_header

    ################## ENCRYPTION SUPPORT ######################

    def _start_crypto(self):
        self.encrypter.setrawaccess(self._read,self._write)
        self.write = self.encrypter.write
        self.read = self.encrypter.read
        if self.buffer:
            self.buffer = self.encrypter.decrypt(self.buffer)

    def _end_crypto(self):
        self.read = self._read
        self.write = self._write
        self.encrypter = None

    def read_crypto_header(self, s):
        self.encrypter.received_key(s)
        self.encrypter.set_skey(self.Encoder.download_id)
        if self.locally_initiated:
            if self.Encoder.config['crypto_only']:
                cryptmode = '\x00\x00\x00\x02'    # full stream encryption
            else:
                cryptmode = '\x00\x00\x00\x03'    # header or full stream
            padc = self.encrypter.padding()
            self.write( self.encrypter.block3a
                      + self.encrypter.block3b
                      + self.encrypter.encrypt(
                            ('\x00'*8)            # VC
                          + cryptmode             # acceptable crypto modes
                          + tobinary16(len(padc))
                          + padc                  # PadC
                          + '\x00\x00' ) )        # no initial payload data
            self._max_search = 520
            return 1, self.read_crypto_block4a
        self.write(self.encrypter.pubkey+self.encrypter.padding())
        self._max_search = 520
        return 0, self.read_crypto_block3a

    def _search_for_pattern(self, s, pat):
        p = s.find(pat)
        if p < 0:
            if len(s) >= len(pat):
                self._max_search -= len(s)+1-len(pat)
            if self._max_search < 0:
                self.close()
                return False
            self._write_buffer(s[1-len(pat):])
            return False
        self._write_buffer(s[p+len(pat):])
        return True

    ### INCOMING CONNECTION ###

    def read_crypto_block3a(self, s):
        if not self._search_for_pattern(s,self.encrypter.block3a):
            return -1, self.read_crypto_block3a     # wait for more data
        return len(self.encrypter.block3b), self.read_crypto_block3b

    def read_crypto_block3b(self, s):
        if s != self.encrypter.block3b:
            return None
        self.Encoder.connecter.external_connection_made += 1
        self._start_crypto()
        return 14, self.read_crypto_block3c

    def read_crypto_block3c(self, s):
        if s[:8] != ('\x00'*8):             # check VC
            return None
        self.cryptmode = toint(s[8:12]) % 4
        if self.cryptmode == 0:
            return None                     # no encryption selected
        if ( self.cryptmode == 1            # only header encryption
             and self.Encoder.config['crypto_only'] ):
            return None
        padlen = (ord(s[12])<<8)+ord(s[13])
        if padlen > 512:
            return None
        return padlen+2, self.read_crypto_pad3

    def read_crypto_pad3(self, s):
        s = s[-2:]
        ialen = (ord(s[0])<<8)+ord(s[1])
        if ialen > 65535:
            return None
        if self.cryptmode == 1:
            cryptmode = '\x00\x00\x00\x01'    # header only encryption
        else:
            cryptmode = '\x00\x00\x00\x02'    # full stream encryption
        padd = self.encrypter.padding()
        self.write( ('\x00'*8)            # VC
                  + cryptmode             # encryption mode
                  + tobinary16(len(padd))
                  + padd )                # PadD
        if ialen:
            return ialen, self.read_crypto_ia
        return self.read_crypto_block3done()

    def read_crypto_ia(self, s):
        if DEBUG:
            self._log_start()
            self.log.write('r:'+b2a_hex(s)+'(ia)\n')
            if self.buffer:
                self.log.write('r:'+b2a_hex(self.buffer)+'(buffer)\n')
        return self.read_crypto_block3done(s)

    def read_crypto_block3done(self, ia=''):
        if DEBUG:
            if not self.log:
                self._log_start()
        if self.cryptmode == 1:     # only handshake encryption
            assert not self.buffer  # oops; check for exceptions to this
            self._end_crypto()
        if ia:
            self._write_buffer(ia)
        return 1+len(protocol_name), self.read_encrypted_header

    ### OUTGOING CONNECTION ###

    def read_crypto_block4a(self, s):
        if not self._search_for_pattern(s,self.encrypter.VC_pattern()):
            return -1, self.read_crypto_block4a     # wait for more data
        self._start_crypto()
        return 6, self.read_crypto_block4b

    def read_crypto_block4b(self, s):
        self.cryptmode = toint(s[:4]) % 4
        if self.cryptmode == 1:             # only header encryption
            if self.Encoder.config['crypto_only']:
                return None
        elif self.cryptmode != 2:
            return None                     # unknown encryption
        padlen = (ord(s[4])<<8)+ord(s[5])
        if padlen > 512:
            return None
        if padlen:
            return padlen, self.read_crypto_pad4
        return self.read_crypto_block4done()

    def read_crypto_pad4(self, s):
        # discard data
        return self.read_crypto_block4done()

    def read_crypto_block4done(self):
        if DEBUG:
            self._log_start()
        # only handshake encryption
        if self.cryptmode == 1:
          # oops; check for exceptions to this
            if not self.buffer:
                return None
            self._end_crypto()
        handshake = self._create_full_handshake()
        self.write(handshake)
        return 1+len(protocol_name), self.read_encrypted_header

    ### START PROTOCOL OVER ENCRYPTED CONNECTION ###
      
    def read_encrypted_header(self, s):
        return self._read_header(s)

    ################################################

    def read_options(self, s):
        """reads the reserved bytes of a handshake"""
        self.options = s
        return INFO_HASH_LENGTH, self.read_download_id

    def _create_full_handshake(self):
        """creates a handshake for unencrypted handshakes per specs"""
        pstrlen = chr(len(protocol_name))
        pstr = protocol_name
        reserved = option_pattern
        infoHash = self.Encoder.download_id
        peerId = self.Encoder.my_id
        handshake = pstrlen + pstr + reserved + infoHash + peerId
        return handshake
        
    def read_download_id(self, s):
        """reads the info hash of a handshake message
        the info hash must match the expected one"""
        badInfoHash = s != self.Encoder.download_id
        ip=self.get_ip()
        bannedIpAddress = not self.Encoder.check_ip(ip=ip)
        
        if (badInfoHash or bannedIpAddress):
            return None
        if not self.locally_initiated:
            if not self.encrypted:
                self.Encoder.connecter.external_connection_made += 1
            handshake = self._create_full_handshake()
            self.write(handshake)
        return PEER_ID_LENGTH, self.read_peer_id

    def read_peer_id(self, s):
        if not self.encrypted and self.Encoder.config['crypto_only']:
            return None     # allows older trackers to ping,
                            # but won't proceed w/ connections
        if not self.id:
            self.id = s
            self.readable_id = make_readable(s)
        else:
            if s != self.id:
                return None
        self.complete = self.Encoder.got_id(self)
        if not self.complete:
            return None
        self._switch_to_read2()
        self.get_client_name()
        c = self.Encoder.connecter.connection_made(self)
        self.readyToFlush = True
        self.keepalive = c.send_keepalive
        #why does this return 4?
        return 4, self.read_len

    def read_len(self, s):
        l = toint(s)
        if l > self.Encoder.max_len:
            return None
        return l, self.read_message

    def read_message(self, s):
        if s != '':
            self.connecter.got_message(self, s)
        return 4, self.read_len

    def read_dead(self, s):
        return None

    def _auto_close(self):
        if not self.complete:
            self.close()

    def close(self):
        if not self.closed:
            #self.connection.close()
            self.transport.loseConnection()
            self.sever()

    def sever(self):
        if self.log:
            self.log.write('closed\n')
            self.log.close()
        self.closed = True
        if self.Encoder:
          if self.Encoder.connections and self in self.Encoder.connections:
            self.Encoder.connections.remove(self)
          if self.complete:
              #NOTE:  I *think* this gets called enough, not 100% sure
              self.connecter.connection_lost(self)
          #elif self.locally_initiated:
              #incompletecounter.decrement()

    def send_message_raw(self, message):
        self.write(message)

    def write(self, message):
      if not self.closed:
        #Need to record bw when we are not being proxied:
        if not self.isProxied:
          BWHistory.localBandwidth.handle_bw_event(0, len(message))
          self.btApp.handle_bw_event(0, len(message))
        self.transport.write(message)
        if self.readyToFlush:
          self.connecter.connection_flushed(self)

    #def data_came_in(self, connection, s):
    #    self.read(s)
    
    def dataReceived(self, data):
      self.read(data)

    def _write_buffer(self, s):
        self.buffer = s+self.buffer

    def read(self, s):
        """gets called when we get raw data"""
        if self.log:
            self.log.write('r:'+b2a_hex(s)+'\n')
        if self.Encoder:
          self.Encoder.measurefunc(len(s))
        self.buffer += s
        if not self.isProxied:
          self.btApp.handle_bw_event(len(s), 0)
          BWHistory.localBandwidth.handle_bw_event(len(s), 0)
        while True:
            if self.closed:
                return
            # self.next_len = # of characters function expects
            # or 0 = all characters in the buffer
            # or -1 = wait for next read, then all characters in the buffer
            # not compatible w/ keepalives, switch out after all negotiation complete
            if self.next_len <= 0:
                m = self.buffer
                self.buffer = ''
            elif len(self.buffer) >= self.next_len:
                m = self.buffer[:self.next_len]
                self.buffer = self.buffer[self.next_len:]
            else:
                return
            try:
                x = self.next_func(m)
            except:
                self.next_len, self.next_func = 1, self.read_dead
                raise
            if x is None:
                self.close()
                return
            if not(x is True):
              self.next_len, self.next_func = x
            if self.next_len < 0:  # already checked buffer
                return             # wait for additional data
            if self.bufferlen is not None:
                self._read2('')
                return

    def _switch_to_read2(self):
        self._write_buffer = None
        if self.encrypter:
            self.encrypter.setrawaccess(self._read2,self._write)
        else:
            self.read = self._read2
        self.bufferlen = len(self.buffer)
        self.buffer = [self.buffer]

    def _read2(self, s):
        """handles reading raw data from actual torrenting (not handshakes"""
        if self.log:
            self.log.write('r:'+b2a_hex(s)+'\n')
        self.Encoder.measurefunc(len(s))
        if not self.isProxied:
          self.btApp.handle_bw_event(len(s), 0)
          BWHistory.localBandwidth.handle_bw_event(len(s), 0)
        while True:
            if self.closed:
                return
            p = self.next_len-self.bufferlen
            if self.next_len == 0:
                m = ''
            elif s:
                if p > len(s):
                    self.buffer.append(s)
                    self.bufferlen += len(s)
                    return
                self.bufferlen = len(s)-p
                self.buffer.append(s[:p])
                m = ''.join(self.buffer)
                if p == len(s):
                    self.buffer = []
                else:
                    self.buffer=[s[p:]]
                s = ''
            elif p <= 0:
                # assert len(self.buffer) == 1
                s = self.buffer[0]
                self.bufferlen = len(s)-self.next_len
                m = s[:self.next_len]
                if p == 0:
                    self.buffer = []
                else:
                    self.buffer = [s[self.next_len:]]
                s = ''
            else:
                return
            try:
                x = self.next_func(m)
            except:
                self.next_len, self.next_func = 1, self.read_dead
                raise
            if x is None:
                self.close()
                return
            self.next_len, self.next_func = x
            if self.next_len < 0:  # already checked buffer
                return             # wait for additional data
              
    def connectionLost(self, reason):
      
      peerId = self.readable_id
      try:
        peerId = peerId.decode("hex")
      #since some peers send in ASCII instead of hex, oh well
      except TypeError:
        pass
        
      if not self.btApp.is_ready() and not self.btApp.is_starting():
        return
      
      if self.read == self._read2:
        stage = 'post handshake'
      elif self.encrypted:
        stage = 'before %s' % (self.next_func)
      else:
        stage = 'during handshake'
      log_msg("Lost connection to %s (%s client -- cm: %s) %s." % (Basic.clean(peerId), self.get_client_name(), self.cryptmode, stage), 3, "btconn")
      
      if self.Encoder:
        if self.Encoder.connections and self in self.Encoder.connections:
          self.sever()
        #maybe we should retry with encryption?
        if self.next_func == self.read_header:
          #did we try connecting via plaintext?
          if not self.supposedlyEncrypted:
            log_msg("Ok, retrying with encryption...", 3, "btconn")
            #ok, lets retry this connection but WITH encryption this time
            self.Encoder.start_connection((self.get_ip(), self.get_port()), self.id, True)
          else:
            log_msg("Failed with encryption too", 3, "btconn")
      else:
        self.closed = True
        
class OutgoingBTProtocol(BTProtocol):
    def __init__(self, Encoder, id, encrypted, proxied):
        assert id != None
        BTProtocol.__init__(self, id, encrypted, proxied)
        self.Encoder = Encoder
        self.connecter = Encoder.connecter
        
    def connectionMade(self):
      self.Encoder.completedConnections += 1
      log_msg("Connected %s BTProtocols" % (self.Encoder.completedConnections), 4, "btconn")
        
      #log_msg("BT Protocol Connected", 4)
      self.Encoder.incompletecounter -= 1
      
      if self.supposedlyEncrypted:
          self.encrypted = True
          self.encrypter = CRYPTO(True)
          self.write(self.encrypter.pubkey+self.encrypter.padding())
      else:
          self.encrypted = False
          handshake = self._create_full_handshake()
          self.write(handshake)
      self.next_len, self.next_func = 1+len(protocol_name), self.read_header
      self.Encoder.connect_succeeded(self)
        
class IncomingBTProtocol(BTProtocol):
    def __init__(self, multihandler, proxied):
        log_msg("New incoming BT Protocol created", 4, "btconn")
        BTProtocol.__init__(self, proxied=proxied)
        self.multihandler = multihandler
        #self.next_len, self.next_func = 1+len(protocol_name), self.read_header
        #TODO:  test--do incoming connections time out properly?
        #self.multihandler.rawserver.add_task(self._auto_close, 30)
        
    def connectionMade(self):
        log_msg("New incoming BT Protocol connected", 4, "btconn")
        self.encrypted = None       # don't know yet
        self.next_len, self.next_func = 1 + len(protocol_name), self.read_header
        
    def externalHandshakeDone(self, Encoder, encrypted, options=None):
        self.Encoder = Encoder
        self.connecter = Encoder.connecter
        self.Encoder.connecter.external_connection_made += 1
        log_msg("Figured out encoder for external connection %s" % (self.Encoder.connecter.external_connection_made), 4, "btconn")
        if encrypted:   # passed an already running encrypter
            self.encrypter = encrypted
            self.encrypted = True
            #self._start_crypto()
            self.next_len, self.next_func = 14, self.read_crypto_block3c
        else:
            self.encrypted = False
            self.options = options
            #self.write(self.Encoder.my_id)
            self.next_len, self.next_func = 20, self.read_peer_id

    def read_header(self, s):
        if self._read_header(s):
            if self.multihandler.config['crypto_only']:
                return None
            return RESERVED_BYTES_LENGTH, self.read_options
        if not self.multihandler.config['crypto_allowed']:
            return None
        self.encrypted = True
        self.encrypter = CRYPTO(False)
        self._write_buffer(s)
        return self.encrypter.keylength, self.read_crypto_header

    def read_crypto_header(self, s):
        self.encrypter.received_key(s)
        self.write(self.encrypter.pubkey+self.encrypter.padding())
        self._max_search = 520
        return 0, self.read_crypto_block3a

    def read_crypto_block3a(self, s):
        if not self._search_for_pattern(s,self.encrypter.block3a):
            # wait for more data
            return -1, self.read_crypto_block3a
        return 20, self.read_crypto_block3b

    def read_crypto_block3b(self, s):
        for k in self.multihandler.singlerawservers.keys():
            if self.encrypter.test_skey(s,k):
                if not self.multihandler.singlerawservers[k]._external_connection_made(self, None, self.buffer, self.encrypter):
                  return None
                BTProtocol.read_crypto_block3b(self, s)
                return True
        log_msg("Incoming encrypted connection is not for any of our current torrents", 2, "btconn")
        return None

    def read_download_id(self, s):
        if self.multihandler.singlerawservers.has_key(s):
            if self.multihandler.singlerawservers[s].protocol == self.protocol:
                if not self.multihandler.singlerawservers[s]._external_connection_made(self, self.options, self.buffer):
                  return None
                BTProtocol.read_download_id(self, s)
                return True
        log_msg("Incoming connection is not for any of our current torrents", 2, "btconn")
        return None
