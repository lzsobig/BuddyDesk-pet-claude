' BuddyDesk Silent Launcher
' Double-click to start without any console window flash

Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")

' Search for Python in common locations
pyExe = ""
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

If pyExe = "" Then
    MsgBox "Python 3.10+ not found." & vbCrLf & "Please install from https://python.org", 16, "BuddyDesk"
    WScript.Quit 1
End If

' Launch via PowerShell with hidden window (no console flash)
psCmd = "Start-Process -FilePath '" & pyExe & "' -ArgumentList 'main.py' -WorkingDirectory '" & appDir & "' -WindowStyle Hidden"
WshShell.Run "powershell.exe -NoProfile -Command """ & psCmd & """", 0, False

Set WshShell = Nothing
Set fso = Nothing
