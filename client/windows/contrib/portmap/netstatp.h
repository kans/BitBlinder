//------------------------------------------------------------
//
// Netstatp
//
// Copyright (C) 1998-2002 Mark Russinovich
// Systems Internals
// http://www.sysinternals.com
//
//------------------------------------------------------------

//
// Maximum string lengths for ASCII ip address and port names
//
#define HOSTNAMELEN 256
#define PORTNAMELEN 256
#define ADDRESSLEN HOSTNAMELEN+PORTNAMELEN

//
// Our option flags
//
#define FLAG_ALL_ENDPOINTS 1
#define FLAG_SHOW_NUMBERS 2


//
// Undocumented extended information structures available
// only on XP and higher
//


typedef struct {
DWORD dwState; // state of the connection
DWORD dwLocalAddr; // address on local computer
DWORD dwLocalPort; // port number on local computer
DWORD dwRemoteAddr; // address on remote computer
DWORD dwRemotePort; // port number on remote computer
DWORD dwProcessId;
} MIB_TCPEXROW, *PMIB_TCPEXROW;


typedef struct {
DWORD dwNumEntries;
MIB_TCPEXROW table[ANY_SIZE];
} MIB_TCPEXTABLE, *PMIB_TCPEXTABLE;



//the corresponding vista entries:
typedef struct _MIB_TCPROW_OWNER_PID {
  DWORD dwState;
  DWORD dwLocalAddr;
  DWORD dwLocalPort;
  DWORD dwRemoteAddr;
  DWORD dwRemotePort;
  DWORD dwOwningPid;
} MIB_TCPROW_OWNER_PID, *PMIB_TCPROW_OWNER_PID;

typedef struct {
  DWORD dwNumEntries;
  MIB_TCPROW_OWNER_PID table[ANY_SIZE];
} MIB_TCPTABLE_OWNER_PID, *PMIB_TCPTABLE_OWNER_PID;

typedef enum {
  TCP_TABLE_BASIC_LISTENER,
  TCP_TABLE_BASIC_CONNECTIONS,
  TCP_TABLE_BASIC_ALL,
  TCP_TABLE_OWNER_PID_LISTENER,
  TCP_TABLE_OWNER_PID_CONNECTIONS,
  TCP_TABLE_OWNER_PID_ALL,
  TCP_TABLE_OWNER_MODULE_LISTENER,
  TCP_TABLE_OWNER_MODULE_CONNECTIONS,
  TCP_TABLE_OWNER_MODULE_ALL
} TCP_TABLE_CLASS, *PTCP_TABLE_CLASS;



typedef struct {
DWORD dwLocalAddr; // address on local computer
DWORD dwLocalPort; // port number on local computer
DWORD dwProcessId;
} MIB_UDPEXROW, *PMIB_UDPEXROW;


typedef struct {
DWORD dwNumEntries;
MIB_UDPEXROW table[ANY_SIZE];
} MIB_UDPEXTABLE, *PMIB_UDPEXTABLE;
