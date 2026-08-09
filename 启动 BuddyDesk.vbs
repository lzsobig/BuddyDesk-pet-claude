' BuddyDesk silent launcher
' Double-click to start without a console window.

Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
quote = Chr(34)

' Prefer the Python launcher, then common per-user installs.
pyExe = ""
pyArgs = ""
If CommandWorks("py.exe -3 --version") Then
    pyExe = "py.exe"
    pyArgs = "-3"
ElseIf CommandWorks("python.exe --version") Then
    pyExe = "python.exe"
Else
    candidates = Array( _
        localAppData & "\Programs\Python\Python312\python.exe", _
        localAppData & "\Programs\Python\Python311\python.exe", _
        localAppData & "\Programs\Python\Python310\python.exe", _
        "C:\Python312\python.exe", _
        "C:\Python311\python.exe", _
        "C:\Python310\python.exe" _
    )

    For Each p In candidates
        If fso.FileExists(p) Then
            pyExe = p
            Exit For
        End If
    Next
End If

If pyExe = "" Then
    MsgBox "Python 3.10 or newer was not found." & vbCrLf & "Install it from https://python.org and enable Add Python to PATH.", 16, "BuddyDesk"
    WScript.Quit 1
End If

pyCmd = quote & pyExe & quote
If pyArgs <> "" Then pyCmd = pyCmd & " " & pyArgs

' Only check required desktop dependencies. Voice input remains optional.
checkCmd = pyCmd & " -c " & quote & "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(x) for x in ['PySide6','openai','requests','PIL','pynput','numpy']) else 1)" & quote
If WshShell.Run(checkCmd, 0, True) <> 0 Then
    MsgBox "BuddyDesk dependencies are missing." & vbCrLf & "Run the BAT launcher once to install them.", 48, "BuddyDesk"
    WScript.Quit 1
End If

' Resolve relative assets from the project directory.
WshShell.CurrentDirectory = appDir
mainPath = appDir & "\main.py"
launchCmd = pyCmd & " " & quote & mainPath & quote
WshShell.Run launchCmd, 0, False

Set WshShell = Nothing
Set fso = Nothing

Function CommandWorks(command)
    On Error Resume Next
    exitCode = WshShell.Run(command, 0, True)
    CommandWorks = (Err.Number = 0 And exitCode = 0)
    Err.Clear
    On Error GoTo 0
End Function
