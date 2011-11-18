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
// GetPortName
//
// Translate port numbers into their text equivalent if
// there is one
//
//------------------------------------------------------------
PCHAR
GetPortName(DWORD Flags,UINT port,PCHAR proto,PCHAR name,int namelen){
  struct servent *psrvent;

  if( Flags & FLAG_SHOW_NUMBERS ) {

    sprintf( name, "%d", htons( (WORD) port));
    return name;
  }

  //
  // Try to translate to a name
  //
  if( psrvent = getservbyport( port, proto )) {

    strcpy( name, psrvent->s_name );

  } else {

    sprintf( name, "%d", htons( (WORD) port));
  }
  return name;
}

//------------------------------------------------------------
//
// GetIpHostName
//
// Translate IP addresses into their name-resolved form
// if possible.
//
//------------------------------------------------------------
PCHAR
GetIpHostName(DWORD Flags,BOOL local,UINT ipaddr,PCHAR name,int namelen){
  struct hostent *phostent;
  UINT nipaddr;

  //
  // Does the user want raw numbers?
  //
  nipaddr = htonl( ipaddr );
  if( Flags & FLAG_SHOW_NUMBERS ) {
    sprintf( name, "%d.%d.%d.%d",
    (nipaddr >> 24) & 0xFF,
    (nipaddr >> 16) & 0xFF,
    (nipaddr >> 8) & 0xFF,
    (nipaddr) & 0xFF);
    return name;
  }

  //
  // Try to translate to a name
  //
  if( !ipaddr ) {
    if( !local ) {
      sprintf( name, "%d.%d.%d.%d",
      (nipaddr >> 24) & 0xFF,
      (nipaddr >> 16) & 0xFF,
      (nipaddr >> 8) & 0xFF,
      (nipaddr) & 0xFF);
    } else {
      gethostname(name, namelen);
    }
  } else if( ipaddr == 0x0100007f ) {
    if( local ) {
      gethostname(name, namelen);
    } else {
      strcpy( name, "localhost" );
    }
  } else if( phostent = gethostbyaddr( (char *) &ipaddr,
    sizeof( nipaddr ), PF_INET )) {
    strcpy( name, phostent->h_name );
  } else {
    sprintf( name, "%d.%d.%d.%d",
    (nipaddr >> 24) & 0xFF,
    (nipaddr >> 16) & 0xFF,
    (nipaddr >> 8) & 0xFF,
    (nipaddr) & 0xFF);
  }
  return name;
}


//------------------------------------------------------------
//
// ProcessPidToName
//
// Translates a PID to a name.
//
//------------------------------------------------------------
PCHAR
ProcessPidToName(
HANDLE hProcessSnap,
DWORD ProcessId,
PCHAR ProcessName
)
{
PROCESSENTRY32 processEntry;

strcpy( ProcessName, "???" );
if( !pProcess32First( hProcessSnap, &processEntry )) {

return ProcessName;
}
do {

if( processEntry.th32ProcessID == ProcessId ) {

strcpy( ProcessName, processEntry.szExeFile );
return ProcessName;
}

} while( pProcess32Next( hProcessSnap, &processEntry ));

return ProcessName;
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

//--------------------------------------------------------------------
//
// Usage
//
//--------------------------------------------------------------------
BOOLEAN
Usage(VOID){
  printf("Netstatp lists process endpoints.\n" );
  printf("\nUsage: netstatp [-a] [-n] [-p PORT]\n" );
  printf(" -a Displays all connections and listening ports.\n");
  printf(" -n Displays addresses and port numbers in numerical form.\n");
  printf(" -p Display the PID of the process bound to localhost:PORT\n");
  printf("\n");
  return FALSE;
}

//--------------------------------------------------------------------
//
// GetOptions
//
// Parses the command line arguments.
//
//--------------------------------------------------------------------
BOOLEAN
GetOptions(int argc,char *argv[],BOOLEAN ExPresent,PDWORD Flags, PDWORD searchPort)
{
  int i, j;
  BOOLEAN skipArgument, skipNextArg;

  *Flags = 0;
  *searchPort = 0;
  skipNextArg = FALSE;
  for(i = 1; i < argc; i++) {
    skipArgument = FALSE;
    switch( argv[i][0] ) {
      case '-':
      case '/':
        j = 1;
        while( argv[i][j] ) {
          switch( toupper( argv[i][j] )) {
            case 'A':
              *Flags |= FLAG_ALL_ENDPOINTS;
              break;
            case 'N':
              *Flags |= FLAG_SHOW_NUMBERS;
              break;
            case 'P':
              if(i+1 >= argc)
                return Usage();
              *searchPort = atoi(argv[i+1]);
              skipArgument = TRUE;
              skipNextArg = TRUE;
              break;
            default:
              return Usage();
          }
          if( skipArgument ) 
            break;
          j++;
        }
        break;
      default:
        if(skipNextArg) {
          skipNextArg = FALSE;
          break;
        }
        return Usage();
    }
  }
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
  HANDLE hProcessSnap;
  DWORD i, localAddr, localPort, remoteAddr;
  
  // Determine if extended query is available (it's only present
  // on XP and higher).
  exPresent = ExApisArePresent();
  if( !exPresent ) {
    printf("This function only available on Windows XP or higher!\n");
  }
  
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

/* The module doc string */
PyDoc_STRVAR(portmap__doc__, "Map from a outoing TCP localhost:port to the process that bound it.");

/* The function doc string */
PyDoc_STRVAR(find_pid_by_port_point__doc__,"port (outgoing, bound to localhost) -> pid");

/* The wrapper to the underlying C function */
static PyObject *
py_find_pid_by_port(PyObject *self, PyObject *args)
{
	double x=0, y=0;
	int iterations, max_iterations=1000;
	/* "args" must have two doubles and may have an integer */
	/* If not specified, "max_iterations" remains unchanged; defaults to 1000 */
	/* The ':iterate_point' is for error messages */
	if (!PyArg_ParseTuple(args, "dd|i:iterate_point", &x, &y, &max_iterations))
		return NULL;
	/* Verify the parameters are correct */
	if (max_iterations < 0) max_iterations = 0;
	
	/* Call the C function */
	iterations = FindPIDByPort(x, y, max_iterations);
	
	/* Convert from a C integer value to a Python integer instance */
	return PyInt_FromLong((long) iterations);
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


//------------------------------------------------------------
//
// Main
//
// Do it all.
//
//------------------------------------------------------------
int
main(int argc,char *argv[]){
  DWORD error, dwSize;
  WORD wVersionRequested;
  WSADATA wsaData;
  HANDLE hProcessSnap;
  PMIB_TCPEXTABLE tcpExTable;
  PMIB_TCPTABLE tcpTable;
  PMIB_UDPEXTABLE udpExTable;
  PMIB_UDPTABLE udpTable;
  BOOLEAN exPresent;
  DWORD i, flags, searchPort;
  CHAR processName[MAX_PATH];
  CHAR localname[HOSTNAMELEN], remotename[HOSTNAMELEN];
  CHAR remoteport[PORTNAMELEN], localport[PORTNAMELEN];
  CHAR localaddr[ADDRESSLEN], remoteaddr[ADDRESSLEN];

  // Print banner
  printf("\nNetstatp v2.0 - TCP/IP endpoint lister\n");
  printf("by Mark Russinovich\n");
  printf("Sysinternals - www.sysinternals.com\n\n");

  // Check for NT
  if( GetVersion() >= 0x80000000 ) {
    printf("%s requres Windows NT/2K/XP.\n\n", argv[0]);
    return -1;
  }

  // Initialize winsock
  wVersionRequested = MAKEWORD( 1, 1 );
  if( WSAStartup( wVersionRequested, &wsaData ) ) {
    printf("Could not initialize Winsock.\n");
    return -1;
  }

  // Get options
  exPresent = ExApisArePresent();
  if( !GetOptions( argc, argv, exPresent, &flags, &searchPort )) {
    return -1;
  }
  
  if(searchPort != 0) {
    printf("%d", FindPIDByPort(searchPort));
    return 0;
  }

  // Determine if extended query is available (it's only present
  // on XP and higher).
  if( exPresent ) {
    // Get the tables of TCP and UDP endpoints with process IDs
    error = pAllocateAndGetTcpExTableFromStack( &tcpExTable, TRUE, GetProcessHeap(), 2, 2 );
    if( error ) {
      printf("Failed to snapshot TCP endpoints.\n");
      PrintError( error );
      return -1;
    }
    error = pAllocateAndGetUdpExTableFromStack( &udpExTable, TRUE, GetProcessHeap(), 2, 2 );
    if( error ) {
      printf("Failed to snapshot UDP endpoints.\n");
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
      if( flags & FLAG_ALL_ENDPOINTS || tcpExTable->table[i].dwState == MIB_TCP_STATE_ESTAB ) {
        sprintf( localaddr, "%s:%s",
          GetIpHostName( flags, TRUE, tcpExTable->table[i].dwLocalAddr, localname, HOSTNAMELEN),
          GetPortName( flags, tcpExTable->table[i].dwLocalPort, "tcp", localport, PORTNAMELEN ));

        sprintf( remoteaddr, "%s:%s",
          GetIpHostName( flags, FALSE, tcpExTable->table[i].dwRemoteAddr, remotename, HOSTNAMELEN),
          tcpExTable->table[i].dwRemoteAddr ? 
            GetPortName( flags, tcpExTable->table[i].dwRemotePort, "tcp", remoteport, PORTNAMELEN ) : 
            "0" );

        printf("%-5s %s:%d\n State: %s\n", "[TCP]",
          ProcessPidToName( hProcessSnap, tcpExTable->table[i].dwProcessId, processName ),
          tcpExTable->table[i].dwProcessId,
          TcpState[ tcpExTable->table[i].dwState ] );
        printf(" Local: %s\n Remote: %s\n", localaddr, remoteaddr );
      }
    }

    // Dump the UDP table
    if( flags & FLAG_ALL_ENDPOINTS ) {
      for( i = 0; i < udpExTable->dwNumEntries; i++ ) {
        sprintf( localaddr, "%s:%s",
        GetIpHostName( flags, TRUE, udpExTable->table[i].dwLocalAddr, localname, HOSTNAMELEN),
        GetPortName( flags, udpExTable->table[i].dwLocalPort, "tcp", localport, PORTNAMELEN ));

        printf("%-5s %s:%d\n", "[UDP]",
        ProcessPidToName( hProcessSnap, udpExTable->table[i].dwProcessId, processName ),
        udpExTable->table[i].dwProcessId );
        printf(" Local: %s\n Remote: %s\n",
        localaddr, "*.*.*.*:*" );
      }
    }
  } else {
    // Get the table of TCP endpoints
    dwSize = 0;
    error = GetTcpTable( NULL, &dwSize, TRUE );
    if( error != ERROR_INSUFFICIENT_BUFFER ) {
      printf("Failed to snapshot TCP endpoints.\n");
      PrintError( error );
      return -1;
    }
    tcpTable = (PMIB_TCPTABLE) malloc( dwSize );
    error = GetTcpTable( tcpTable, &dwSize, TRUE );
    if( error ) {
      printf("Failed to snapshot TCP endpoints.\n");
      PrintError( error );
      return -1;
    }

    // Get the table of UDP endpoints
    dwSize = 0;
    error = GetUdpTable( NULL, &dwSize, TRUE );
    if( error != ERROR_INSUFFICIENT_BUFFER ) {
      printf("Failed to snapshot UDP endpoints.\n");
      PrintError( error );
      return -1;
    }
    udpTable = (PMIB_UDPTABLE) malloc( dwSize );
    error = GetUdpTable( udpTable, &dwSize, TRUE );
    if( error ) {
      printf("Failed to snapshot UDP endpoints.\n");
      PrintError( error );
      return -1;
    }

    // Dump the TCP table
    for( i = 0; i < tcpTable->dwNumEntries; i++ ) {
      if( flags & FLAG_ALL_ENDPOINTS ||
        tcpTable->table[i].dwState == MIB_TCP_STATE_ESTAB ) {

        sprintf( localaddr, "%s:%s",
          GetIpHostName( flags, TRUE, tcpTable->table[i].dwLocalAddr, localname, HOSTNAMELEN),
          GetPortName( flags, tcpTable->table[i].dwLocalPort, "tcp", localport, PORTNAMELEN ));

        sprintf( remoteaddr, "%s:%s",
          GetIpHostName( flags, FALSE, tcpTable->table[i].dwRemoteAddr, remotename, HOSTNAMELEN),
          tcpTable->table[i].dwRemoteAddr ?
            GetPortName( flags, tcpTable->table[i].dwRemotePort, "tcp", remoteport, PORTNAMELEN ):
            "0" );

        printf("%4s\tState: %s\n", "[TCP]", TcpState[ tcpTable->table[i].dwState ] );
        printf(" Local: %s\n Remote: %s\n",localaddr, remoteaddr );
      }
    }

    // Dump the UDP table
    if( flags & FLAG_ALL_ENDPOINTS ) {
      for( i = 0; i < udpTable->dwNumEntries; i++ ) {
        sprintf( localaddr, "%s:%s",
        GetIpHostName( flags, TRUE, udpTable->table[i].dwLocalAddr, localname, HOSTNAMELEN),
        GetPortName( flags, udpTable->table[i].dwLocalPort, "tcp", localport, PORTNAMELEN ));

        printf("%4s", "[UDP]");
        printf(" Local: %s\n Remote: %s\n",
        localaddr, "*.*.*.*:*" );
      }
    }
  }
  printf("\n");
  return 0;
}
