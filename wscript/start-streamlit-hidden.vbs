Option Explicit

Dim shell, fso
Dim scriptFolder, projectPath
Dim batFile
Dim bat

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
projectPath = fso.GetParentFolderName(scriptFolder)

batFile = projectPath & "\temp_streamlit_start.bat"

Set bat = fso.CreateTextFile(batFile, True)

bat.WriteLine "@echo off"
bat.WriteLine "cd /d """ & projectPath & """"

bat.WriteLine "echo ============================== >> streamlit.log"
bat.WriteLine "echo Streamlit startup: %date% %time% >> streamlit.log"
bat.WriteLine "echo Project Path: " & projectPath & " >> streamlit.log"

bat.WriteLine "echo Checking Python venv... >> streamlit.log"
bat.WriteLine "if not exist .venv ("
bat.WriteLine "    echo ERROR: .venv not found. Run start-backend-hidden.vbs first. >> streamlit.log"
bat.WriteLine "    exit /b 1"
bat.WriteLine ")"

bat.WriteLine "echo Checking RAG requirements... >> streamlit.log"
bat.WriteLine "if not exist .venv\rag_installed.flag ("
bat.WriteLine "    echo Installing RAG requirements... >> streamlit.log"
bat.WriteLine "    .venv\Scripts\python.exe -m pip install -r local-rag\requirements.txt >> streamlit.log 2>&1"
bat.WriteLine "    echo installed > .venv\rag_installed.flag"
bat.WriteLine ")"

bat.WriteLine "echo Starting Streamlit on port 8501... >> streamlit.log"
bat.WriteLine ".venv\Scripts\python.exe -m streamlit run local-rag\web.py --server.port 8501 --server.headless true >> streamlit.log 2>&1"

bat.Close

shell.Run """" & batFile & """", 0, False
