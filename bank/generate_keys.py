# Copyright (c) 2008 InnomiNet
# See LICENSE for details.
import M2Crypto

l = 384
name = 'bank'

name += '_%s'%l
key = M2Crypto.RSA.gen_key(l, 65537)

key.save_key(name+'.key', cipher=None)
key.save_pub_key(name+'.pem')

print len(key)
