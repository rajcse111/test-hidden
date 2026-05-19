Option Explicit

Dim shell, fso
Dim scriptFolder, projectPath
Dim cmd

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
projectPath = fso.GetParentFolderName(scriptFolder)

cmd = "cmd /c " & _
      "cd /d """ & projectPath & """ && " & _
      "echo ==== STARTED %date% %time% ==== >> frontend.log && " & _
      "npm run electron:dev --workspace @interview/desktop >> frontend.log 2>&1"

shell.Run cmd, 0, False