Option Explicit

' start-ollama-hidden.vbs
' Pulls required Ollama models (once each, tracked by flag files) then starts
' the Ollama server in a hidden window with output appended to ollama.log.
'
' Models pulled:
'   llama3.2:3b       — LLM for answer generation and RAG generation
'   nomic-embed-text  — embedding model for RAG vector indexing and querying
'
' Flag files (in project root) prevent re-pulling on every launch:
'   ollama_llama3_2_3b.flag   — created after llama3.2:3b is pulled
'   ollama_nomic_embed.flag   — created after nomic-embed-text is pulled

Dim shell, fso
Dim scriptFolder, projectPath
Dim cmd

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
projectPath = fso.GetParentFolderName(scriptFolder)

cmd = "cmd /c " & _
      "cd /d """ & projectPath & """ && " & _
      "if not exist ollama_llama3_2_3b.flag (" & _
          "ollama pull llama3.2:3b && " & _
          "echo installed > ollama_llama3_2_3b.flag" & _
      ") && " & _
      "if not exist ollama_nomic_embed.flag (" & _
          "ollama pull nomic-embed-text && " & _
          "echo installed > ollama_nomic_embed.flag" & _
      ") && " & _
      "set OLLAMA_HOST=127.0.0.1:11434 && " & _
      "echo ==== STARTED %date% %time% ==== >> ollama.log && " & _
      "ollama serve >> ollama.log 2>&1"

shell.Run cmd, 0, False
