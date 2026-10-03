Set files = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
project = files.GetParentFolderName(WScript.ScriptFullName)
buddy = files.GetParentFolderName(project) & "\BuddyDesk-pet-claude-recovered"
python = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"
island = project & "\build\WinIsland.exe"
quote = Chr(34)
If Not files.FileExists(python) Or Not files.FileExists(buddy & "\main.py") Or Not files.FileExists(island) Then
    MsgBox "The application or Python runtime could not be found.", 16, "BuddyDesk"
    WScript.Quit 1
End If
shell.CurrentDirectory = project
shell.Run quote & island & quote & " --companion", 0, False
shell.CurrentDirectory = buddy
shell.Run quote & python & quote & " " & quote & buddy & "\main.py" & quote & " --winisland", 0, False
