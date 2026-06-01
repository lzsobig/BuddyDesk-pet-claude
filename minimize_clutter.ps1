Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder t, int c);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
}
"@

# Find File Explorer windows and minimize them
$explorerHwnds = @()
[W]::EnumWindows([W+EnumWindowsProc]{
  param($h, $l)
  $procId = 0
  [W]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
  if ($procId -eq 0) { return $true }  # skip PID 0
  $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
  if ($proc -and $proc.ProcessName -match "explorer" -and [W]::IsWindowVisible($h)) {
    $sb = New-Object System.Text.StringBuilder 256
    [W]::GetWindowText($h, $sb, 256) | Out-Null
    $title = $sb.ToString()
    if ($title -match "文件|explorer|Quick|搜索" -or $title.Length -eq 0 -or $title -match "Edge|浏览") {
      [W]::ShowWindow($h, 6) | Out-Null  # SW_MINIMIZE
      Write-Host "minimized: $title (hwnd=$h)"
    }
  }
  return $true
}, [IntPtr]::Zero) | Out-Null

# Find Claude window and minimize
[W]::EnumWindows([W+EnumWindowsProc]{
  param($h, $l)
  $procId = 0
  [W]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
  if ($procId -eq 0) { return $true }
  $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
  if ($proc -and ($proc.ProcessName -match "Claude" -or $proc.ProcessName -match "msedge" -or $proc.ProcessName -match "WeMail")) {
    $sb = New-Object System.Text.StringBuilder 256
    [W]::GetWindowText($h, $sb, 256) | Out-Null
    $title = $sb.ToString()
    [W]::ShowWindow($h, 6) | Out-Null
    Write-Host "minimized: $title (proc=$($proc.ProcessName))"
  }
  return $true
}, [IntPtr]::Zero) | Out-Null
