
//JOSH:
//SEE HERE:  http://www.dalkescientific.com/writings/NBN/c_extensions.html
//For the code that this was based one
//NOTE:  if you want to build this in debug mode, the you have to download and build the libs for python from source (it's easy)
//C:\local\python2.5.2 has it right now

//------------------------------------------------------------
//
// Netstatp
//
// Copyright (C) 1998-2002 Mark Russinovich
// Sysinternals
// www.sysinternals.com
//
// This program implements a subset of the Netstat program's
// functionality. Specifically, it enumerates and displays
// information about all UDP and TCP endpoints.
//
//------------------------------------------------------------
#include "windows.h"
#include "stdio.h"
#include "winsock.h"
#include "iprtrmib.h"
#include "tlhelp32.h"
#include "iphlpapi.h"
#include "netstatp.h"
#include "Python.h"


//
// APIs that we link against dynamically in case they aren't
// present on the system we're running on.
//
DWORD (WINAPI *pAllocateAndGetTcpExTableFromStack)(
  PMIB_TCPEXTABLE *pTcpTable, // buffer for the connection table
  BOOL bOrder, // sort the table?
  HANDLE heap,
  DWORD zero,
  DWORD flags
);

DWORD (WINAPI *pGetExtendedTcpTable)(
  PVOID pTcpTable,
  PDWORD pdwSize,
  BOOL bOrder,
  ULONG ulAf,
  TCP_TABLE_CLASS TableClass,
  ULONG Reserved
);


DWORD (WINAPI *pAllocateAndGetUdpExTableFromStack)(
  PMIB_UDPEXTABLE *pTcpTable, // buffer for the connection table
  BOOL bOrder, // sort the table?
  HANDLE heap,
  DWORD zero,
  DWORD flags
);

HANDLE (WINAPI *pCreateToolhelp32Snapshot)(
  DWORD dwFlags,
  DWORD th32ProcessID
);

BOOL (WINAPI *pProcess32First)(
  HANDLE hSnapshot,
  LPPROCESSENTRY32 lppe
);

BOOL (WINAPI *pProcess32Next)(
  HANDLE hSnapshot,
  LPPROCESSENTRY32 lppe
);


//
// Possible TCP endpoint states
//
static char TcpState[][32] = {
  "???",
  "CLOSED",
  "LISTENING",
  "SYN_SENT",
  "SYN_RCVD",
  "ESTABLISHED",
  "FIN_WAIT1",
  "FIN_WAIT2",
  "CLOSE_WAIT",
  "CLOSING",
  "LAST_ACK",
  "TIME_WAIT",
  "DELETE_TCB"
};


//--------------------------------------------------------------------
//
// PrintError
//
// Translates a Win32 error into a text equivalent
//
//--------------------------------------------------------------------
VOID
PrintError(  DWORD ErrorCode  )  {
  LPVOID lpMsgBuf;

  FormatMessage( FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM,
    NULL, ErrorCode,
    MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
    (LPTSTR) &lpMsgBuf, 0, NULL );
  printf("%s\n", lpMsgBuf );
  LocalFree( lpMsgBuf );
}


//------------------------------------------------------------
//
// ExApisArePresent
//
// Determines if Ex APIs (the XP version) are present, and
// if so, gets the function entry points.
//
//------------------------------------------------------------
BOOLEAN
ExApisArePresent(
VOID
)
{
pAllocateAndGetTcpExTableFromStack = (PVOID) GetProcAddress( LoadLibrary( "iphlpapi.dll"),
"AllocateAndGetTcpExTableFromStack" );
if( !pAllocateAndGetTcpExTableFromStack ) return FALSE;

pAllocateAndGetUdpExTableFromStack = (PVOID) GetProcAddress( LoadLibrary( "iphlpapi.dll"),
"AllocateAndGetUdpExTableFromStack" );
if( !pAllocateAndGetUdpExTableFromStack ) return FALSE;

pCreateToolhelp32Snapshot = (PVOID) GetProcAddress( GetModuleHandle( "kernel32.dll" ),
"CreateToolhelp32Snapshot" );
if( !pCreateToolhelp32Snapshot ) return FALSE;

pProcess32First = (PVOID) GetProcAddress( GetModuleHandle( "kernel32.dll" ),
"Process32First" );
if( !pProcess32First ) return FALSE;

pProcess32Next = (PVOID) GetProcAddress( GetModuleHandle( "kernel32.dll" ),
"Process32Next" );
if( !pProcess32Next ) return FALSE;
return TRUE;
}

//------------------------------------------------------------
//
// VistaApisArePresent
//
// Determines if Ex APIs (the Vista version) are present, and
// if so, gets the function entry points.
//
//------------------------------------------------------------
BOOLEAN
VistaApisArePresent(
VOID
)
{
pGetExtendedTcpTable =
  (DWORD (WINAPI *)(PVOID,PDWORD,BOOL,ULONG,TCP_TABLE_CLASS,ULONG))
    GetProcAddress(LoadLibrary( "iphlpapi.dll"), "GetExtendedTcpTable");
 if(pGetExtendedTcpTable == NULL) return FALSE;

pCreateToolhelp32Snapshot = (PVOID) GetProcAddress( GetModuleHandle( "kernel32.dll" ),
"CreateToolhelp32Snapshot" );
if( !pCreateToolhelp32Snapshot ) return FALSE;

pProcess32First = (PVOID) GetProcAddress( GetModuleHandle( "kernel32.dll" ),
"Process32First" );
if( !pProcess32First ) return FALSE;

pProcess32Next = (PVOID) GetProcAddress( GetModuleHandle( "kernel32.dll" ),
"Process32Next" );
if( !pProcess32Next ) return FALSE;
return TRUE;
}


//------------------------------------------------------------
// FindPIDByPort
//    figure out which process bound this port
//------------------------------------------------------------
DWORD
FindPIDByPort(DWORD port) {
  DWORD error;
  BOOLEAN exPresent;
  PMIB_TCPEXTABLE tcpExTable;
  PMIB_TCPTABLE_OWNER_PID vistaExTable;
  PVOID pTCPTable = NULL;
  DWORD size = 0;
  DWORD result = 0;
  HANDLE hProcessSnap;
  DWORD i, localAddr, localPort, remoteAddr;
  
  
  // Determine if the new version of the API is available (XP SP2, Vista)
  exPresent = VistaApisArePresent();
  if( !exPresent ) {
    // Determine if extended query is available (it's only present
    // on XP and higher).
    exPresent = ExApisArePresent();
  
    // Get the tables of TCP endpoints with process IDs
    error = pAllocateAndGetTcpExTableFromStack( &tcpExTable, TRUE, GetProcessHeap(), 2, 2 );
    if( error ) {
      printf("Failed to snapshot TCP endpoints.\n");
      PrintError( error );
      return -1;
    }
    
    // Get a process snapshot. Note that we won't be guaranteed to
    // exactly match a PID against a process name because a process could have exited
    // and the PID gotten reused between our endpoint and process snapshots.
    hProcessSnap = pCreateToolhelp32Snapshot( TH32CS_SNAPPROCESS, 0 );
    if( hProcessSnap == INVALID_HANDLE_VALUE ) {
      printf("Failed to take process snapshot. Process names will not be shown.\n\n");
    }
    // Dump the TCP table
    for( i = 0; i < tcpExTable->dwNumEntries; i++ ) {
      localAddr = tcpExTable->table[i].dwLocalAddr;
      remoteAddr = tcpExTable->table[i].dwRemoteAddr;
      localPort = htons( (WORD) tcpExTable->table[i].dwLocalPort);
      //is this the port we're looking for?
      if( (localAddr==0 || localAddr==16777343) && (remoteAddr==0 || remoteAddr==16777343) && localPort == port) {
        return tcpExTable->table[i].dwProcessId;
      }
    }
    return 0;
  }
  
  // Get the tables of TCP endpoints with process IDs
  result = pGetExtendedTcpTable(NULL, &size, TRUE, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0);
  while(result == ERROR_INSUFFICIENT_BUFFER){
    if(pTCPTable != NULL){
      free(pTCPTable);
    }
    pTCPTable = malloc(size);
    result = pGetExtendedTcpTable(pTCPTable, &size, TRUE, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0);
    if(result != NO_ERROR){
      printf("Failed to get TCP Table %s\n", GetLastError());
      free(pTCPTable);
      return -2;
    }
  }
  if(result != NO_ERROR){
    printf("Failed to get size estimation %s\n", GetLastError());
    return -3;
  }
  
  vistaExTable = ((PMIB_TCPTABLE_OWNER_PID)pTCPTable);
  
  // Get a process snapshot. Note that we won't be guaranteed to
  // exactly match a PID against a process name because a process could have exited
  // and the PID gotten reused between our endpoint and process snapshots.
  hProcessSnap = pCreateToolhelp32Snapshot( TH32CS_SNAPPROCESS, 0 );
  if( hProcessSnap == INVALID_HANDLE_VALUE ) {
    printf("Failed to take process snapshot. Process names will not be shown.\n\n");
  }
  // Dump the TCP table
  for( i = 0; i < vistaExTable->dwNumEntries; i++ ) {
    localAddr = vistaExTable->table[i].dwLocalAddr;
    remoteAddr = vistaExTable->table[i].dwRemoteAddr;
    localPort = htons( (WORD) vistaExTable->table[i].dwLocalPort);
    //is this the port we're looking for?
    if( (localAddr==0 || localAddr==16777343) && (remoteAddr==0 || remoteAddr==16777343) && localPort == port) {
      return vistaExTable->table[i].dwOwningPid;
    }
  }
  return 0;
}

/* The module doc string */
PyDoc_STRVAR(portmap__doc__, "Map from a outoing TCP localhost:port to the process that bound it.");

/* The function doc string */
PyDoc_STRVAR(find_pid_by_port_point__doc__,"port (outgoing, bound to localhost) -> pid");

/* The wrapper to the underlying C function */
static PyObject *
py_find_pid_by_port(PyObject *self, PyObject *args)
{
	int port, pid;
	/* "args" must have one int */
	/* The ':iterate_point' is for error messages */
	if (!PyArg_ParseTuple(args, "i:find_pid_by_port", &port))
		return NULL;
	
	/* Call the C function */
	pid = FindPIDByPort(port);
	
	/* Convert from a C integer value to a Python integer instance */
	return PyInt_FromLong((long) pid);
}

/* A list of all the methods defined by this module. */
/* "iterate_point" is the name seen inside of Python */
/* "py_iterate_point" is the name of the C function handling the Python call */
/* "METH_VARGS" tells Python how to call the handler */
/* The {NULL, NULL} entry indicates the end of the method definitions */
static PyMethodDef portmap_methods[] = {
	{"find_pid_by_port",  py_find_pid_by_port, METH_VARARGS, find_pid_by_port_point__doc__},
	{NULL, NULL}      /* sentinel */
};

/* When Python imports a C module named 'X' it loads the module */
/* then looks for a method named "init"+X and calls it.  Hence */
/* for the module "mandelbrot" the initialization function is */
/* "initmandelbrot".  The PyMODINIT_FUNC helps with portability */
/* across operating systems and between C and C++ compilers */
PyMODINIT_FUNC
initPortMap(void)
{
	/* There have been several InitModule functions over time */
	Py_InitModule3("PortMap", portmap_methods,
                   portmap__doc__);
}
