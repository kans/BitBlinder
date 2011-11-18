!macro BBCommon
  RequestExecutionLevel user /* RequestExecutionLevel REQUIRED! */

  SetCompressor /SOLID lzma
  SetCompressorDictSize 32
  CRCCheck on 

  !addplugindir installer
  !include "FileFunc.nsh"
  !include "UAC.nsh"
  !include LogicLib.nsh

  !define TORRENT_CLIENT "BitBlinder"
  !define PRODUCT_NAME "BitBlinder"
  !define PRODUCT_PUBLISHER "BitBlinder"
  !define PRODUCT_WEB_SITE "http://www.bitblinder.com/"
  Var value
!macroend

!macro UACCommon
  Function .OnInit
  ${UAC.I.Elevate.AdminOnly}
  FunctionEnd
  Function .OnInstFailed
  ${UAC.Unload}
  FunctionEnd
  Function .OnInstSuccess
  ${UAC.Unload}
  FunctionEnd
!macroend

!macro addTorrentKey
  ${GetOptions} $CMDLINE "--add-torrent=" $value
  ;MessageBox MB_OK "Adding torrent key for $value"
  WriteRegStr HKCR "${TORRENT_CLIENT}\Content Type" "" "application/x-bittorrent"
  WriteRegStr HKCR "${TORRENT_CLIENT}\DefaultIcon" "" "$value"
  WriteRegStr HKCR "${TORRENT_CLIENT}\shell" "" "open"
  WriteRegStr HKCR "${TORRENT_CLIENT}\shell\open\command" "" '"$value" --torrent "%1"'
  WriteRegStr HKCR ".torrent" "" "${TORRENT_CLIENT}"
  WriteRegStr HKCU "Software\Classes\.torrent" "" "${TORRENT_CLIENT}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.torrent" "Progid" "${TORRENT_CLIENT}"
!macroend

!macro removeTorrentKey
  DeleteRegKey HKCR "${TORRENT_CLIENT}"
  ReadRegStr $value HKCR ".torrent" ""
  ;MessageBox MB_OK "$value is .torrent key"
  StrCmp $value "${TORRENT_CLIENT}" 0 +2
    DeleteRegKey HKCR ".torrent"
  ReadRegStr $value HKCU "Software\Classes\.torrent" ""
  StrCmp $value "${TORRENT_CLIENT}" 0 +2
    DeleteRegKey HKCU "Software\Classes\.torrent"
  ReadRegStr $value HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.torrent" "Progid"
  StrCmp $value "${TORRENT_CLIENT}" 0 +2
    DeleteRegValue  HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.torrent" "Progid"
!macroend

!macro addStartupKey
  ${GetOptions} $CMDLINE "--add-startup=" $value
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" '"$value" --m --launch-bb'
!macroend

!macro removeStartupKey
  DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
!macroend
