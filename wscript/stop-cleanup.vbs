' stop-cleanup.vbs
' Terminates all AI Answer Assistant processes and removes runtime files.
' Safe to run multiple times — missing processes and absent files are silently skipped.

Option Explicit

Dim oShell, oFSO, sRoot

Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

' Repo root is one directory above this script (wscript\ -> repo root)
sRoot = oFSO.GetParentFolderName(oFSO.GetParentFolderName(WScript.ScriptFullName))

' ============================================================
' 1. Kill simple processes (single-word names)
' ============================================================
' /F = force terminate, /T = include child processes
' Window style 0 = hidden; bWaitOnReturn = True.
' WScript.Shell.Run returns the exit code but never raises a
' VBScript error, so taskkill's non-zero exit when a process
' is not running is harmlessly ignored.
oShell.Run "taskkill /F /IM node.exe    /T", 0, True
oShell.Run "taskkill /F /IM uvicorn.exe /T", 0, True
oShell.Run "taskkill /F /IM python.exe  /T", 0, True
oShell.Run "taskkill /F /IM ollama.exe  /T", 0, True

' ============================================================
' 2. Kill "Ollama App.exe" — process name contains a space
' ============================================================
' taskkill /IM ollama app.exe fails without quoting, and
' WScript.Shell.Run argument parsing makes quoting unreliable.
' WMI Win32_Process matches on the exact Name field and
' handles any process name regardless of spaces.
On Error Resume Next
Dim oWMI, oProcs, oProc
Set oWMI   = GetObject("winmgmts:{impersonationLevel=impersonate}!\\.\root\cimv2")
Set oProcs = oWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name = 'Ollama App.exe'")
For Each oProc In oProcs
    oProc.Terminate()
Next
Set oProcs = Nothing
Set oWMI   = Nothing
On Error GoTo 0

' ============================================================
' 3. Remove runtime files from the repo root
' ============================================================
' FileExists check makes deletion idempotent; no error handling needed.
Dim aFiles(3), sFile

aFiles(0) = sRoot & "\backend.log"
aFiles(1) = sRoot & "\frontend.log"
aFiles(2) = sRoot & "\ollama.log"
aFiles(3) = sRoot & "\ollama_llama3_installed.flag"

For Each sFile In aFiles
    If oFSO.FileExists(sFile) Then
        oFSO.DeleteFile sFile, True  ' True = force-delete even if read-only
    End If
Next

' ============================================================
' Cleanup
' ============================================================
Set oFSO   = Nothing
Set oShell = Nothing
