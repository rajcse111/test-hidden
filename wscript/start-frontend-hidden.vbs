Option Explicit

Dim shell, fso
Dim scriptFolder, projectPath
Dim cmd
Dim depMarker, waited

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
projectPath = fso.GetParentFolderName(scriptFolder)

' start-backend-hidden.vbs runs `npm install`, which takes minutes on a fresh
' clone. Launching Vite before it finishes means `concurrently` does not exist
' yet and the hidden window dies instantly with
'   'concurrently' is not recognized as an internal or external command
' Wait for npm to produce the binary (up to 10 minutes) before starting.
depMarker = projectPath & "\node_modules\.bin\concurrently.cmd"
waited = 0
Do While Not fso.FileExists(depMarker)
    If waited >= 600 Then Exit Do   ' give up, let npm log the real error
    WScript.Sleep 2000
    waited = waited + 2
Loop

cmd = "cmd /c " & _
      "cd /d """ & projectPath & """ && " & _
      "echo ==== STARTED %date% %time% ==== >> frontend.log && " & _
      "npm run electron:dev --workspace @interview/desktop >> frontend.log 2>&1"

shell.Run cmd, 0, False