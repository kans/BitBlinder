#!/usr/bin/python
#Copyright 2008-2009 InnomiNet

"""General Methods to access a postgresql db- using twisted and psycopg2"""

from twisted.enterprise import adbapi
import os
import psycopg2 as cyborg
import time
import DbAccessConfig

class DB_Pool():
  def  __init__(self, user, pw, db, minConns, maxConns):
    """wrapper for starting our antipool of connections to the db!"""
    #determine if this is live or on dev!
    
    self.conn_pool = adbapi.ConnectionPool("psycopg2", 
                                            cp_min=minConns,
                                            cp_max=maxConns,
                                            user = user, 
                                            password = pw, 
                                            database = db,
                                            )

  def read_db(self, sql, tup=None):
    """simple wrapper for read only database calls
    sql: string of sql command to execute 
    tup: string or tuple containing string arguments to use with python dbapi for escaping
    """
    if tup:
      d = self.conn_pool.runQuery(sql, tup)
    else:
      d = self.conn_pool.runQuery(sql)
    return d

  def write_db(self, sql, tup=None):
    """simple wrapper for writing db calls
    sql: string sql commands to execute in one commit
    tup: string, tuple ( list of strings), or None: contains string arguments to use
    """
    #nothing to escape
    if not tup:
      d = self.conn_pool.runOperation(sql)
    #need to escape something
    else:
      tup = tuple(tup)
      d = self.conn_pool.runOperation(sql, tup)    
    return d

#start up the pool based on the config file
Pool = DB_Pool(DbAccessConfig.user, 
                                DbAccessConfig.password, 
                                DbAccessConfig.database, 
                                DbAccessConfig.minconns, 
                                DbAccessConfig.maxconns)
write = Pool.write_db
read = Pool.read_db

if __name__ == "__main__":
  from twisted.internet import reactor
  
  def print_results(stuff):
    print stuff
  
  d = read('select * from accounts where username= %s', ('kans',))
  d.addCallback(print_results)
  d.addErrback(print_results)
  reactor.run()

