Option Explicit

Dim shell, fso
Dim scriptFolder, projectPath
Dim batFile
Dim bat

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
projectPath = fso.GetParentFolderName(scriptFolder)

batFile = projectPath & "\temp_backend_start.bat"

Set bat = fso.CreateTextFile(batFile, True)

bat.WriteLine "@echo off"
bat.WriteLine "cd /d """ & projectPath & """"

bat.WriteLine "echo ============================== >> backend.log"
bat.WriteLine "echo Backend startup: %date% %time% >> backend.log"
bat.WriteLine "echo Project Path: " & projectPath & " >> backend.log"

bat.WriteLine "echo Checking node_modules... >> backend.log"
bat.WriteLine "if not exist node_modules ("
bat.WriteLine "    echo Running npm install... >> backend.log"
bat.WriteLine "    npm install >> backend.log 2>&1"
bat.WriteLine ")"

bat.WriteLine "echo Checking Python venv... >> backend.log"
bat.WriteLine "if not exist .venv ("
bat.WriteLine "    echo Creating virtual environment... >> backend.log"
bat.WriteLine "    python -m venv .venv >> backend.log 2>&1"
bat.WriteLine ")"

bat.WriteLine "echo Checking Python requirements... >> backend.log"
bat.WriteLine "if not exist .venv\installed.flag ("
bat.WriteLine "    echo Installing requirements... >> backend.log"
bat.WriteLine "    .venv\Scripts\python.exe -m pip install -r apps\backend\requirements.txt >> backend.log 2>&1"
bat.WriteLine "    echo installed > .venv\installed.flag"
bat.WriteLine ")"

bat.WriteLine "echo Checking RAG requirements... >> backend.log"
bat.WriteLine "if not exist .venv\rag_installed.flag ("
bat.WriteLine "    echo Installing RAG requirements... >> backend.log"
bat.WriteLine "    .venv\Scripts\python.exe -m pip install -r local-rag\requirements.txt >> backend.log 2>&1"
bat.WriteLine "    echo installed > .venv\rag_installed.flag"
bat.WriteLine ")"

' IMPORTANT: Activate virtual environment
bat.WriteLine "echo Activating virtual environment... >> backend.log"
bat.WriteLine "call .venv\Scripts\activate.bat"

bat.WriteLine "echo Starting backend server... >> backend.log"
bat.WriteLine "npm run backend:dev >> backend.log 2>&1"

bat.Close

shell.Run """" & batFile & """", 0, False