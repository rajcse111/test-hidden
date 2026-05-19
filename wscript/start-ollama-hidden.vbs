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
      "if not exist ollama_llama3_installed.flag (" & _
      "ollama pull llama3 && " & _
      "echo installed > ollama_llama3_installed.flag" & _
      ") && " & _
      "set OLLAMA_HOST=127.0.0.1:11435 && " & _
      "echo ==== STARTED %date% %time% ==== >> ollama.log && " & _
      "ollama serve >> ollama.log 2>&1"

shell.Run cmd, 0, False