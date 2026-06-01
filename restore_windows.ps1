Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int n);
  [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder t, int c);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
}
"@

# Restore all windows (SW_RESTORE = 9)
[W]::EnumWindows([W+EnumWindowsProc]{
  param($h, $l)
  $procId = 0
  [W]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
  if ($procId -eq 0) { return $true }
  $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
  if ($proc -and $proc.ProcessName -match "explorer|msedge|claude|WeMail|notepad") {
    [W]::ShowWindow($h, 9) | Out-Null  # SW_RESTORE
  }
  return $true
}, [IntPtr]::Zero) | Out-Null

Write-Host "Restored"
