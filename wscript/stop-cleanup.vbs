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
' 1. Kill child processes first (node, python, uvicorn, ollama)
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
On Error GoTo 0

' ============================================================
' 3. Kill cmd.exe processes holding the log files open
' ============================================================
' The start-*.vbs scripts launch backends via "cmd /c ... >> *.log 2>&1".
' Those cmd.exe processes keep the log files locked even after their child
' processes (node, python, uvicorn) are killed — they are the file owners.
'
' Matching strategy:
'   backend  -> cmd.exe running temp_backend_start.bat  (bat file name in CommandLine)
'   frontend -> cmd.exe with ">> frontend.log" in CommandLine
'   ollama   -> cmd.exe with ">> ollama.log"   in CommandLine
On Error Resume Next
Set oProcs = oWMI.ExecQuery( _
    "SELECT * FROM Win32_Process WHERE Name = 'cmd.exe'" & _
    " AND (" & _
    "  CommandLine LIKE '%temp_backend_start%'" & _
    "  OR CommandLine LIKE '%frontend.log%'" & _
    "  OR CommandLine LIKE '%ollama.log%'" & _
    ")")
For Each oProc In oProcs
    oProc.Terminate()
Next
Set oProcs = Nothing
Set oWMI   = Nothing
On Error GoTo 0

' ============================================================
' 4. Wait for the OS to flush all file handles
' ============================================================
' Terminate() is asynchronous; give Windows 1.5 s to release handles
' before we attempt deletion.  Without this pause, DeleteFile can still
' raise 800A0046 "Permission denied" on a file that is mid-teardown.
WScript.Sleep 1500

' ============================================================
' 5. Remove runtime files from the repo root
' ============================================================
' On Error Resume Next guards against any file that is still transitionally
' locked (edge case) — those files are silently skipped.
Dim aFiles(6), sFile

aFiles(0) = sRoot & "\backend.log"
aFiles(1) = sRoot & "\frontend.log"
aFiles(2) = sRoot & "\ollama.log"
aFiles(3) = sRoot & "\ollama_llama3_2_3b.flag"
aFiles(4) = sRoot & "\ollama_nomic_embed.flag"
aFiles(5) = sRoot & "\.venv\rag_installed.flag"
aFiles(6) = sRoot & "\temp_backend_start.bat"

On Error Resume Next
For Each sFile In aFiles
    If oFSO.FileExists(sFile) Then
        oFSO.DeleteFile sFile, True  ' True = force-delete even if read-only
    End If
Next
On Error GoTo 0

' ============================================================
' Cleanup
' ============================================================
Set oFSO   = Nothing
Set oShell = Nothing
