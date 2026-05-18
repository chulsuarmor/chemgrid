' install.vbs -- ChemGrid Downloader (VBScript edition)
' Worker D-M1153-002-W_INSTALLER_VBS / M1428 / 2026-05-18
'
' Compatible: Windows 95 ~ Windows 11 (wscript.exe / cscript.exe built-in)
' Components used: MSXML2.XMLHTTP (built-in), ADODB.Stream (built-in)
' Zero additional dependencies.
'
' Rule I  : No API keys in source. No hardcoded magic values without comment.
' Rule M  : No silent failure -- every error surfaces a MsgBox or WScript.Echo.
' Rule JJ : wscript default mode = no console window. cscript = console mode.
' Rule K3 : Surgical -- VBS download + launch only. No registry, no shortcuts.
'
' Usage:
'   Double-click install.vbs          (wscript -- GUI dialog, no console)
'   cscript install.vbs               (cscript -- console progress text)
'   cscript install.vbs //NoLogo      (suppress cscript banner)
'
' After download, ChemGrid.exe is placed on the Desktop and launched.

Option Explicit

' ----------------------------------------------------------------------------
' Configuration (Rule I: magic number comments)
' ----------------------------------------------------------------------------
Const DOWNLOAD_URL  = "https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc2/ChemGrid.exe"
Const EXE_NAME      = "ChemGrid.exe"
' Minimum expected file size: 100 MB = 104857600 bytes (actual ~1.17 GB)
Const MIN_BYTES     = 104857600

' Destination: %USERPROFILE%\Desktop\ChemGrid.exe (no admin required)
Dim DEST_PATH
DEST_PATH = CreateObject("WScript.Shell").ExpandEnvironmentStrings("%USERPROFILE%\Desktop\" & EXE_NAME)

' ----------------------------------------------------------------------------
' Helper: detect running host (wscript = GUI, cscript = console)
' ----------------------------------------------------------------------------
Dim bConsole
bConsole = (InStr(LCase(WScript.FullName), "cscript") > 0)

Sub Say(msg)
    If bConsole Then
        WScript.Echo msg
    End If
End Sub

Sub Alert(msg)
    ' Always show MsgBox in wscript mode; echo in cscript mode.
    If bConsole Then
        WScript.Echo "[MSG] " & msg
    Else
        MsgBox msg, 64, "ChemGrid Installer"
    End If
End Sub

Sub AlertError(msg)
    If bConsole Then
        WScript.Echo "[ERROR] " & msg
    Else
        MsgBox msg, 16, "ChemGrid Installer -- Error"
    End If
End Sub

' ----------------------------------------------------------------------------
' Step 0: Announce
' ----------------------------------------------------------------------------
Say "======================================"
Say "  ChemGrid Installer (VBScript)"
Say "======================================"
Say ""
Say "Download URL : " & DOWNLOAD_URL
Say "Destination  : " & DEST_PATH
Say ""

If Not bConsole Then
    Dim confirm
    confirm = MsgBox("ChemGrid Installer" & Chr(13) & Chr(10) & _
                     Chr(13) & Chr(10) & _
                     "ChemGrid.exe will be downloaded to:" & Chr(13) & Chr(10) & _
                     DEST_PATH & Chr(13) & Chr(10) & _
                     Chr(13) & Chr(10) & _
                     "File size: ~1.17 GB  (may take several minutes)" & Chr(13) & Chr(10) & _
                     Chr(13) & Chr(10) & _
                     "Click OK to start, Cancel to abort.", _
                     1 + 64, "ChemGrid Installer")
    ' 1 = OK+Cancel, 64 = Information icon
    ' Return value 1 = OK, 2 = Cancel
    If confirm <> 1 Then
        WScript.Quit 0
    End If
End If

' ----------------------------------------------------------------------------
' Step 1: Download via MSXML2.XMLHTTP (binary safe)
' ----------------------------------------------------------------------------
Say "[STEP 1] Connecting to GitHub..."

On Error Resume Next

Dim http
Set http = CreateObject("MSXML2.XMLHTTP")
If Err.Number <> 0 Then
    AlertError "MSXML2.XMLHTTP not available: " & Err.Description & Chr(13) & Chr(10) & _
               "This component is built into Windows. Please contact your system administrator."
    WScript.Quit 1
End If
Err.Clear

' Open synchronous GET request
http.Open "GET", DOWNLOAD_URL, False   ' False = synchronous (wait for completion)
If Err.Number <> 0 Then
    AlertError "Failed to open connection: " & Err.Description
    WScript.Quit 1
End If
Err.Clear

' Notify user that download is starting (large file -- may appear frozen)
If Not bConsole Then
    MsgBox "Download starting." & Chr(13) & Chr(10) & _
           Chr(13) & Chr(10) & _
           "The installer window will appear frozen while downloading." & Chr(13) & Chr(10) & _
           "This is normal -- ChemGrid.exe is ~1.17 GB." & Chr(13) & Chr(10) & _
           Chr(13) & Chr(10) & _
           "Click OK and wait. A second message will appear when done.", _
           64, "ChemGrid Installer -- Downloading"
End If

Say "[STEP 1] Sending HTTP request (synchronous -- may take several minutes)..."
http.Send
If Err.Number <> 0 Then
    AlertError "HTTP request failed: " & Err.Description & Chr(13) & Chr(10) & _
               "Check your internet connection and try again." & Chr(13) & Chr(10) & _
               "Manual download: " & DOWNLOAD_URL
    WScript.Quit 1
End If

' Check HTTP status (Rule M: no silent failure)
Dim httpStatus
httpStatus = http.Status
If httpStatus <> 200 Then
    AlertError "Download failed. HTTP status: " & httpStatus & Chr(13) & Chr(10) & _
               "Expected: 200 OK" & Chr(13) & Chr(10) & _
               "URL: " & DOWNLOAD_URL & Chr(13) & Chr(10) & _
               "The release asset may be missing. Visit:" & Chr(13) & Chr(10) & _
               "https://github.com/chulsuarmor/chemgrid/releases"
    WScript.Quit 1
End If
Err.Clear

Say "[OK] HTTP 200 received."

' ----------------------------------------------------------------------------
' Step 2: Save binary response via ADODB.Stream
' ----------------------------------------------------------------------------
Say "[STEP 2] Saving to " & DEST_PATH & " ..."

Dim stream
Set stream = CreateObject("ADODB.Stream")
If Err.Number <> 0 Then
    AlertError "ADODB.Stream not available: " & Err.Description & Chr(13) & Chr(10) & _
               "This component is built into Windows. Please contact your system administrator."
    WScript.Quit 1
End If
Err.Clear

stream.Type = 1          ' 1 = adTypeBinary (binary mode -- required for .exe)
stream.Open
If Err.Number <> 0 Then
    AlertError "Stream open failed: " & Err.Description
    WScript.Quit 1
End If

stream.Write http.responseBody
If Err.Number <> 0 Then
    AlertError "Stream write failed: " & Err.Description & Chr(13) & Chr(10) & _
               "Disk may be full. Required free space: ~1.5 GB on Desktop drive."
    stream.Close
    WScript.Quit 1
End If

stream.SaveToFile DEST_PATH, 2   ' 2 = adSaveCreateOverWrite (overwrite if exists)
If Err.Number <> 0 Then
    AlertError "SaveToFile failed: " & Err.Description & Chr(13) & Chr(10) & _
               "Destination: " & DEST_PATH & Chr(13) & Chr(10) & _
               "Check disk space and Desktop folder permissions."
    stream.Close
    WScript.Quit 1
End If

stream.Close
Set stream = Nothing
Set http = Nothing
Err.Clear

Say "[OK] File saved."

' ----------------------------------------------------------------------------
' Step 3: File size sanity check (Rule M: no silent delivery of corrupt file)
' ----------------------------------------------------------------------------
Say "[STEP 3] Verifying file size..."

Dim fso
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(DEST_PATH) Then
    AlertError "File not found after save: " & DEST_PATH & Chr(13) & Chr(10) & _
               "Something went wrong. Please retry."
    WScript.Quit 1
End If

Dim fileSize
fileSize = fso.GetFile(DEST_PATH).Size   ' Size in bytes (Long on 64-bit VBS host)
Set fso = Nothing

If fileSize < MIN_BYTES Then
    AlertError "Downloaded file is too small: " & fileSize & " bytes" & Chr(13) & Chr(10) & _
               "Expected at least 100 MB (100,000,000 bytes)." & Chr(13) & Chr(10) & _
               "The file may be corrupt or the release asset may be incomplete." & Chr(13) & Chr(10) & _
               "The partial file has been left at: " & DEST_PATH & Chr(13) & Chr(10) & _
               "Please delete it and retry, or download manually:" & Chr(13) & Chr(10) & _
               DOWNLOAD_URL
    WScript.Quit 1
End If

Say "[OK] File size: " & fileSize & " bytes (" & Int(fileSize / 1048576) & " MB)"

' ----------------------------------------------------------------------------
' Step 4: Launch ChemGrid.exe (Rule JJ: WScript.Shell.Run, not cmd.exe)
' ----------------------------------------------------------------------------
Say "[STEP 4] Launching " & EXE_NAME & " ..."

Dim shell
Set shell = CreateObject("WScript.Shell")
' Run with ShowWindow=1 (SW_SHOWNORMAL) so ChemGrid appears in foreground.
' WScript.Shell.Run does NOT spawn a cmd window -- Rule JJ compliant.
shell.Run """" & DEST_PATH & """", 1, False   ' 1=SW_SHOWNORMAL, False=async
If Err.Number <> 0 Then
    ' Non-fatal: file is on desktop, user can launch manually
    Say "[WARN] Auto-launch failed: " & Err.Description
    If Not bConsole Then
        MsgBox "Download complete!" & Chr(13) & Chr(10) & _
               Chr(13) & Chr(10) & _
               "ChemGrid.exe is on your Desktop." & Chr(13) & Chr(10) & _
               "Auto-launch failed (" & Err.Description & ")." & Chr(13) & Chr(10) & _
               "Please double-click ChemGrid.exe on your Desktop.", _
               48, "ChemGrid Installer -- Done"
    End If
    Err.Clear
Else
    Say "[OK] ChemGrid launched."
End If
Set shell = Nothing

' ----------------------------------------------------------------------------
' Step 5: Done
' ----------------------------------------------------------------------------
Say ""
Say "======================================"
Say "  Installation complete!"
Say "======================================"
Say ""
Say "  Executable : " & DEST_PATH
Say "  To relaunch: double-click ChemGrid.exe on your Desktop"
Say ""
Say "  For AI features (optional), create a .env file"
Say "  next to ChemGrid.exe with your API key:"
Say "    GROQ_API_KEY=your_key_here"
Say "  Free key: https://console.groq.com/keys"
Say ""
Say "  Issues: https://github.com/chulsuarmor/chemgrid/issues"
Say ""

If Not bConsole Then
    MsgBox "Installation complete!" & Chr(13) & Chr(10) & _
           Chr(13) & Chr(10) & _
           "ChemGrid.exe: " & DEST_PATH & Chr(13) & Chr(10) & _
           "(" & Int(fileSize / 1048576) & " MB)" & Chr(13) & Chr(10) & _
           Chr(13) & Chr(10) & _
           "ChemGrid is starting. Check your taskbar.", _
           64, "ChemGrid Installer -- Complete"
End If

WScript.Quit 0
