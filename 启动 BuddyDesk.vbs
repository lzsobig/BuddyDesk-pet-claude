' BuddyDesk Silent Launcher
' Double-click to start without console window flash
' Runs 启动 BuddyDesk.bat in hidden mode

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run """启动 BuddyDesk.bat""", 0, False
Set WshShell = Nothing
