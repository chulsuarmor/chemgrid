' install.vbs -- ChemGrid rc1 onefile EXE installer launcher (VBScript edition)
' Worker D-M1153-002-W_INSTALLER_VBS / M1428 / 2026-05-18
'
' Compatible: Windows 95 ~ Windows 11 (wscript.exe / cscript.exe built-in)
' Components used: MSXML2.XMLHTTP (built-in), ADODB.Stream (built-in)
' Zero additional dependencies.
'
' Rule I  : No API keys in source. No hardcoded magic values without comment.
' Rule M  : No silent failure -- every error surfaces a MsgBox or WScript.Echo.
' Rule JJ : wscript default mode = no console window. cscript = console mode.
' Rule K3 : Surgical -- launcher only. Canonical logic lives in install.ps1.
'
' Usage:
'   Double-click install.vbs          (wscript -- GUI dialog, no console)
'   cscript install.vbs               (cscript -- console progress text)
'   cscript install.vbs //NoLogo      (suppress cscript banner)
'
' The canonical installer downloads the pinned rc1 ChemGrid.exe to Desktop/Downloads.

Option Explicit

' ----------------------------------------------------------------------------
' Configuration (Rule I: magic number comments)
' ----------------------------------------------------------------------------
Const INSTALL_SCRIPT = "install.ps1"

' ----------------------------------------------------------------------------
' Helper: detect running host (wscript = GUI, cscript = console)
' ----------------------------------------------------------------------------
Dim bConsole
bConsole = (InStr(LCase(WScript.FullName), "cscript") > 0)

Dim dryRun
dryRun = False
If WScript.Arguments.Count > 0 Then
    Dim arg
    For Each arg In WScript.Arguments
        Select Case LCase(CStr(arg))
            Case "/?", "-?", "--help", "/help"
                WScript.Echo "Usage: cscript //NoLogo install.vbs [/dryrun]"
                WScript.Quit 0
            Case "/dryrun", "--dry-run"
                dryRun = True
        End Select
    Next
End If

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
Say "  ChemGrid Installer (VBScript launcher)"
Say "======================================"
Say ""
Say "Canonical asset: v1.0.0-lite-rc1/ChemGrid.exe"
Say ""

If Not bConsole Then
    Dim confirm
    confirm = MsgBox("ChemGrid Installer" & Chr(13) & Chr(10) & _
                     Chr(13) & Chr(10) & _
                     "The canonical PowerShell installer will download ChemGrid.exe" & Chr(13) & Chr(10) & _
                     "from the pinned v1.0.0-lite-rc1 release and start it." & Chr(13) & Chr(10) & _
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
' Step 1: Launch canonical PowerShell installer
' ----------------------------------------------------------------------------
Say "[STEP 1] Launching canonical PowerShell installer..."

Dim scriptPath
scriptPath = CreateObject("Scripting.FileSystemObject").BuildPath(CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName), INSTALL_SCRIPT)

If dryRun Then
    Say "[DRYRUN] Would run install.ps1 from: " & scriptPath
    WScript.Quit 0
End If

Dim shell
Set shell = CreateObject("WScript.Shell")
Dim rc
rc = shell.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & scriptPath & """", 1, True)
If Err.Number <> 0 Then
    AlertError "PowerShell installer failed: " & Err.Description
    Err.Clear
    WScript.Quit 1
End If
If rc <> 0 Then
    AlertError "PowerShell installer failed with exit code: " & rc
    WScript.Quit rc
End If
Set shell = Nothing
Say "[OK] Installer finished."

WScript.Quit 0
