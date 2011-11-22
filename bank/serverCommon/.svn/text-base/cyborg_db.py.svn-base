#!/usr/bin/python
#Copyright 2008 InnomiNet

"""General Methods to access a postgresql db- assumes antipool and psycopg2, as well as a python file, DbAccessConfig, with following syntax in the path
user = 'iuser'
password = 'password'
minconns = int
maxconns = int"""
import antipool
import os
import psycopg2 as cyborg
import time
import DbAccessConfig

class DB_Pool():
  def  __init__(self, user, pw, db, minConns, maxConns):
    """wrapper for starting our antipool of connections to the db!"""
    #determine if this is live or on dev!
    self.conn_pool = antipool.ConnectionPool (cyborg, options={'maxconn': maxConns, 'minconn':minConns}, user = user, password = pw, database = db)
    self.ro_conn = self.conn_pool.connection_ro()

  def get_conn(self):
    """attempts to return a conn object for writing
    may hang but will not raise an exception
    note: use the ro_conn for reading among multiple threads
    note: start_db_pool() must be called to initialize the pool"""
    got_connection = False
    while not got_connection:
      try:
        conn = self.conn_pool.connection()
        got_connection = True
      except:
        time.sleep(0.1)
    return conn

  def read_db(self, sql, tup=None, fetch='fetchone'):
    """simple wrapper for read only database calls
    it opens a cursor from the read only connection which is thread safe
    read_db(sql, tup, fetch='fetchone')
    sql: string of sql command to execute 
    tup: string or tuple containing string arguments to use with python dbapi for escaping
    fetch: string of fetch method (many, all, one) default is fetchone"""
    cur = self.ro_conn.cursor()
    if tup:
      tup = tuple(tup)
      cur.execute(sql, tup)
    else:
      cur.execute(sql)
    #eg for jash: cur.fetchone()
    tup = getattr(cur, fetch)()
    return tup

  def write_db(self, sql, tup=None):
    """simple wrapper for writing writing db calls which releases its conn obj back to the pool
    write_db(sql, tup)
    sql: either string or list of string sql commands to execute in one commit
    tup: string, tuple or list of tuples (! list of strings), or None: contains string arguments to use with python dbapi 2 for escaping
    note, if a list of strings and tuples is given, they must have the same length
    """
    conn = self.get_conn()
    cur = conn.cursor()
    if not tup: #nothing to escape
      if type(sql)==str: #only one line to execute
        cur.execute(sql)
      elif type(sql)==list: #need to execute multiple stuffs
        for item in sql:
          cur.execute(item)
    else:#need to escape something
      if type(sql)== str:
        sql = [sql]
      if type(tup) == str:
        tup = [tuple(tup)]
      elif type(tup)==tuple:
        tup = [tup]
      if len(sql) != len(tup):
        raise ValueError('sql and tup must be the same length')
      for position, s in enumerate(sql):
        cur.execute(s, tup[position])
    #commit it, if not, release the db connection to the pool    
    try:
      conn.commit()
    except Exception, e:
      raise e
    finally:
      conn.release()

Pool = DB_Pool(DbAccessConfig.user, DbAccessConfig.password, DbAccessConfig.database, DbAccessConfig.minconns, DbAccessConfig.minconns)#start up the pool based on the config file
write = Pool.write_db
read = Pool.read_db