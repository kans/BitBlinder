# Written by John Hoffman
# see LICENSE.txt for license information

from cStringIO import StringIO
from BTcrypto import Crypto

from BT1.JashEncrypter import protocol_name

default_task_id = []

class SingleRawServer:
    def __init__(self, info_hash, multihandler, doneflag, protocol):
        self.info_hash = info_hash
        self.doneflag = doneflag
        self.protocol = protocol
        self.multihandler = multihandler
        self.rawserver = multihandler.rawserver
        self.finished = False
        self.running = False
        self.handler = None
        self.taskqueue = []

    def shutdown(self):
        if not self.finished:
            self.multihandler.shutdown_torrent(self.info_hash)

    def _shutdown(self):
        if not self.finished:
            self.finished = True
            self.running = False
            self.rawserver.kill_tasks(self.info_hash)
            if self.handler:
                self.handler.close_all()

    def _external_connection_made(self, c, options, already_read,
                                  encrypted = None ):
        if self.running:
            #c.set_handler(self.handler)
            return self.handler.externally_handshaked_connection_made(c, options, already_read, encrypted = encrypted)
        return False

    ### RawServer functions ###

    def add_task(self, func, delay=0, id = default_task_id):
        if id is default_task_id:
            id = self.info_hash
        if not self.finished:
            self.rawserver.add_task(func, delay, id)

#    def bind(self, port, bind = '', reuse = False):
#        pass    # not handled here
        
    def start_connection(self, dns, handler = None):
        raise Exception("Should not be called")
        #if not handler:
        #    handler = self.handler
        #c = self.rawserver.start_connection(dns, handler)
        #return c

#    def listen_forever(self, handler):
#        pass    # don't call with this
    
    def start_listening(self, handler):
        self.handler = handler
        self.running = True
        #return self.shutdown    # obviously, doesn't listen forever

    def is_finished(self):
        return self.finished

    #def get_exception_flag(self):
    #    return self.rawserver.get_exception_flag()


class MultiHandler:
    def __init__(self, rawserver, doneflag, config):
        self.rawserver = rawserver
        self.rawserver.factory.multihandler = self
        self.masterdoneflag = doneflag
        self.config = config
        self.singlerawservers = {}
        self.connections = {}
        self.taskqueues = {}

    def newRawServer(self, info_hash, doneflag, protocol=protocol_name):
        new = SingleRawServer(info_hash, self, doneflag, protocol)
        self.singlerawservers[info_hash] = new
        return new

    def shutdown_torrent(self, info_hash):
        self.singlerawservers[info_hash]._shutdown()
        del self.singlerawservers[info_hash]

    def listen_forever(self):
        self.rawserver.listen_forever(self)
        for srs in self.singlerawservers.values():
            srs.finished = True
            srs.running = False
            srs.doneflag.set()
        
    ### RawServer handler functions ###
    # be wary of name collisions

    def external_connection_made(self, ss):
        NewSocketHandler(self, ss)
